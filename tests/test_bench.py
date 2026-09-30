"""Tests for bench/metrics.py and bench/run.py: hand-made rows with known answers,
and the runner against an in-process fake typryx on 127.0.0.1."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bench import metrics, run

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = metrics.load_templates(ROOT / "templates")

CX = "request.complexity"      # choice: cheap/default/hard/reasoning
OM = "eval.outcome_met"        # noul
AQ = "eval.answer_quality"     # score 0..3


def row(i, family, gold, answer, probs, backend="b", **kw):
    r = {"id": f"{family}-{i}", "family": family, "gold": gold, "answer": answer,
         "probabilities": probs, "unanswered": False, "reason": None, "backend": backend,
         "model": None, "latency_ms": None, "wall_ms": None, "cost_usd": None,
         "held_back_fields": 0, "http_status": 200}
    r.update(kw)
    return r


def cx(i, gold, answer, top, rest="default", **kw):
    """A request.complexity row whose winning probability is `top` on `answer`."""
    others = [o for o in ("cheap", "default", "hard", "reasoning") if o != answer]
    probs = {answer: top, others[0]: 1 - top, others[1]: 0.0, others[2]: 0.0}
    return row(i, CX, gold, answer, probs, **kw)


def overall(rows):
    return metrics.summarise(rows, TEMPLATES)["backends"]["b"]["overall"]


class AccuracyAndWilson(unittest.TestCase):
    def test_accuracy_counts_unanswered_as_wrong(self):
        rows = [cx(i, "cheap", "cheap", 0.9) for i in range(4)]
        rows.append(cx(4, "cheap", "hard", 0.9))
        rows.append(row(5, CX, "cheap", None, None, unanswered=True, reason="low_confidence"))
        s = overall(rows)
        self.assertEqual((s["n"], s["answered"], s["correct"]), (6, 5, 4))
        self.assertAlmostEqual(s["accuracy"], 4 / 6)

    def test_wilson_bounds_8_of_10(self):
        lo, hi = metrics.wilson(8, 10)
        self.assertAlmostEqual(lo, 0.4902, places=3)
        self.assertAlmostEqual(hi, 0.9433, places=3)

    def test_wilson_edges(self):
        self.assertIsNone(metrics.wilson(0, 0))
        lo, hi = metrics.wilson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.2775, places=3)
        lo, hi = metrics.wilson(10, 10)
        self.assertAlmostEqual(lo, 0.7225, places=3)
        self.assertAlmostEqual(hi, 1.0)

    def test_summary_carries_the_interval(self):
        rows = [cx(i, "cheap", "cheap" if i < 8 else "hard", 0.9) for i in range(10)]
        lo, hi = overall(rows)["accuracy_ci95"]
        self.assertAlmostEqual(lo, 0.4902, places=3)
        self.assertAlmostEqual(hi, 0.9433, places=3)


class BrierAndEce(unittest.TestCase):
    def test_brier_sums_over_all_options(self):
        rows = [
            row(1, CX, "cheap", "cheap", {"cheap": 0.7, "default": 0.2, "hard": 0.1, "reasoning": 0.0}),
            row(2, CX, "hard", "hard", {"cheap": 0.1, "default": 0.1, "hard": 0.5, "reasoning": 0.3}),
        ]
        # 0.09+0.04+0.01+0 = 0.14 ; 0.01+0.01+0.25+0.09 = 0.36 ; mean 0.25
        self.assertAlmostEqual(overall(rows)["brier"], 0.25)

    def test_brier_counts_options_missing_from_probabilities_as_zero(self):
        rows = [row(1, CX, "cheap", "cheap", {"cheap": 0.8, "default": 0.2})]
        self.assertAlmostEqual(overall(rows)["brier"], 0.04 + 0.04)

    def test_brier_score_type_uses_index_keys(self):
        probs = {"0": 0.0, "1": 0.1, "2": 0.6, "3": 0.3}
        s = overall([row(1, AQ, 2, 2, probs)])
        self.assertAlmostEqual(s["brier"], 0.01 + 0.16 + 0.09)   # 0.26
        self.assertEqual(s["correct"], 1)

    def test_score_answer_as_float_and_string_is_compared_as_int(self):
        probs = {"0": 0.0, "1": 0.0, "2": 1.0, "3": 0.0}
        s = overall([row(1, AQ, 2, 2.0, probs), row(2, AQ, 2, "2", probs),
                     row(3, AQ, 2, 2.5, probs), row(4, AQ, 2, 3, probs)])
        self.assertEqual(s["correct"], 2)

    def test_ece_two_bins(self):
        rows = [cx(1, "cheap", "cheap", 0.95), cx(2, "default", "cheap", 0.95),   # bin 9: acc .5
                cx(3, "hard", "hard", 0.55), cx(4, "hard", "hard", 0.55)]         # bin 5: acc 1
        # |0.5-0.95|*2/4 + |1-0.55|*2/4 = 0.225 + 0.225
        self.assertAlmostEqual(overall(rows)["ece"], 0.45)

    def test_ece_confidence_of_exactly_one_lands_in_the_last_bin(self):
        rows = [cx(1, "cheap", "cheap", 1.0), cx(2, "cheap", "hard", 1.0)]
        s = overall(rows)
        self.assertAlmostEqual(s["ece"], 0.5)
        self.assertEqual(s["ece_bins"][9]["n"], 2)

    def test_ece_bin_edges_are_lower_inclusive(self):
        rows = [cx(1, "cheap", "cheap", 0.5), cx(2, "cheap", "cheap", 0.6)]
        bins = overall(rows)["ece_bins"]
        self.assertEqual((bins[5]["n"], bins[6]["n"]), (1, 1))

    def test_unanswered_are_excluded_from_brier_and_ece_but_counted(self):
        rows = [cx(1, "cheap", "cheap", 0.9),
                row(2, CX, "cheap", None, None, unanswered=True, reason="backend_failed"),
                row(3, CX, "cheap", None, {"cheap": 0.6, "default": 0.4}, unanswered=True,
                    reason="backend_failed", http_status=500),   # probabilities present: still excluded
                row(4, CX, "cheap", None, None, unanswered=True, reason="low_confidence")]
        s = overall(rows)
        self.assertEqual((s["n"], s["answered"], s["unanswered"], s["scored"]), (4, 1, 3, 1))
        # one scored row: (0.9-1)^2 + (0.1-0)^2 = 0.02 ; the unanswered would change this if they leaked in
        self.assertAlmostEqual(s["brier"], 0.02)
        self.assertAlmostEqual(s["ece"], 0.1)
        self.assertEqual(s["unanswered_reasons"], {"backend_failed": 2, "low_confidence": 1})
        self.assertAlmostEqual(s["unanswered_rate"], 0.75)
        self.assertEqual(s["errors"], 1)

    def test_answered_row_without_probabilities_counts_for_accuracy_only(self):
        s = overall([row(1, CX, "cheap", "cheap", None)])
        self.assertEqual((s["correct"], s["scored"]), (1, 0))
        self.assertIsNone(s["brier"])
        self.assertIsNone(s["ece"])


class NoulThreshold(unittest.TestCase):
    def test_threshold_is_p_true_at_least_one_half(self):
        def om(i, gold, p):
            return row(i, OM, gold, p, {"true": p, "false": round(1 - p, 10)})
        rows = [om(1, True, 0.5),     # exactly 0.5 predicts true: correct
                om(3, False, 0.49),   # correct
                om(4, True, 0.49),    # wrong
                om(5, True, 0.9)]     # correct
        s = overall(rows)
        self.assertEqual(s["correct"], 3)

    def test_noul_brier_is_over_true_and_false(self):
        s = overall([row(1, OM, True, 0.8, {"true": 0.8, "false": 0.2}),
                     row(2, OM, False, 0.3, {"true": 0.3, "false": 0.7})])
        # 0.04+0.04 and 0.09+0.09 -> mean 0.13
        self.assertAlmostEqual(s["brier"], 0.13)

    def test_noul_confidence_is_the_max_probability(self):
        # P(true)=0.2 means a confident "false": confidence 0.8, bin 8, correct
        s = overall([row(1, OM, False, 0.2, {"true": 0.2, "false": 0.8})])
        self.assertEqual(s["correct"], 1)
        self.assertEqual(s["ece_bins"][8]["n"], 1)
        self.assertAlmostEqual(s["ece"], 0.2)


class Percentiles(unittest.TestCase):
    def test_linear_interpolation(self):
        self.assertEqual(metrics.percentile([10, 20, 30, 40, 50], 50), 30)
        self.assertAlmostEqual(metrics.percentile([10, 20, 30, 40, 50], 95), 48.0)
        self.assertEqual(metrics.percentile([7], 95), 7)
        self.assertIsNone(metrics.percentile([], 50))
        self.assertEqual(metrics.percentile([50, 10, 30], 50), 30)   # unsorted input

    def test_latency_and_wall_are_separate_series(self):
        rows = [cx(i, "cheap", "cheap", 0.9, latency_ms=l, wall_ms=w)
                for i, (l, w) in enumerate([(10, 100), (20, 200), (30, 300), (40, 400), (50, 500)])]
        s = overall(rows)
        self.assertEqual(s["latency_ms"]["p50"], 30)
        self.assertAlmostEqual(s["latency_ms"]["p95"], 48.0)
        self.assertEqual(s["wall_ms"]["p50"], 300)
        self.assertAlmostEqual(s["wall_ms"]["p95"], 480.0)


class CostAndHeldBack(unittest.TestCase):
    def test_cost_total_per_1000_and_held_back(self):
        rows = [cx(i, "cheap", "cheap", 0.9, cost_usd=0.001, held_back_fields=1) for i in range(4)]
        rows.append(row(9, CX, "cheap", None, None, unanswered=True, reason="x", cost_usd=None,
                        held_back_fields=2))
        s = overall(rows)
        self.assertAlmostEqual(s["cost_usd_total"], 0.004)
        self.assertAlmostEqual(s["cost_usd_per_1000"], 0.8)   # over all 5 decisions
        self.assertEqual(s["held_back_fields"], 6)


class GroupingAndProducers(unittest.TestCase):
    def test_per_family_and_per_backend(self):
        rows = [cx(1, "cheap", "cheap", 0.9), cx(2, "cheap", "hard", 0.9),
                row(3, OM, True, 0.9, {"true": 0.9, "false": 0.1}),
                cx(4, "cheap", "cheap", 0.9, backend="other")]
        out = metrics.summarise(rows, TEMPLATES)["backends"]
        self.assertEqual(sorted(out), ["b", "other"])
        self.assertEqual(out["b"]["overall"]["n"], 3)
        self.assertEqual(out["b"]["families"][CX]["accuracy"], 0.5)
        self.assertEqual(out["b"]["families"][OM]["accuracy"], 1.0)
        self.assertEqual(out["other"]["overall"]["accuracy"], 1.0)

    def test_a_baseline_with_only_the_core_fields_is_scored_the_same(self):
        rows = [{"id": "cx-1", "family": CX, "gold": "cheap", "answer": "cheap",
                 "probabilities": {"cheap": 1.0}, "unanswered": False, "backend": "majority"},
                {"id": "cx-2", "family": CX, "gold": "hard", "answer": "cheap",
                 "probabilities": {"cheap": 1.0}, "unanswered": False, "backend": "majority"}]
        s = metrics.summarise(rows, TEMPLATES)["backends"]["majority"]["overall"]
        self.assertEqual(s["accuracy"], 0.5)
        self.assertIsNone(s["latency_ms"]["p50"])
        self.assertEqual(s["cost_usd_total"], 0)
        # row 2: (1-0)^2 + (0-1)^2 = 2 ; row 1: 0 ; mean 1
        self.assertAlmostEqual(s["brier"], 1.0)

    def test_repeated_id_keeps_the_last_row(self):
        a, b = cx(1, "cheap", "hard", 0.9), cx(1, "cheap", "cheap", 0.9)
        blk = metrics.summarise([a, b], TEMPLATES)["backends"]["b"]
        self.assertEqual(blk["overall"]["n"], 1)
        self.assertEqual(blk["overall"]["correct"], 1)
        self.assertEqual(blk["duplicate_ids_dropped"], 1)

    def test_cli_text_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.jsonl"
            p.write_text("\n".join(json.dumps(cx(i, "cheap", "cheap", 0.9)) for i in range(3)) + "\n{torn")
            buf, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
                self.assertEqual(metrics.main([str(p), "--json", str(Path(d) / "m.json")]), 0)
            self.assertIn("backend: b", buf.getvalue())
            self.assertIn("skipped unparsable", err.getvalue())
            data = json.loads((Path(d) / "m.json").read_text())
            self.assertEqual(data["backends"]["b"]["overall"]["n"], 3)
            self.assertEqual(data["meta"]["unparsable_lines"], 1)

    def test_empty_input_measures_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.jsonl"
            p.write_text("")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(metrics.main([str(p)]), 1)
            self.assertIn("measured nothing", err.getvalue())


# ---------------------------------------------------------------- run.py ---

KEY = "sk-test-SECRET-0123456789"


class FakeTypryx(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), FakeHandler)
        self.calls, self.keys, self.lock = [], [], threading.Lock()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"


class FakeHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with self.server.lock:
            self.server.calls.append((self.path, body))
            self.server.keys.append(self.headers.get("X-Typryx-Key"))
        prompt = body["state"]["prompt"]
        if "BOOM" in prompt:
            return self._send(500, {"error": "internal"})
        if "SLOW" in prompt:
            time.sleep(1.0)
            return self._send(200, {})
        if "ABSTAIN" in prompt:
            return self._send(200, {"template": body["template"], "unanswered": True,
                                    "reason": "low_confidence", "latency_ms": 3,
                                    "held_back_fields": 1})
        if "GARBAGE" in prompt:
            raw = b"<html>not json</html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            return self.wfile.write(raw)
        if "DELAY" in prompt:
            time.sleep(0.06)
        label = "hard" if "hard" in prompt else "cheap"
        self._send(200, {"template": body["template"], "template_version": "v1", "type": "choice",
                         "answer": label, "probabilities": {label: 0.9, "default": 0.1},
                         "backend": "stub", "model": "fake-1", "latency_ms": 7, "cost_usd": 0.002,
                         "held_back_fields": 1})


def prompt_rows():
    spec = [("a", "cheap", "say cheap DELAY"), ("b", "hard", "say hard"), ("c", "cheap", "BOOM"),
            ("d", "cheap", "SLOW"), ("e", "cheap", "ABSTAIN"), ("f", "cheap", "GARBAGE")]
    return [{"id": f"cx-{i}", "family": CX, "template": CX, "gold": g,
             "group": f"g{i}", "source": "construct", "state": {"prompt": p}}
            for i, g, p in spec]


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.data = d / "data"
        self.data.mkdir()
        blob = "".join(json.dumps(r, sort_keys=True) + "\n" for r in prompt_rows()).encode()
        (self.data / "test.jsonl").write_bytes(blob)
        self.write_manifest(blob)
        self.keyfile = d / "key"
        self.keyfile.write_text(KEY + "\n")
        self.out = d / "results" / "fake.jsonl"
        self.server = FakeTypryx()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def write_manifest(self, blob):
        (self.data / "MANIFEST.json").write_text(json.dumps(
            {"files": {"test.jsonl": {"sha256": hashlib.sha256(blob).hexdigest(), "rows": 6}}}))

    def go(self, *extra):
        argv = ["--typryx-url", self.server.url, "--key-file", str(self.keyfile),
                "--backend-name", "fake", "--split", "test", "--out", str(self.out),
                "--data-dir", str(self.data), "--timeout", "0.3", *extra]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run.main(argv)
        return code, out.getvalue(), err.getvalue()

    def results(self):
        out = {}
        for line in self.out.read_text().splitlines():
            try:
                out[json.loads(line)["id"]] = json.loads(line)
            except (json.JSONDecodeError, KeyError):
                pass   # the torn line a crash left behind
        return out

    def test_every_row_is_recorded_and_bad_rows_do_not_abort(self):
        code, out, err = self.go()
        self.assertEqual(code, 0)
        res = self.results()
        self.assertEqual(sorted(res), [f"cx-{c}" for c in "abcdef"])
        for r in res.values():
            for f in run.FIELDS:
                self.assertIn(f, r)
        a = res["cx-a"]
        self.assertEqual((a["answer"], a["unanswered"], a["http_status"], a["backend"]),
                         ("cheap", False, 200, "fake"))
        self.assertEqual((a["latency_ms"], a["model"], a["cost_usd"], a["held_back_fields"]),
                         (7, "fake-1", 0.002, 1))
        self.assertGreaterEqual(a["wall_ms"], 60)             # the runner's own clock saw the delay
        self.assertEqual(a["gold"], "cheap")
        b = res["cx-b"]
        self.assertEqual(b["answer"], "hard")
        c = res["cx-c"]                                        # HTTP 500
        self.assertEqual((c["http_status"], c["unanswered"], c["reason"]),
                         (500, True, "error:http_500"))
        d = res["cx-d"]                                        # timeout
        self.assertEqual((d["http_status"], d["unanswered"], d["reason"]),
                         (None, True, "error:timeout"))
        self.assertGreaterEqual(d["wall_ms"], 290)
        e = res["cx-e"]                                        # typryx abstained
        self.assertEqual((e["http_status"], e["unanswered"], e["reason"], e["held_back_fields"]),
                         (200, True, "low_confidence", 1))
        f = res["cx-f"]
        self.assertEqual((f["unanswered"], f["reason"]), (True, "error:bad_json"))

    def test_request_shape_and_key_header(self):
        self.go("--limit", "2")
        self.assertEqual(self.server.keys, [KEY, KEY])
        path, body = self.server.calls[0]
        self.assertEqual(path, "/v1/ask")
        self.assertEqual(body, {"template": CX, "state": {"prompt": "say cheap DELAY"}})

    def test_the_key_is_never_printed_or_written(self):
        code, out, err = self.go()
        self.assertEqual(code, 0)
        self.assertNotIn(KEY, out + err + self.out.read_text())
        code, out, err = self.go("--typryx-url", "http://127.0.0.1:1")   # refused connection
        self.assertNotIn(KEY, out + err)

    def test_progress_is_printed_every_25_rows(self):
        big = [dict(prompt_rows()[1], id=f"cx-{i}") for i in range(60)]
        blob = "".join(json.dumps(r) + "\n" for r in big).encode()
        (self.data / "test.jsonl").write_bytes(blob)
        self.write_manifest(blob)
        code, out, err = self.go()
        self.assertEqual(code, 0)
        lines = [l for l in out.splitlines() if l.startswith("run: ") and "/60 done" in l]
        self.assertEqual(len(lines), 2)
        self.assertIn("25/60", lines[0])
        self.assertIn("50/60", lines[1])

    def test_resume_skips_ids_already_in_the_output(self):
        self.go("--limit", "2")
        self.assertEqual(len(self.server.calls), 2)
        self.go()
        self.assertEqual(len(self.server.calls), 2 + 4)       # only the four missing rows asked
        self.assertEqual(len(self.results()), 6)
        self.assertEqual(len(self.out.read_text().splitlines()), 6)
        self.go()
        self.assertEqual(len(self.server.calls), 6)           # nothing left to ask

    def test_resume_tolerates_a_torn_last_line(self):
        self.go("--limit", "2")
        with open(self.out, "a") as fh:
            fh.write('{"id": "cx-c", "fam')
        self.go()
        self.assertEqual(sorted(self.results()), [f"cx-{c}" for c in "abcdef"])
        self.assertEqual(len(self.results()), 6)

    def test_concurrency_gives_the_same_set_of_rows(self):
        code, _, _ = self.go("--concurrency", "4")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(self.results()), [f"cx-{c}" for c in "abcdef"])
        self.assertEqual(self.results()["cx-c"]["http_status"], 500)

    def test_a_changed_test_file_is_refused_before_any_request(self):
        path = self.data / "test.jsonl"
        blob = path.read_bytes()
        path.write_bytes(blob.replace(b"say cheap", b"say chEap", 1))
        code, out, err = self.go()
        self.assertNotEqual(code, 0)
        self.assertIn("refusing to run", err)
        self.assertIn("frozen", err)
        self.assertEqual(self.server.calls, [])
        self.assertFalse(self.out.exists())

    def test_a_missing_manifest_is_refused_not_passed(self):
        (self.data / "MANIFEST.json").unlink()
        code, out, err = self.go()
        self.assertNotEqual(code, 0)
        self.assertIn("measured nothing", err)
        self.assertEqual(self.server.calls, [])

    def test_a_missing_key_file_stops_the_run(self):
        self.keyfile.unlink()
        code, out, err = self.go()
        self.assertEqual(code, 2)
        self.assertEqual(self.server.calls, [])

    def test_runner_output_feeds_metrics_unchanged(self):
        self.go()
        rows, _ = metrics.read_results([self.out])
        s = metrics.summarise(rows, TEMPLATES)["backends"]["fake"]["overall"]
        # a: cheap ok, b: hard vs gold hard ok, c/d/e/f unanswered
        self.assertEqual((s["n"], s["answered"], s["correct"]), (6, 2, 2))
        self.assertEqual(s["unanswered_reasons"], {"error:bad_json": 1, "error:http_500": 1,
                                                   "error:timeout": 1, "low_confidence": 1})
        self.assertEqual(s["errors"], 1)                      # the 500 (no status for the timeout)
        self.assertAlmostEqual(s["cost_usd_total"], 0.004)
        self.assertEqual(s["latency_ms"]["p50"], 7)


if __name__ == "__main__":
    unittest.main()
