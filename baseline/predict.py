"""Write one of the two no-model baselines' predictions for a split.

    python3 -m baseline.predict --which constant|rules --split dev|test --out results/NAME.jsonl

Output rows have the same shape the benchmark runner writes. The test split is
refused unless data/test.jsonl still matches the sha256 frozen in
data/MANIFEST.json.
"""
import argparse
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from baseline.constant import ROOT, Constant, label_order, load_jsonl, load_templates  # noqa: E402
from baseline.rules import Rules  # noqa: E402

MODELS = {"constant": "constant-v1", "rules": "rules-v1"}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_frozen(root, split):
    """Refuse the test split unless it is byte-identical to the frozen one."""
    if split != "test":
        return
    path = os.path.join(root, "data", "test.jsonl")
    with open(os.path.join(root, "data", "MANIFEST.json"), encoding="utf-8") as fh:
        want = json.load(fh)["files"]["test.jsonl"]["sha256"]
    if not os.path.exists(path) or sha256_of(path) != want:
        raise SystemExit("refusing --split test: data/test.jsonl does not match the sha256 in data/MANIFEST.json")


def shape(template, label):
    """(answer, probabilities) for a one-hot prediction, in the runner's shape."""
    order = label_order(template)
    if template["type"] == "noul":
        return (1.0 if label else 0.0), {"true": 1.0 if label else 0.0, "false": 0.0 if label else 1.0}
    return label, {str(lab): 1.0 if lab == label else 0.0 for lab in order}


def run(which, split, out, root=ROOT):
    check_frozen(root, split)
    templates = load_templates(root)
    if which == "constant":
        model = Constant(load_jsonl(os.path.join(root, "data", "train.jsonl")), templates)
    else:
        model = Rules()
    rows = load_jsonl(os.path.join(root, "data", split + ".jsonl"))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        for r in rows:
            t0 = time.perf_counter()
            label = model.predict(r["family"], r["state"])
            t1 = time.perf_counter()
            answer, probs = shape(templates[r["family"]], label)
            line = {"id": r["id"], "family": r["family"], "gold": r["gold"], "answer": answer,
                    "probabilities": probs, "unanswered": False, "reason": None, "backend": which,
                    "model": MODELS[which], "latency_ms": int((t1 - t0) * 1000), "wall_ms": 0,
                    "cost_usd": 0, "held_back_fields": 0, "http_status": None}
            line["wall_ms"] = int((time.perf_counter() - t0) * 1000)
            fh.write(json.dumps(line) + "\n")
    return len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--which", choices=sorted(MODELS), required=True)
    ap.add_argument("--split", choices=("dev", "test"), required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    n = run(a.which, a.split, a.out)
    print(f"wrote {n} rows to {a.out}")


if __name__ == "__main__":
    main()
