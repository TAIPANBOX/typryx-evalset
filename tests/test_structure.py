import hashlib
import json
import unittest
from collections import Counter

from gen import build as B
from gen.common import DISTRACTOR_NAMES
from tests.helpers import FAMILIES, TEMPLATES, built, by_family, disk, manifest, template

ROW_KEYS = {"id", "family", "template", "state", "gold", "group", "source"}

#: sha256 of the four templates copied verbatim from typryx/examples/templates.
VERBATIM = {
    "eval.answer_quality": "19c104db19e397cbb6e79b25df71cba71243a494a630b90fd5f526d3e54220c9",
    "eval.outcome_met": "a9ee2bd20e79e0abeb2311172ec675efe75ed952807ae2b0aaaab12f45724a42",
    "request.complexity": "9a486d4e31849044d790ea1ab36bb2fb235aa9c7a46110a851f284f14bb5c5c6",
    "triage.anomaly_class": "dbd6a47954348f067a3b90a1c8b7225f02a9c71876642a5a74052e06a276579c",
}

EXPECTED_LABELS = {
    "request.complexity": {k: 125 for k in ("cheap", "default", "hard", "reasoning")},
    "triage.anomaly_class": {k: 100 for k in ("expected_growth", "runaway_agent", "misconfiguration", "price_change", "unknown")},
    "eval.outcome_met": {True: 250, False: 250},
    "eval.answer_quality": {0: 125, 1: 125, 2: 125, 3: 125},
    "action.risk_class": {k: 100 for k in ("read_only", "reversible_change", "destructive", "external_send", "financial")},
    "console.question_topic": {k: 100 for k in ("spend", "incident", "identity", "approval", "other")},
}


class Templates(unittest.TestCase):
    def test_six_templates_exist_and_the_four_examples_are_verbatim(self):
        files = sorted(p.name for p in TEMPLATES.glob("*.json"))
        self.assertEqual(files, sorted(f"{f}.json" for f in FAMILIES))
        for tid, digest in VERBATIM.items():
            self.assertEqual(hashlib.sha256((TEMPLATES / f"{tid}.json").read_bytes()).hexdigest(), digest, tid)

    def test_template_shape(self):
        for f in FAMILIES:
            t = template(f)
            self.assertEqual(t["id"], f)
            self.assertIn(t["type"], ("choice", "score", "noul"))
            self.assertEqual(t["max_state_bytes"], 16384)
            self.assertTrue(t["fields"])


class Rows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = disk("all")
        cls.fam = by_family(cls.rows)

    def test_three_thousand_rows_five_hundred_per_family(self):
        self.assertEqual(len(self.rows), 3000)
        for f in FAMILIES:
            self.assertEqual(len(self.fam[f]), 500, f)

    def test_row_keys_are_exactly_the_spec(self):
        for r in self.rows:
            self.assertEqual(set(r), ROW_KEYS, r["id"])
            self.assertEqual(r["source"], "construct")
            self.assertEqual(r["template"], r["family"])

    def test_ids_are_unique(self):
        ids = [r["id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))

    def test_balance_per_family_and_label(self):
        for f, want in EXPECTED_LABELS.items():
            got = Counter(r["gold"] for r in self.fam[f])
            self.assertEqual(dict(got), want, f)

    def test_outcome_met_is_balanced_per_task_kind(self):
        from tests.helpers import disk_rows_with_params
        per = Counter()
        for row, p in disk_rows_with_params("eval.outcome_met"):
            per[(p["kind"], row["gold"])] += 1
        kinds = sorted({k for k, _ in per})
        self.assertEqual(len(kinds), 10)
        for k in kinds:
            self.assertEqual((per[(k, True)], per[(k, False)]), (25, 25), k)

    def test_every_gold_is_valid_for_its_template(self):
        for f in FAMILIES:
            t = template(f)
            for r in self.fam[f]:
                g = r["gold"]
                if t["type"] == "choice":
                    self.assertIsInstance(g, str)
                    self.assertIn(g, t["criteria"], r["id"])
                elif t["type"] == "score":
                    self.assertIs(type(g), int, r["id"])
                    self.assertTrue(0 <= g < len(t["criteria"]), r["id"])
                else:
                    self.assertIs(type(g), bool, r["id"])

    def test_state_is_the_templates_fields_plus_at_most_one_distractor(self):
        for f in FAMILIES:
            fields = set(template(f)["fields"])
            for r in self.fam[f]:
                extra = set(r["state"]) - fields
                self.assertTrue(fields <= set(r["state"]), r["id"])
                self.assertLessEqual(len(extra), 1, r["id"])
                self.assertTrue(extra <= set(DISTRACTOR_NAMES), r["id"])
                for k, v in r["state"].items():
                    self.assertIsInstance(v, str, (r["id"], k))
                    self.assertTrue(v.strip(), (r["id"], k))
                self.assertLess(len(json.dumps(r["state"]).encode()), template(f)["max_state_bytes"], r["id"])

    def test_distractor_rate_is_15_to_25_percent_overall_and_per_label(self):
        for f in FAMILIES:
            fields = set(template(f)["fields"])
            rate = sum(1 for r in self.fam[f] if set(r["state"]) - fields) / 500
            self.assertTrue(0.15 <= rate <= 0.25, (f, rate))
            for label in {r["gold"] for r in self.fam[f]}:
                rows = [r for r in self.fam[f] if r["gold"] == label]
                lr = sum(1 for r in rows if set(r["state"]) - fields) / len(rows)
                self.assertTrue(0.15 <= lr <= 0.25, (f, label, lr))

    def test_at_least_twenty_groups_per_family_each_with_rows(self):
        for f in FAMILIES:
            groups = Counter(r["group"] for r in self.fam[f])
            self.assertGreaterEqual(len(groups), 20, f)
            self.assertTrue(all(n >= 1 for n in groups.values()))

    def test_no_two_rows_in_a_family_ask_the_same_thing(self):
        for f in FAMILIES:
            fields = template(f)["fields"]
            seen = Counter(tuple(r["state"][k] for k in fields) for r in self.fam[f])
            dup = [k for k, n in seen.items() if n > 1]
            self.assertEqual(dup, [], f)

    def test_manifest_counts_agree_with_the_rows(self):
        m = manifest()
        self.assertEqual(m["rows"], 3000)
        for f in FAMILIES:
            self.assertEqual(m["families"][f]["rows"], 500)
            total = Counter()
            for sp, c in m["families"][f]["counts"].items():
                total.update(c)
            want = Counter(r["gold"] if isinstance(r["gold"], str) else json.dumps(r["gold"]) for r in self.fam[f])
            self.assertEqual(dict(total), dict(want), f)


if __name__ == "__main__":
    unittest.main()
