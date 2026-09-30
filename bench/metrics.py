#!/usr/bin/env python3
"""Metrics over benchmark result files (results/*.jsonl). Stdlib only.

Reads rows of the shape bench/run.py writes; any other producer (for example a
no-model baseline) uses the same shape and is treated identically. Rows are
grouped by their `backend` field, overall and per family.

Correctness, by template type (taken from templates/<family>.json):
  choice  answer == gold
  score   int(answer) == gold
  noul    `answer` is P(true); predicted = P(true) >= 0.5; correct if predicted == gold
An unanswered row (unanswered=true, no answer, a runner error) is WRONG for
accuracy and is excluded from Brier and ECE; both counts are reported.

Brier: sum over the template's options of (p - onehot)^2, averaged over rows.
ECE: 10 equal-width bins on the max probability (confidence), weighted by bin size.
Percentiles: linear interpolation between order statistics.

  python3 bench/metrics.py results/*.jsonl [--json [PATH|-]] [--templates DIR]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
Z95 = 1.959963984540054
ECE_BINS = 10


def wilson(k: int, n: int, z: float = Z95):
    """Wilson score interval for k successes in n trials; None when n == 0."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def percentile(values, q: float):
    """q in [0,100], linear interpolation; None for an empty list."""
    xs = sorted(values)
    if not xs:
        return None
    if len(xs) == 1:
        return float(xs[0])
    rank = q / 100 * (len(xs) - 1)
    lo = int(math.floor(rank))
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (rank - lo)


def load_templates(directory: Path) -> dict:
    """{template id: {"type": ..., "options": [...]}} from templates/*.json."""
    out = {}
    for path in sorted(Path(directory).glob("*.json")):
        t = json.loads(path.read_text())
        kind = t["type"]
        if kind == "choice":
            options = list(t["criteria"].keys())
        elif kind == "score":
            options = [str(i) for i in range(len(t["criteria"]))]
        elif kind == "noul":
            options = ["true", "false"]
        else:
            continue
        out[t["id"]] = {"type": kind, "options": options}
    return out


def _infer_type(gold) -> str:
    if isinstance(gold, bool):
        return "noul"
    if isinstance(gold, int):
        return "score"
    return "choice"


def _gold_key(gold, kind: str) -> str:
    if kind == "noul":
        return "true" if gold else "false"
    return str(gold)


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def is_answered(row: dict) -> bool:
    return not row.get("unanswered") and row.get("answer") is not None


def is_correct(row: dict, kind: str) -> bool:
    """Only meaningful for an answered row; any malformed answer is wrong."""
    answer, gold = row["answer"], row["gold"]
    if kind == "noul":
        if isinstance(answer, bool):
            predicted = answer
        elif _is_number(answer):
            predicted = answer >= 0.5
        else:
            return False
        return predicted == bool(gold)
    if kind == "score":
        if isinstance(answer, bool):
            return False
        try:
            value = float(answer)
        except (TypeError, ValueError):
            return False
        return value == int(value) and int(value) == int(gold)
    return answer == gold


def _valid_probs(probs) -> bool:
    return (isinstance(probs, dict) and len(probs) > 0
            and all(_is_number(v) for v in probs.values()))


def brier(probs: dict, gold_key: str, options) -> float:
    return sum((float(probs.get(o, 0.0)) - (1.0 if o == gold_key else 0.0)) ** 2
               for o in options)


def ece(pairs):
    """pairs = [(confidence, correct)]. Returns (ece, bins) or (None, bins)."""
    bins = [{"bin": i, "lo": i / ECE_BINS, "hi": (i + 1) / ECE_BINS,
             "n": 0, "conf": 0.0, "acc": 0.0} for i in range(ECE_BINS)]
    total = len(pairs)
    for conf, ok in pairs:
        b = bins[min(int(conf * ECE_BINS), ECE_BINS - 1)]
        b["n"] += 1
        b["conf"] += conf
        b["acc"] += 1.0 if ok else 0.0
    value = 0.0
    for b in bins:
        if b["n"]:
            b["conf"] /= b["n"]
            b["acc"] /= b["n"]
            value += b["n"] / total * abs(b["acc"] - b["conf"])
        else:
            b["conf"] = b["acc"] = None
    return (value if total else None), bins


def _lat(values):
    return {"n": len(values), "p50": percentile(values, 50), "p95": percentile(values, 95)}


def stats(rows, templates: dict) -> dict:
    n = len(rows)
    correct = answered = 0
    reasons = Counter()
    briers, pairs = [], []
    lat_ms, wall_ms = [], []
    cost = held = errors = 0
    for row in rows:
        tmpl = templates.get(row.get("family"))
        kind = tmpl["type"] if tmpl else _infer_type(row.get("gold"))
        if _is_number(row.get("latency_ms")):
            lat_ms.append(row["latency_ms"])
        if _is_number(row.get("wall_ms")):
            wall_ms.append(row["wall_ms"])
        if _is_number(row.get("cost_usd")):
            cost += row["cost_usd"]
        if _is_number(row.get("held_back_fields")):
            held += row["held_back_fields"]
        status = row.get("http_status")
        if status is not None and status != 200:
            errors += 1
        if not is_answered(row):
            reasons[row.get("reason") or "(none)"] += 1
            continue
        answered += 1
        ok = is_correct(row, kind)
        correct += ok
        probs = row.get("probabilities")
        if _valid_probs(probs):
            options = tmpl["options"] if tmpl else sorted(
                set(probs) | {_gold_key(row["gold"], kind)})
            briers.append(brier(probs, _gold_key(row["gold"], kind), options))
            pairs.append((float(max(probs.values())), ok))
    ece_value, bins = ece(pairs)
    ci = wilson(correct, n)
    return {
        "n": n,
        "answered": answered,
        "unanswered": n - answered,
        "unanswered_rate": (n - answered) / n if n else None,
        "unanswered_reasons": dict(sorted(reasons.items())),
        "errors": errors,
        "correct": correct,
        "accuracy": correct / n if n else None,
        "accuracy_ci95": list(ci) if ci else None,
        "scored": len(briers),
        "brier": sum(briers) / len(briers) if briers else None,
        "ece": ece_value,
        "ece_bins": bins,
        "latency_ms": _lat(lat_ms),
        "wall_ms": _lat(wall_ms),
        "cost_usd_total": cost,
        "cost_usd_per_1000": cost / n * 1000 if n else None,
        "held_back_fields": held,
    }


def summarise(rows, templates: dict) -> dict:
    """{"backends": {name: {"overall": stats, "families": {family: stats}}}}.
    Rows are grouped by `backend`; a repeated (backend, id) keeps the last one."""
    latest = {}
    duplicates = Counter()
    for row in rows:
        key = (row.get("backend") or "(unknown)", row.get("id"))
        if key in latest:
            duplicates[key[0]] += 1
        latest[key] = row
    by_backend = defaultdict(list)
    for (backend, _), row in latest.items():
        by_backend[backend].append(row)
    result = {}
    for backend in sorted(by_backend):
        group = by_backend[backend]
        fams = defaultdict(list)
        for row in group:
            fams[row.get("family") or "(unknown)"].append(row)
        result[backend] = {
            "overall": stats(group, templates),
            "families": {f: stats(fams[f], templates) for f in sorted(fams)},
            "duplicate_ids_dropped": duplicates.get(backend, 0),
        }
    return {"backends": result}


def read_results(paths):
    rows, bad = [], 0
    for path in paths:
        for lineno, line in enumerate(Path(path).read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                print(f"metrics: skipped unparsable line {path}:{lineno}", file=sys.stderr)
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows, bad


# ---- text rendering -------------------------------------------------------

def _f(x, fmt="{:.3f}"):
    return "-" if x is None else fmt.format(x)


def _line(label, s):
    ci = s["accuracy_ci95"]
    return [
        label, str(s["n"]), str(s["answered"]),
        _f(s["accuracy"]), "-" if ci is None else f"[{ci[0]:.3f},{ci[1]:.3f}]",
        _f(s["brier"]), _f(s["ece"]),
        _f(s["latency_ms"]["p50"], "{:.0f}") + "/" + _f(s["latency_ms"]["p95"], "{:.0f}"),
        _f(s["wall_ms"]["p50"], "{:.0f}") + "/" + _f(s["wall_ms"]["p95"], "{:.0f}"),
        _f(s["cost_usd_per_1000"], "{:.4f}"),
        _f(s["unanswered_rate"], "{:.1%}"), str(s["held_back_fields"]),
    ]


HEAD = ["scope", "n", "answ", "acc", "acc 95% CI", "brier", "ece",
        "lat p50/p95", "wall p50/p95", "$/1k", "unans", "held"]


def render(summary: dict) -> str:
    out = []
    for backend, blk in summary["backends"].items():
        rows = [HEAD, _line("overall", blk["overall"])]
        rows += [_line(f, s) for f, s in blk["families"].items()]
        widths = [max(len(r[i]) for r in rows) for i in range(len(HEAD))]
        o = blk["overall"]
        out.append(f"== backend: {backend}")
        for i, r in enumerate(rows):
            out.append("  ".join(c.ljust(w) if j == 0 else c.rjust(w)
                                 for j, (c, w) in enumerate(zip(r, widths))))
            if i == 0:
                out.append("  ".join("-" * w for w in widths))
        out.append(f"   scored for brier/ece: {o['scored']} of {o['n']}; "
                   f"unanswered (counted wrong, excluded from brier/ece): {o['unanswered']}; "
                   f"runner/http errors: {o['errors']}; total cost ${o['cost_usd_total']:.4f}")
        if o["unanswered_reasons"]:
            out.append("   unanswered reasons: " + ", ".join(
                f"{k}={v}" for k, v in o["unanswered_reasons"].items()))
        if blk["duplicate_ids_dropped"]:
            out.append(f"   duplicate ids dropped (last kept): {blk['duplicate_ids_dropped']}")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", nargs="?", const="-", default=None, metavar="PATH",
                    help="write machine-readable metrics to PATH ('-' or no value: stdout)")
    ap.add_argument("--templates", default=str(ROOT / "templates"))
    args = ap.parse_args(argv)
    missing = [f for f in args.files if not Path(f).is_file()]
    if missing:
        print("metrics: no such result file: " + ", ".join(missing), file=sys.stderr)
        return 2
    rows, bad = read_results(args.files)
    if not rows:
        print("metrics: measured nothing (no result rows)", file=sys.stderr)
        return 1
    summary = summarise(rows, load_templates(Path(args.templates)))
    summary["meta"] = {"files": list(args.files), "rows": len(rows),
                       "unparsable_lines": bad, "ece_bins": ECE_BINS}
    if args.json == "-":
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        print()
        return 0
    print(render(summary))
    if args.json:
        Path(args.json).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
