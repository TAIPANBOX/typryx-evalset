import random
import unittest
from collections import Counter

from gen.common import split_groups
from tests.helpers import FAMILIES, by_family, disk, disk_rows_with_params


def _splits():
    return {sp: by_family(disk(sp)) for sp in ("train", "dev", "test")}


class Split(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sp = _splits()
        cls.all = by_family(disk("all"))

    def test_the_three_files_partition_all(self):
        lines = {sp: [r["id"] for f in FAMILIES for r in self.sp[sp][f]] for sp in self.sp}
        union = sorted(i for ids in lines.values() for i in ids)
        self.assertEqual(union, sorted(r["id"] for f in FAMILIES for r in self.all[f]))
        self.assertEqual(len(union), len(set(union)))

    def test_proportions_are_about_70_15_15_per_family(self):
        for f in FAMILIES:
            n = len(self.all[f])
            for sp, target in (("train", 0.70), ("dev", 0.15), ("test", 0.15)):
                share = len(self.sp[sp][f]) / n
                self.assertLess(abs(share - target), 0.04, (f, sp, share))

    def test_no_group_appears_in_two_splits(self):
        for f in FAMILIES:
            owner = {}
            for sp in self.sp:
                for g in {r["group"] for r in self.sp[sp][f]}:
                    self.assertNotIn(g, owner, (f, g, owner.get(g), sp))
                    owner[g] = sp

    def test_every_label_appears_in_every_split(self):
        for f in FAMILIES:
            labels = {r["gold"] for r in self.all[f]}
            for sp in self.sp:
                self.assertEqual({r["gold"] for r in self.sp[sp][f]}, labels, (f, sp))

    def test_every_task_kind_appears_in_dev_and_test(self):
        kinds = {}
        for row, p in disk_rows_with_params("eval.outcome_met"):
            kinds[row["id"]] = p["kind"]
        for sp in ("train", "dev", "test"):
            got = {kinds[r["id"]] for r in self.sp[sp]["eval.outcome_met"]}
            self.assertEqual(len(got), 10, sp)

    def test_every_split_has_groups_it_alone_holds(self):
        # the point of the split: dev and test hold phrasings train never showed
        for f in FAMILIES:
            train = {r["group"] for r in self.sp["train"][f]}
            for sp in ("dev", "test"):
                held = {r["group"] for r in self.sp[sp][f]}
                self.assertTrue(held and not (held & train), (f, sp))


class Splitter(unittest.TestCase):
    def test_a_group_is_assigned_once_and_every_group_is_assigned(self):
        strata = {"a": [f"a{i}" for i in range(14)], "b": [f"b{i}" for i in range(10)]}
        out = split_groups(random.Random(1), strata)
        self.assertEqual(sorted(out), sorted(g for gs in strata.values() for g in gs))
        for name, gs in strata.items():
            c = Counter(out[g] for g in gs)
            self.assertEqual(set(c), {"train", "dev", "test"}, name)

    def test_the_split_is_about_70_15_15_by_groups(self):
        strata = {"x": [f"g{i}" for i in range(20)]}
        c = Counter(split_groups(random.Random(3), strata).values())
        self.assertEqual((c["train"], c["dev"], c["test"]), (14, 3, 3))

    def test_too_few_groups_refuse_rather_than_leak(self):
        with self.assertRaises(ValueError):
            split_groups(random.Random(1), {"x": ["g1", "g2"]})


if __name__ == "__main__":
    unittest.main()
