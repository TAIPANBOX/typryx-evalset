"""Baseline 1, "no model": what the stack does today without typryx.

For every family it always answers the most frequent gold label in train.jsonl.
Ties go to the first option in the template's criteria order (for score
templates, the lowest index; for noul, "true" before "false").
"""
import collections
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_templates(root=ROOT):
    """family id -> template dict, from templates/*.json."""
    out = {}
    tdir = os.path.join(root, "templates")
    for name in sorted(os.listdir(tdir)):
        if name.endswith(".json"):
            with open(os.path.join(tdir, name), encoding="utf-8") as fh:
                t = json.load(fh)
            out[t["id"]] = t
    return out


def label_order(template):
    """The labels of a template in criteria order, as gold values."""
    if template["type"] == "noul":
        return [k == "true" for k in template["criteria"]]
    if template["type"] == "score":
        return list(range(len(template["criteria"])))
    return list(template["criteria"])


def majority(train_rows, templates):
    """family -> most frequent gold label in train (ties: criteria order)."""
    counts = collections.defaultdict(collections.Counter)
    for r in train_rows:
        counts[r["family"]][r["gold"]] += 1
    out = {}
    for fam, tpl in templates.items():
        order = label_order(tpl)
        c = counts[fam]
        out[fam] = max(order, key=lambda lab: (c[lab], -order.index(lab)))
    return out


class Constant:
    def __init__(self, train_rows, templates):
        self.labels = majority(train_rows, templates)

    def predict(self, family, state):
        return self.labels[family]
