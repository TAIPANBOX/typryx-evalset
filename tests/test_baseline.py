"""Tests for the two no-model baselines (baseline/constant.py, baseline/rules.py, baseline/predict.py).

Nothing here opens data/test.jsonl: the refusal test builds its own throwaway root.
"""
import collections
import glob
import hashlib
import json
import os
import shutil
import tempfile
import unittest

from baseline import constant, predict, rules

ROOT = constant.ROOT
TEMPLATES = constant.load_templates(ROOT)


def _row(family, gold, state=None, i=0):
    return {"id": f"{family}-{i}", "family": family, "template": family, "state": state or {}, "gold": gold,
            "group": "g", "source": "construct"}


class ConstantBaseline(unittest.TestCase):
    def test_picks_the_train_majority_per_family(self):
        rows = ([_row("request.complexity", "hard", i=i) for i in range(3)]
                + [_row("request.complexity", "cheap", i=10 + i) for i in range(2)]
                + [_row("eval.outcome_met", False, i=i) for i in range(4)]
                + [_row("eval.outcome_met", True, i=10)]
                + [_row("eval.answer_quality", 2, i=i) for i in range(3)]
                + [_row("eval.answer_quality", 0, i=10)])
        c = constant.Constant(rows, TEMPLATES)
        self.assertEqual(c.predict("request.complexity", {}), "hard")
        self.assertIs(c.predict("eval.outcome_met", {}), False)
        self.assertEqual(c.predict("eval.answer_quality", {}), 2)

    def test_ties_go_to_the_first_option_in_criteria_order(self):
        rows = [_row("request.complexity", "reasoning"), _row("request.complexity", "default"),
                _row("eval.outcome_met", False), _row("eval.outcome_met", True),
                _row("eval.answer_quality", 3), _row("eval.answer_quality", 1)]
        c = constant.Constant(rows, TEMPLATES)
        self.assertEqual(c.predict("request.complexity", {}), "default")  # cheap, default, hard, reasoning
        self.assertIs(c.predict("eval.outcome_met", {}), True)  # "true" is listed before "false"
        self.assertEqual(c.predict("eval.answer_quality", {}), 1)  # lowest index wins
        self.assertEqual(c.predict("console.question_topic", {}), "spend")  # no rows at all: first option

    def test_matches_the_real_train_majority(self):
        rows = constant.load_jsonl(os.path.join(ROOT, "data", "train.jsonl"))
        c = constant.Constant(rows, TEMPLATES)
        for fam in TEMPLATES:
            counts = collections.Counter(r["gold"] for r in rows if r["family"] == fam)
            best = max(counts.values())
            self.assertEqual(counts[c.predict(fam, {})], best, fam)


class RulesBaseline(unittest.TestCase):
    def check(self, family, state, want):
        self.assertEqual(rules.Rules().predict(family, state), want, state)

    def test_complexity(self):
        f = "request.complexity"
        self.check(f, {"prompt": "What does DNS stand for?"}, "cheap")
        self.check(f, {"prompt": "Explain the difference between a mutex and a semaphore to a new hire, in a few paragraphs."}, "default")
        self.check(f, {"prompt": "Design a zero-downtime migration of our billing database to a new region, covering cutover, rollback and the audit trail for the finance team."}, "hard")
        self.check(f, {"prompt": "Prove that the sum of two even numbers is even, step by step."}, "reasoning")

    def test_triage(self):
        f = "triage.anomaly_class"
        self.check(f, {"anomaly": "project=a spend_delta=+200%", "recent_changes": "calls_delta=+198%, traffic_delta=+195%, unique_ratio=0.80, price_delta=+1%, event=none"}, "expected_growth")
        self.check(f, {"anomaly": "project=a spend_delta=+400%", "recent_changes": "calls_delta=+390%, traffic_delta=+2%, unique_ratio=0.10, price_delta=+0%, event=none"}, "runaway_agent")
        self.check(f, {"anomaly": "project=a spend_delta=+80%", "recent_changes": "calls_delta=+1%, traffic_delta=+0%, unique_ratio=0.70, price_delta=+82%, event=none"}, "price_change")
        self.check(f, {"anomaly": "spend up 120%", "recent_changes": "The rate limit on the route was removed yesterday."}, "misconfiguration")
        self.check(f, {"anomaly": "Budget alert: spend is up 50% week over week.", "recent_changes": "No call breakdown available. The change log is empty."}, "unknown")

    def test_outcome_met_evaluates_what_a_regex_can_evaluate(self):
        f = "eval.outcome_met"
        t = lambda task, ans: {"task": task, "final_answer": ans}  # noqa: E731
        self.check(f, t("What is 12 + 30?", "42"), True)
        self.check(f, t("What is 12 + 30?", "43"), False)
        self.check(f, t("Compute 6 * 7.", "The answer is 42."), True)
        self.check(f, t("Compute 6 * 7.", "The answer is 48."), False)
        self.check(f, t("Reverse this word: gateway", "Reversed: yawetag"), True)
        self.check(f, t("Reverse this word: gateway", "Reversed: yaweatg"), False)
        self.check(f, t("Make this string uppercase: quota", "QUOTA"), True)
        self.check(f, t("Make this string uppercase: quota", "QUOTa"), False)
        self.check(f, t("How many times does the letter 'e' appear in \"deployment\"?", "2"), True)
        self.check(f, t("How many times does the letter 'e' appear in \"deployment\"?", "3"), False)
        self.check(f, t("Sort ascending: 9 3 7", "3 7 9"), True)
        self.check(f, t("Sort ascending: 9 3 7", "3 9 7"), False)
        self.check(f, t("Which weekday is 2024-03-01?", "Friday"), True)
        self.check(f, t("Which weekday is 2024-03-01?", "Monday"), False)
        self.check(f, t("How many items are in this list: a, b, c?", "3"), True)
        self.check(f, t("Convert: 2 feet -> inches", "24 inches"), True)
        self.check(f, t("Out of apple, saw, pear, how many are fruits?", "2"), True)  # cannot be checked: trust

    def test_answer_quality_counts_items(self):
        f = "eval.answer_quality"
        task4 = "List four benefits of code review."
        items = ["Catches bugs early", "Spreads knowledge", "Keeps style consistent", "Improves design"]
        self.check(f, {"task": task4, "final_answer": "\n".join(items)}, 3)
        self.check(f, {"task": task4, "final_answer": "\n".join(items[:3])}, 2)
        self.check(f, {"task": task4, "final_answer": "\n".join(items[:1]) + "\nHope that helps."}, 1)
        self.check(f, {"task": task4, "final_answer": "Happy to help. Let me know if you want more detail."}, 0)
        self.check(f, {"task": "Give three reasons to cache.", "final_answer": "Speed. Cost. Load. Let me know how it goes."}, 3)

    def test_risk_class(self):
        f = "action.risk_class"
        self.check(f, {"tool": "github.list_issues", "arguments": "repo=a/b", "target": "a/b"}, "read_only")
        self.check(f, {"tool": "github.create_branch", "arguments": "name=x", "target": "a/b"}, "reversible_change")
        self.check(f, {"tool": "s3.delete_bucket", "arguments": "bucket=x", "target": "s3://x"}, "destructive")
        self.check(f, {"tool": "email.send_email", "arguments": "to=a@b.example", "target": "external"}, "external_send")
        self.check(f, {"tool": "stripe.create_refund", "arguments": "charge=ch_1", "target": "acct"}, "financial")
        self.check(f, {"tool": "db.run_query", "arguments": "{\"sql\": \"DROP TABLE t\"}", "target": "db"}, "destructive")
        self.check(f, {"tool": "db.run_query", "arguments": "{\"sql\": \"SELECT 1\"}", "target": "db"}, "read_only")

    def test_console_topic(self):
        f = "console.question_topic"
        self.check(f, {"question": "How much did we spend on tokens last week?"}, "spend")
        self.check(f, {"question": "We are seeing a spike in 502 errors, what is going on?"}, "incident")
        self.check(f, {"question": "Which agent identities are active in sandbox?"}, "identity")
        self.check(f, {"question": "Who has to sign off on this deploy?"}, "approval")
        self.check(f, {"question": "Are there any pending approvals for payments-bot?"}, "approval")
        self.check(f, {"question": "Is the invoice for March correct?"}, "spend")
        self.check(f, {"question": "Was the key for code-reviewer rotated?"}, "identity")
        self.check(f, {"question": "Is the gateway degraded right now?"}, "incident")
        self.check(f, {"question": "How do I export a table to CSV?"}, "other")


class PredictOutput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def lines(self, which):
        out = os.path.join(self.tmp.name, "results", which + ".jsonl")
        n = predict.run(which, "dev", out)
        with open(out, encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh]
        self.assertEqual(len(rows), n)
        return rows

    def test_rows_have_the_runner_shape(self):
        keys = ["id", "family", "gold", "answer", "probabilities", "unanswered", "reason", "backend", "model",
                "latency_ms", "wall_ms", "cost_usd", "held_back_fields", "http_status"]
        dev = constant.load_jsonl(os.path.join(ROOT, "data", "dev.jsonl"))
        for which, model in (("constant", "constant-v1"), ("rules", "rules-v1")):
            rows = self.lines(which)
            self.assertEqual([r["id"] for r in rows], [r["id"] for r in dev])
            for r in rows:
                self.assertEqual(list(r), keys)
                self.assertIs(r["unanswered"], False)
                self.assertIsNone(r["reason"])
                self.assertIsNone(r["http_status"])
                self.assertEqual((r["backend"], r["model"]), (which, model))
                self.assertEqual((r["cost_usd"], r["held_back_fields"]), (0, 0))
                self.assertIsInstance(r["latency_ms"], int)
                self.assertIsInstance(r["wall_ms"], int)
                self.assertAlmostEqual(sum(r["probabilities"].values()), 1.0)
                kind = TEMPLATES[r["family"]]["type"]
                if kind == "noul":
                    self.assertIn(r["answer"], (0.0, 1.0))
                    self.assertIsInstance(r["answer"], float)
                    self.assertEqual(set(r["probabilities"]), {"true", "false"})
                    self.assertEqual(r["probabilities"]["true"], r["answer"])
                elif kind == "score":
                    self.assertIsInstance(r["answer"], int)
                    self.assertNotIsInstance(r["answer"], bool)
                    self.assertEqual(set(r["probabilities"]), {"0", "1", "2", "3"})
                    self.assertEqual(r["probabilities"][str(r["answer"])], 1.0)
                else:
                    self.assertIn(r["answer"], TEMPLATES[r["family"]]["criteria"])
                    self.assertEqual(set(r["probabilities"]), set(TEMPLATES[r["family"]]["criteria"]))
                    self.assertEqual(r["probabilities"][r["answer"]], 1.0)


class TestSplitIsGuarded(unittest.TestCase):
    """--split test is refused unless the file matches the manifest hash (throwaway root, never the real file)."""

    def make_root(self, tamper):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = tmp.name
        os.makedirs(os.path.join(root, "data"))
        shutil.copytree(os.path.join(ROOT, "templates"), os.path.join(root, "templates"))
        rows = [_row("console.question_topic", "spend", {"question": "what did we spend?"}, i=1)]
        body = "".join(json.dumps(r) + "\n" for r in rows)
        for name in ("train.jsonl", "test.jsonl"):
            with open(os.path.join(root, "data", name), "w", encoding="utf-8") as fh:
                fh.write(body)
        manifest = {"files": {"test.jsonl": {"sha256": hashlib.sha256(body.encode()).hexdigest()}}}
        with open(os.path.join(root, "data", "MANIFEST.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)
        if tamper:
            with open(os.path.join(root, "data", "test.jsonl"), "a", encoding="utf-8") as fh:
                fh.write(" \n")
        return root

    def test_a_changed_file_is_refused_and_nothing_is_written(self):
        root = self.make_root(tamper=True)
        out = os.path.join(root, "out.jsonl")
        with self.assertRaises(SystemExit) as cm:
            predict.run("rules", "test", out, root=root)
        self.assertIn("refusing", str(cm.exception))
        self.assertFalse(os.path.exists(out))

    def test_the_frozen_file_is_accepted(self):
        root = self.make_root(tamper=False)
        out = os.path.join(root, "out.jsonl")
        self.assertEqual(predict.run("rules", "test", out, root=root), 1)
        self.assertTrue(os.path.exists(out))

    def test_a_missing_manifest_entry_is_not_a_pass(self):
        root = self.make_root(tamper=False)
        with open(os.path.join(root, "data", "MANIFEST.json"), "w", encoding="utf-8") as fh:
            json.dump({"files": {}}, fh)
        with self.assertRaises(KeyError):
            predict.run("rules", "test", os.path.join(root, "out.jsonl"), root=root)


class RulesAreBlindToTheTestFile(unittest.TestCase):
    def test_only_predict_py_names_the_test_file(self):
        files = sorted(glob.glob(os.path.join(ROOT, "baseline", "*.py")))
        names = [os.path.basename(f) for f in files]
        self.assertIn("rules.py", names, "measured nothing: baseline/rules.py is missing")
        self.assertIn("predict.py", names)
        def text(path):
            with open(path, encoding="utf-8") as fh:
                return fh.read()

        offenders = [n for f, n in zip(files, names) if n != "predict.py" and "test.jsonl" in text(f)]
        self.assertEqual(offenders, [])
        self.assertIn("test.jsonl", text(os.path.join(ROOT, "baseline", "predict.py")),
                      "measured nothing: predict.py no longer guards the test file")


if __name__ == "__main__":
    unittest.main()
