"""Labels by construction: every gold is recomputed from the row itself, or
from the generator's own parameters for the row, by rules written HERE and
not imported from the generators. Families 2, 3 and 5 are recomputed fully;
families 1, 4 and 6 by the construction rule the spec gives for them.

scripts/labels-by-construction.sh runs exactly this module.
"""

import datetime
import json
import random
import re
import unittest
from fractions import Fraction

from gen import quality, triage
from tests.helpers import disk_rows_with_params


# ============================================================ 1 request.complexity

REASONING_CUE = re.compile(
    r"\b(prove|proof|derive|derivation|step by step|step-by-step|rigorous\w*|formal\w*|every step|each step|carefully|induction|invariant)\b",
    re.I,
)


class Complexity(unittest.TestCase):
    def test_reasoning_cue_if_and_only_if_reasoning(self):
        rows = disk_rows_with_params("request.complexity")
        self.assertEqual(len(rows), 500)
        for row, p in rows:
            has = bool(REASONING_CUE.search(row["state"]["prompt"]))
            self.assertEqual(has, row["gold"] == "reasoning", (row["id"], row["gold"], row["state"]["prompt"][:80]))

    def test_group_carries_its_class(self):
        for row, p in disk_rows_with_params("request.complexity"):
            self.assertEqual(row["group"].split(".")[1], row["gold"], row["id"])

    def test_cheap_prompts_are_short_and_hard_prompts_are_not_one_liners(self):
        for row, p in disk_rows_with_params("request.complexity"):
            words = len(row["state"]["prompt"].split())
            if row["gold"] == "cheap":
                self.assertLessEqual(words, 45, row["id"])
            if row["gold"] == "hard":
                self.assertGreaterEqual(words, 15, row["id"])


# ============================================================ 2 triage.anomaly_class

SETTINGS = {"cache_disabled", "max_tokens_raised", "model_route_changed", "quota_raised", "rate_limit_removed", "context_cap_raised"}


def ref_classify(p):
    """The spec's clear-cut rules, each written as a list of requirements
    (every one must hold), independent of gen.triage.classify. Returns None
    for a parameter set no rule covers."""
    calls, traffic, unique, price, event = p["calls"], p["traffic"], p["unique"], p["price"], p["event"]
    stated = lambda v: v is not None
    within = lambda v, n: abs(v) <= n
    no_setting = event in ("none", "noise")
    matches = []
    if event in SETTINGS:
        if all([calls is None or within(calls, 10), traffic is None or within(traffic, 10),
                price is None or within(price, 5), unique is None or unique >= 40]):
            matches.append("misconfiguration")
    elif no_setting:
        if not any(stated(v) for v in (calls, traffic, unique, price)):
            matches.append("unknown")
        if all([stated(calls), stated(traffic), stated(price)]) and all([
                calls >= 20, traffic >= 20, abs(calls - traffic) <= 10, within(price, 5), unique is None or unique >= 50]):
            matches.append("expected_growth")
        if stated(calls) and stated(unique) and stated(price) and unique <= 25 and within(price, 5):
            if stated(traffic):
                if calls >= 100 and calls >= 3 * max(traffic, 0):
                    matches.append("runaway_agent")
            elif calls >= 400:
                matches.append("runaway_agent")
        if all([stated(calls), stated(traffic), stated(price)]) and all([
                within(calls, 10), within(traffic, 10), price >= 15, unique is None or unique >= 40]):
            matches.append("price_change")
    assert len(matches) <= 1, (p, matches)      # the rules never overlap
    return matches[0] if matches else None


#: Hand-written truth table: (calls, traffic, unique, price, event) -> class or None (not clear-cut, never generated).
#: Rows named tri-... are the rows the blind re-labels disputed, by content.
TRUTH = [
    ((1400, None, 18, 0, "none"), "runaway_agent"),          # tri-0022: 15x calls, 18% distinct, no traffic figure
    ((465, 4, 13, 21, "none"), None),                        # tri-0252: repeats AND a +21% price: two causes, not clear-cut
    ((454, 3, 10, 31, "none"), None),                        # tri-0436: likewise a +31% price
    ((454, 3, 10, 3, "none"), "runaway_agent"),
    ((21, 18, 44, 0, "none"), None),                         # tri-0185: growth numbers but only 44% distinct: not clear-cut
    ((141, 134, 7, 0, "none"), None),                        # tri-0287: growth numbers with 93% repeats: contradictory
    ((26, None, None, None, "none"), None),                  # tri-0311: +26% requests, no traffic figure
    ((76, 76, 80, 0, "model_route_changed"), None),          # tri-0315: model swap plus growth: mixed
    ((None, 245, None, None, "none"), None),                 # tri-0316: sessions up, no call counts
    ((None, None, None, None, "rate_limit_removed"), "misconfiguration"),    # tri-0106
    ((None, None, 69, 4, "model_route_changed"), "misconfiguration"),         # tri-0404
    ((None, None, None, None, "context_cap_raised"), "misconfiguration"),     # tri-0467
    ((2, None, None, 2, "cache_disabled"), "misconfiguration"),               # tri-0231
    ((3, 0, 80, 0, "quota_raised"), "misconfiguration"),                      # tri-0263: intentional counts
    ((50, 0, 80, 0, "quota_raised"), None),                  # a setting change AND calls up
    ((0, 0, 80, 40, "cache_disabled"), None),                # a setting change AND a price rise
    ((0, 0, 20, 0, "cache_disabled"), None),                 # a setting change, but prompts are mostly repeats
    ((60, 62, 80, 1, "none"), "expected_growth"),
    ((60, 62, None, 1, "noise"), "expected_growth"),
    ((60, 90, 80, 1, "none"), None),                         # calls and traffic 30 points apart
    ((60, 62, 80, 1, "model_route_changed"), None),
    ((60, 62, 80, 30, "none"), None),                        # growth and a price rise
    ((150, 0, 10, 0, "none"), "runaway_agent"),
    ((150, 0, 10, 0, "agent_deploy"), None),                 # deploys are not generated
    ((150, 0, 60, 0, "none"), None),                         # extra calls but diverse prompts
    ((150, 60, 10, 0, "none"), None),                        # calls not 3x traffic growth
    ((300, None, 10, 0, "none"), None),                      # 4x with no traffic figure: below the 5x bar
    ((400, None, 10, 0, "none"), "runaway_agent"),
    ((3, 2, 70, 40, "none"), "price_change"),
    ((3, 2, None, 40, "none"), "price_change"),
    ((3, 2, 70, 10, "none"), None),                          # price up only 10
    ((3, 40, 70, 40, "none"), None),
    ((3, 2, 70, None, "none"), None),
    ((None, None, None, None, "none"), "unknown"),
    ((None, None, None, None, "noise"), "unknown"),
    ((None, None, 70, None, "noise"), None),                 # one figure stated: not the no-information case
]


class Triage(unittest.TestCase):
    def test_truth_table_holds_for_reference_and_generator(self):
        for (c, t, u, pr, e), want in TRUTH:
            p = {"spend": 100, "calls": c, "traffic": t, "unique": u, "price": pr, "event": e}
            self.assertEqual(ref_classify(p), want, p)
            self.assertEqual(triage.classify(p), want, p)

    def test_every_setting_event_can_be_the_cause(self):
        # the tri-0231 class of bug: a setting event left off a list, or needing evidence the verdict does not need
        for ev in triage.SETTING_EVENTS:
            for c, t, u, pr in ((2, None, None, 2), (None, None, None, None), (0, 3, 70, 0)):
                p = {"spend": 300, "calls": c, "traffic": t, "unique": u, "price": pr, "event": ev}
                self.assertEqual(triage.classify(p), "misconfiguration", p)
                self.assertEqual(ref_classify(p), "misconfiguration", p)
        self.assertEqual(set(triage.SETTING_EVENTS), SETTINGS)

    def test_generator_classifier_agrees_with_the_reference_on_a_sweep(self):
        rng = random.Random(99)
        vals = [None, -30, -10, -5, -4, 0, 4, 5, 6, 10, 11, 15, 19, 20, 21, 35, 60, 99, 100, 150, 299, 300, 399, 400, 900]
        uvals = [None, 0, 10, 25, 26, 39, 40, 49, 50, 90]
        labelled = 0
        for _ in range(60000):
            p = {"spend": 100, "calls": rng.choice(vals), "traffic": rng.choice(vals), "unique": rng.choice(uvals),
                 "price": rng.choice(vals), "event": rng.choice(triage.ALL_EVENTS + ["agent_deploy"])}
            want = ref_classify(p)
            labelled += want is not None
            self.assertEqual(triage.classify(p), want, p)
        self.assertGreater(labelled, 500)

    def test_every_row_gold_is_the_label_of_its_parameters(self):
        rows = disk_rows_with_params("triage.anomaly_class")
        self.assertEqual(len(rows), 500)
        for row, p in rows:
            self.assertEqual(ref_classify(p), row["gold"], (row["id"], p))      # never None: no row is outside the rules

    def test_rows_sit_well_inside_their_class(self):
        """A clear-cut benchmark: every stated figure is comfortably clear of its threshold."""
        for row, p in disk_rows_with_params("triage.anomaly_class"):
            c, t, u, pr, g = p["calls"], p["traffic"], p["unique"], p["price"], row["gold"]
            rid = row["id"]
            if g == "expected_growth":
                self.assertTrue(t >= 30 and abs(c - t) <= 6 and abs(pr) <= 3 and (u is None or u >= 58), rid)
            elif g == "runaway_agent":
                self.assertTrue(u <= 18 and abs(pr) <= 3, rid)
                self.assertTrue(c >= 150 if t is not None else c >= 450, rid)
                self.assertTrue(t is None or abs(t) <= 8, rid)
            elif g == "price_change":
                self.assertTrue(pr >= 25 and abs(c) <= 6 and abs(t) <= 6 and (u is None or u >= 55), rid)
            elif g == "misconfiguration":
                self.assertIn(p["event"], SETTINGS, rid)
                for v, lim in ((c, 6), (t, 6), (pr, 3)):
                    self.assertTrue(v is None or abs(v) <= lim, rid)
                self.assertTrue(u is None or u >= 55, rid)
            else:
                self.assertEqual((c, t, u, pr), (None, None, None, None), rid)
                self.assertIn(p["event"], ("none", "noise"), rid)

    def test_every_class_shows_up_in_its_varieties(self):
        rows = disk_rows_with_params("triage.anomaly_class")
        by = {lab: [p for r, p in rows if r["gold"] == lab] for lab in triage.LABELS}
        self.assertTrue(any(p["traffic"] is None for p in by["runaway_agent"]))
        self.assertTrue(any(p["traffic"] is not None for p in by["runaway_agent"]))
        self.assertEqual({p["event"] for p in by["misconfiguration"]}, SETTINGS)
        self.assertTrue(any(p["calls"] is None for p in by["misconfiguration"]))
        self.assertTrue(any(p["calls"] is not None for p in by["misconfiguration"]))
        self.assertEqual({p["event"] for p in by["unknown"]}, {"none", "noise"})

    def test_the_headline_spend_reconciles_with_the_shown_calls_and_price(self):
        for row, p in disk_rows_with_params("triage.anomaly_class"):
            if row["gold"] == "unknown" or p["calls"] is None or p["price"] is None:
                continue
            implied = round(100 * ((1 + p["calls"] / 100) * (1 + p["price"] / 100) - 1))
            if row["gold"] == "misconfiguration":
                self.assertGreaterEqual(p["spend"], implied, row["id"])       # per-call cost rose too
            else:
                self.assertEqual(p["spend"], implied, row["id"])

    SURFACE_EVENT = {
        "cache_disabled": r"cach",
        "max_tokens_raised": r"max_tokens|token limit|completion cap",
        "model_route_changed": None,  # names the model pair, checked below
        "quota_raised": r"quota",
        "rate_limit_removed": r"rate limit|throttle|per-minute cap",
        "context_cap_raised": r"context window|token prompts|truncation",
    }

    def test_the_rendered_text_carries_what_the_parameters_say(self):
        """A row whose text disagreed with its parameters would carry a label
        the reader cannot derive. Check the text mentions each known number,
        and the event."""
        for row, p in disk_rows_with_params("triage.anomaly_class"):
            text = row["state"]["anomaly"] + " " + row["state"]["recent_changes"]
            self.assertIn(p["project"], text, row["id"])
            for sig in ("spend", "calls", "traffic", "price"):
                v = p[sig]
                if v is None:
                    continue
                forms = [str(abs(v)), f"{1 + v / 100:.1f}x"]
                if sig == "calls":
                    forms += [_human(round(p["base_calls"] * (1 + v / 100)))]
                if sig == "spend":
                    forms += [f"{round(p['base_cost'] * (1 + v / 100)):,}"]
                if sig == "price":
                    forms += [f"{p['base_price'] * (1 + v / 100):.2f}"]
                    if abs(v) <= 4:
                        forms += ["has not changed"]
                if sig == "traffic" and abs(v) <= 10:
                    forms += ["has not really moved", "about the same"]
                self.assertTrue(any(f in text for f in forms), (row["id"], sig, v, text))
            if p["unique"] is not None:
                u = p["unique"]
                forms = [f"{u}%", f"{u / 100:.2f}", f"{100 - u}%"]
                self.assertTrue(any(f in text for f in forms), (row["id"], "unique", u, text))
            ev = p["event"]
            if ev in self.SURFACE_EVENT and self.SURFACE_EVENT[ev]:
                self.assertRegex(text, re.compile(self.SURFACE_EVENT[ev], re.I), (row["id"], ev))
            if ev == "model_route_changed":
                self.assertIn(p["big"], text, row["id"])
            if ev == "agent_deploy":
                self.assertRegex(text, r"(?i)agent v|planner build|code release|deployed", row["id"])
            if ev == "none":
                self.assertRegex(text, r"(?i)no deploys|empty|nothing|no releases|Deploy history", row["id"])


def _human(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


# ============================================================ 3 eval.outcome_met

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
#: unit -> unit multipliers, from the tables in a physics or cooking textbook.
UNIT = {
    ("kilometres", "metres"): Fraction(1000), ("hours", "minutes"): Fraction(60), ("minutes", "seconds"): Fraction(60),
    ("days", "hours"): Fraction(24), ("weeks", "days"): Fraction(7), ("feet", "inches"): Fraction(12), ("yards", "feet"): Fraction(3),
    ("pounds", "ounces"): Fraction(16), ("kilograms", "grams"): Fraction(1000), ("litres", "millilitres"): Fraction(1000),
    ("gallons", "quarts"): Fraction(4), ("miles", "feet"): Fraction(5280), ("metres", "centimetres"): Fraction(100),
    ("metres", "kilometres"): Fraction(1, 1000), ("seconds", "minutes"): Fraction(1, 60), ("ounces", "pounds"): Fraction(1, 16),
    ("hours", "days"): Fraction(1, 24), ("inches", "feet"): Fraction(1, 12), ("grams", "kilograms"): Fraction(1, 1000),
    ("millilitres", "litres"): Fraction(1, 1000), ("days", "weeks"): Fraction(1, 7), ("quarts", "gallons"): Fraction(1, 4),
}
CATEGORIES = {
    "fruits": {"apple", "banana", "cherry", "mango", "pear", "plum", "grape", "peach", "lemon", "fig"},
    "animals": {"otter", "heron", "lynx", "badger", "falcon", "gecko", "moose", "tapir", "viper", "whale"},
    "colours": {"crimson", "teal", "amber", "violet", "indigo", "ochre", "scarlet", "olive", "azure", "coral"},
    "services": {"nginx", "redis", "postgres", "kafka", "grafana", "vault", "etcd", "envoy", "consul", "prometheus"},
    "tools": {"hammer", "wrench", "chisel", "pliers", "spanner", "mallet", "drill", "saw", "level", "clamp"},
}


def _num(f: Fraction) -> str:
    if f.denominator == 1:
        return str(f.numerator)
    from decimal import Decimal
    return format((Decimal(f.numerator) / Decimal(f.denominator)).quantize(Decimal("0.001")).normalize(), "f")


def last_int(text: str):
    m = re.findall(r"-?\d+", text)
    return int(m[-1]) if m else None


class Outcome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = disk_rows_with_params("eval.outcome_met")

    def test_arithmetic_is_recomputed_from_the_text_alone(self):
        n = 0
        for row, p in self.rows:
            if p["kind"] not in ("add", "sub", "mul"):
                continue
            n += 1
            nums = [int(x) for x in re.findall(r"\d+", row["state"]["task"])]
            self.assertEqual(len(nums), 2, row["id"])
            want = {"add": sum(nums), "sub": max(nums) - min(nums), "mul": nums[0] * nums[1]}[p["kind"]]
            stated = last_int(row["state"]["final_answer"])
            self.assertEqual(stated == want, row["gold"], (row["id"], row["state"]))
        self.assertEqual(n, 150)

    def test_every_kind_is_recomputed_from_its_parameters(self):
        for row, p in self.rows:
            kind, given = p["kind"], p["given"]
            if kind == "add":
                right = str(p["a"] + p["b"])
            elif kind == "sub":
                right = str(p["a"] - p["b"])
            elif kind == "mul":
                right = str(p["a"] * p["b"])
            elif kind == "unit":
                right = _num(Fraction(p["v"]) * UNIT[(p["frm"], p["to"])]) if "." not in p["v"] else _num(Fraction(p["v"]) * UNIT[(p["frm"], p["to"])])
            elif kind == "weekday":
                right = WEEKDAYS[datetime.date.fromisoformat(p["iso"]).weekday()]
            elif kind == "count":
                items = p["items"]
                right = str(sum(1 for i in items if i in CATEGORIES[p["cat"]]) if p["category_mode"] else len(items))
            elif kind == "reverse":
                right = p["w"][::-1]
            elif kind == "upper":
                right = p["w"].upper()
            elif kind == "letters":
                right = str(p["w"].count(p["l"]))
            elif kind == "sort":
                items = p["items"]
                right = p["sep"].join(sorted(items, key=(int if p["mode"].startswith("num") else str), reverse=(p["mode"] == "num_desc")))
            else:
                self.fail(kind)
            self.assertEqual(p["right"], right, (row["id"], kind))
            self.assertEqual(given == right, row["gold"], (row["id"], kind, given, right))
            self.assertIn(given, row["state"]["final_answer"], row["id"])

    def test_the_task_states_what_the_parameters_say(self):
        for row, p in self.rows:
            task = row["state"]["task"]
            for key in ("a", "b", "w", "l", "date", "lst"):
                if key in p:
                    self.assertIn(str(p[key]), task, (row["id"], key))
            if p["kind"] == "unit":
                for key in ("v", "frm", "to"):
                    self.assertIn(p[key], task, (row["id"], key))

    def test_near_misses_differ_from_the_right_answer(self):
        falses = 0
        for row, p in self.rows:
            if row["gold"] is False:
                falses += 1
                self.assertNotEqual(p["given"], p["right"], row["id"])
            else:
                self.assertEqual(p["given"], p["right"], row["id"])
        self.assertEqual(falses, 250)

    def test_sort_and_reverse_near_misses_are_really_different_strings(self):
        for row, p in self.rows:
            if p["kind"] in ("sort", "reverse", "upper") and row["gold"] is False:
                self.assertNotEqual(p["given"].lower().replace(",", "").split(), p["right"].lower().replace(",", "").split()
                                    if p["kind"] == "sort" else ["x"], row["id"])
                self.assertNotEqual(p["given"], p["right"])


# ============================================================ 4 eval.answer_quality

NUMBER_WORDS = {"three": 3, "four": 4, "five": 5}


def asked_count(task: str) -> int:
    for w, n in NUMBER_WORDS.items():
        if re.search(rf"\b{w}\b", task):
            return n
    raise AssertionError(task)


def reference_level(n: int, clear: int, vague: int) -> int:
    """A reader's share-of-the-task rule, from the counts found in the text.
    Defects = missing + vague. 3: none. 2: one defect, and N >= 4 or (N = 3
    and the defect is a vague item). 1: a correct item but more defects.
    0: nothing of the topic at all."""
    if clear == 0 and vague == 0:
        return 0
    missing = n - clear - vague
    if clear < 1 or missing < 0:
        raise AssertionError((n, clear, vague))
    defects = missing + vague
    if defects == 0:
        return 3
    if defects == 1:
        if n >= 4:
            return 2
        return 2 if vague == 1 else 1
    return 1


class Quality(unittest.TestCase):
    def test_the_fact_banks_do_not_overlap(self):
        for slug, _, bank in quality.TOPICS:
            texts = [t.lower() for pair in bank for t in pair]
            for i, a in enumerate(texts):
                for j, b in enumerate(texts):
                    if i != j:
                        self.assertNotIn(a, b, (slug, a, b))

    def test_level_is_recomputed_from_the_text_by_counting_the_topics_facts(self):
        topics = {f"aq.{slug}": bank for slug, _, bank in quality.TOPICS}
        rows = disk_rows_with_params("eval.answer_quality")
        self.assertEqual(len(rows), 500)
        for row, p in rows:
            ans = row["state"]["final_answer"].lower()
            bank = topics[row["group"]]
            clear = sum(1 for c, _ in bank if c.lower() in ans)
            vague = sum(1 for _, v in bank if v.lower() in ans)
            n = asked_count(row["state"]["task"])
            self.assertEqual(reference_level(n, clear, vague), row["gold"], (row["id"], n, clear, vague))

    def test_generator_parameters_give_the_same_level(self):
        for row, p in disk_rows_with_params("eval.answer_quality"):
            self.assertEqual(quality.level_of(p["n"], p["clear"], p["vague"], p["offtopic"]), row["gold"], row["id"])

    #: (asked, clear, vague) -> level: the principal's blind-read cases and the edges of the rule.
    LEVELS = [
        ((5, 5, 0), 3), ((3, 3, 0), 3),
        ((5, 4, 0), 2), ((4, 3, 0), 2),            # one of four/five missing: still level 2
        ((5, 4, 1), 2), ((4, 3, 1), 2), ((3, 2, 1), 2),   # one vague, nothing missing
        ((3, 2, 0), 1),                            # two of three given: a third of the task missing
        ((4, 2, 0), 1), ((5, 3, 0), 1), ((3, 1, 0), 1),  # half or less given
        ((4, 2, 2), 1), ((3, 1, 2), 1), ((4, 2, 1), 1),  # two defects
    ]

    def test_level_table_holds_for_reference_and_generator(self):
        for (n, c, v), want in self.LEVELS:
            self.assertEqual(reference_level(n, c, v), want, (n, c, v))
            self.assertEqual(quality.level_of(n, c, v, False), want, (n, c, v))

    def test_three_of_four_is_level_two_and_two_of_three_is_level_one(self):
        # the blind re-label's rows: aq-0056 (4 of 5), aq-0126, aq-0177, aq-0363 (3 of 4), aq-0385 (4 of 5) are 2
        for n, c in ((5, 4), (4, 3)):
            self.assertEqual(quality.level_of(n, c, 0, False), 2)
        self.assertEqual(quality.level_of(3, 2, 0, False), 1)
        for row, p in disk_rows_with_params("eval.answer_quality"):
            if p["offtopic"]:
                continue
            defects = p["n"] - p["clear"]
            if row["gold"] == 3:
                self.assertEqual(defects, 0, row["id"])
            elif row["gold"] == 2:
                self.assertEqual(defects, 1, row["id"])
                self.assertTrue(p["n"] >= 4 or p["vague"] == 1, row["id"])
            elif row["gold"] == 1:
                self.assertGreaterEqual(p["clear"], 1, row["id"])
                self.assertTrue(defects >= 2 or (defects == 1 and p["n"] == 3 and p["vague"] == 0), row["id"])

    def test_level_rule_rejects_what_the_spec_does_not_define(self):
        with self.assertRaises(ValueError):
            quality.level_of(4, 0, 2, False)      # nothing correct, not off-topic
        with self.assertRaises(ValueError):
            quality.level_of(3, 2, 2, False)      # more items than asked
        with self.assertRaises(ValueError):
            quality.level_of(5, 1, 3, False)      # three vague

    def test_word_count_does_not_track_the_level(self):
        rows = disk_rows_with_params("eval.answer_quality")
        means = {}
        for lvl in range(4):
            ws = [len(r["state"]["final_answer"].split()) for r, _ in rows if r["gold"] == lvl]
            means[lvl] = sum(ws) / len(ws)
        self.assertLess(max(means.values()) - min(means.values()), 12, means)


# ============================================================ 5 action.risk_class

READ_VERBS = {"get", "list", "read", "search", "describe", "fetch", "view", "tail", "diff", "status", "inspect", "check", "retrieve", "query", "plan"}
DESTRUCTIVE_VERBS = {"delete", "drop", "truncate", "terminate", "destroy", "purge", "overwrite", "force", "empty", "revoke"}
REVERSIBLE_VERBS = {"create", "add", "set", "update", "scale", "annotate", "rename", "assign", "transition", "acknowledge", "mute",
                    "cordon", "stop", "enable", "start", "post", "snooze", "tag", "pause", "resume"}
EXTERNAL_VERBS = {"send", "forward", "publish", "share"}
EXTERNAL_MARKERS = ("external", "shared_channel", "public", "partner", "third_party")
FINANCIAL_NOUNS = ("refund", "charge", "payout", "transfer", "subscription", "savings_plan", "reserved_instances", "credit",
                   "purchase", "pay_bill", "pay_invoice", "top_up", "buy")


def ref_risk(tool: str, arguments: str, target: str) -> str:
    service, op = tool.split(".", 1)
    if tool == "db.run_query":
        first = json.loads(arguments)["sql"].split()[0].upper()
        return {"SELECT": "read_only", "EXPLAIN": "read_only", "SHOW": "read_only", "CREATE": "reversible_change",
                "DROP": "destructive", "TRUNCATE": "destructive", "DELETE": "destructive"}[first]
    if tool == "shell.exec":
        cmd = json.loads(arguments)["command"]
        first = cmd.split()[0]
        if first == "curl":
            return "external_send"
        if first in ("ls", "cat", "df", "du", "ps", "tail", "head", "grep", "uptime", "stat"):
            return "read_only"
        if first in ("mkdir", "touch", "cp"):
            return "reversible_change"
        if first in ("rm", "dd", "mkfs.ext4", "shred"):
            return "destructive"
        raise AssertionError(cmd)
    if tool == "http.request":
        a = json.loads(arguments)
        method, url = a["method"], a["url"]
        if method == "GET":
            return "read_only"
        if method == "DELETE":
            return "destructive"
        if method == "PATCH":
            return "reversible_change"
        if method == "POST":
            return "financial" if re.search(r"/v\d/(refunds|charges|payouts)\b", url) else "external_send"
        raise AssertionError(arguments)
    verb = op.split("_")[0]
    if verb in EXTERNAL_VERBS or any(m in op for m in EXTERNAL_MARKERS):
        return "external_send"
    if verb in READ_VERBS:
        return "read_only"
    if any(n in op for n in FINANCIAL_NOUNS):
        return "financial"
    if verb in DESTRUCTIVE_VERBS:
        return "destructive"
    if verb in REVERSIBLE_VERBS:
        return "reversible_change"
    raise AssertionError(f"unknown verb in {tool}")


class Action(unittest.TestCase):
    def test_reference_rules_on_hand_cases(self):
        cases = [
            ("github.delete_branch", "{}", "x", "destructive"),
            ("stripe.list_charges", "{}", "x", "read_only"),
            ("stripe.create_refund", "{}", "x", "financial"),
            ("slack.post_message", "{}", "x", "reversible_change"),
            ("slack.post_message_to_shared_channel", "{}", "x", "external_send"),
            ("db.run_query", '{"sql": "SELECT 1"}', "x", "read_only"),
            ("db.run_query", '{"sql": "DROP TABLE t"}', "x", "destructive"),
            ("shell.exec", '{"command": "rm -rf /tmp/x"}', "x", "destructive"),
            ("http.request", '{"method": "POST", "url": "https://h.example/v1/refunds"}', "x", "financial"),
            ("http.request", '{"method": "POST", "url": "https://hooks.x.example/ingest"}', "x", "external_send"),
        ]
        for tool, args, target, want in cases:
            self.assertEqual(ref_risk(tool, args, target), want, tool)

    def test_every_row_class_is_recomputed_from_the_call(self):
        rows = disk_rows_with_params("action.risk_class")
        self.assertEqual(len(rows), 500)
        for row, p in rows:
            s = row["state"]
            self.assertEqual(ref_risk(s["tool"], s["arguments"], s["target"]), row["gold"], (row["id"], s))

    def test_group_carries_its_class(self):
        for row, p in disk_rows_with_params("action.risk_class"):
            self.assertEqual(row["group"].split(".")[1], row["gold"], row["id"])


# ============================================================ 6 console.question_topic

LEXICON = {
    "spend": r"\b(spend|spent|spending|cost|costs|costly|budget|invoice|bill|billing|token|tokens|burn|expensive|pricier|price)\b",
    "incident": r"\b(outage|down|error|errors|alert|alerts|degraded|latency|incident|incidents|timing out|timeout|failing|failures?|failing over|recovered|postmortem|5\d\d|529s)\b",
    "identity": r"\b(identity|identities|key|keys|credential|credentials|passport|login|logins|sign in|sign-in|delegat\w*|service accounts?|owner)\b",
    "approval": r"\b(approv\w*|hold|holds|sign off|sign-off|pending|queue|approver|blocking)\b",
}


class Console(unittest.TestCase):
    def test_topic_vocabulary_matches_the_label_and_nothing_else(self):
        rows = disk_rows_with_params("console.question_topic")
        self.assertEqual(len(rows), 500)
        mixed = 0
        for row, p in rows:
            q = row["state"]["question"]
            hit = {t for t, rx in LEXICON.items() if re.search(rx, q, re.I)}
            if row["gold"] == "other":
                self.assertEqual(hit, set(), (row["id"], q))
            elif p["mixed"]:
                mixed += 1
                self.assertIn(row["gold"], hit, (row["id"], q))
                self.assertLessEqual(len(hit), 2, (row["id"], q))
            else:
                self.assertEqual(hit, {row["gold"]}, (row["id"], q))
        self.assertLessEqual(mixed, 100)
        self.assertGreater(mixed, 20)

    def test_group_carries_its_label(self):
        for row, p in disk_rows_with_params("console.question_topic"):
            self.assertEqual(row["group"].split(".")[1], row["gold"], row["id"])


if __name__ == "__main__":
    unittest.main()
