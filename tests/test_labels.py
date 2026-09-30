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

import math

THREE_QUARTERS = 0.75
SETTINGS = {"cache_disabled", "max_tokens_raised", "model_route_changed", "quota_raised", "rate_limit_removed", "context_cap_raised"}


def ref_shares(p):
    """Each cause's share of the cost increase, written from the rule's prose:
    work in log terms (calls x price multiply), count only the increase, and
    divide by the larger of the headline increase and what is explained."""
    ln = lambda pct: math.log1p(pct / 100.0)
    headline = ln(p["spend"])
    calls = None if p["calls"] is None else max(0.0, ln(p["calls"]))
    demand = None if p["traffic"] is None else max(0.0, ln(p["traffic"]))
    price = None if p["price"] is None else max(0.0, ln(p["price"]))
    amounts = {"price": price}
    if calls is not None and demand is not None:
        amounts["growth"] = min(calls, demand)
        amounts["runaway"] = calls - min(calls, demand)
    else:
        amounts["growth"] = amounts["runaway"] = None
    amounts["config"] = None if (calls is None or price is None) else max(0.0, headline - calls - price)
    explained = sum(v for k, v in amounts.items() if v is not None)
    if calls is not None and demand is None:      # calls known but not attributable to demand or to extra calls
        explained += calls
    denom = max(headline, explained)
    return {k: (None if v is None else v / denom) for k, v in amounts.items()}


def ref_classify(p):
    sh = ref_shares(p)
    u, event = p["unique"], p["event"]
    verdicts = []
    if sh["growth"] is not None and sh["growth"] >= THREE_QUARTERS and not (u is not None and u < 50):
        verdicts.append("expected_growth")
    if sh["runaway"] is not None and sh["runaway"] >= THREE_QUARTERS and u is not None and u <= 25:
        verdicts.append("runaway_agent")
    if sh["config"] is not None and sh["config"] >= THREE_QUARTERS and event in SETTINGS:
        verdicts.append("misconfiguration")
    if sh["price"] is not None and sh["price"] >= THREE_QUARTERS:
        verdicts.append("price_change")
    return verdicts[0] if len(verdicts) == 1 else "unknown"


#: Hand-written truth table: (spend, calls, traffic, unique, price, event) -> class.
#: The first three rows are the rows a blind re-label disputed (by content).
TRUTH = [
    ((486, 465, 4, 13, 21, "none"), "runaway_agent"),              # tri-0252: repeats, flat traffic, price a small part
    ((485, 454, 3, 10, 31, "none"), "runaway_agent"),              # tri-0436
    ((316, 2, None, None, 2, "cache_disabled"), "misconfiguration"),   # tri-0231: cache off, volume and price flat, cost 4x
    ((266, 149, 4, 18, 47, "none"), "unknown"),                    # tri-0139: calls and price comparable
    ((80, 49, 13, 30, 9, "noise"), "unknown"),                     # tri-0212
    ((283, None, None, None, None, "rate_limit_removed"), "unknown"),  # tri-0106: no volume data
    ((256, None, None, 69, 4, "model_route_changed"), "unknown"),  # tri-0404
    ((30, None, None, None, None, "context_cap_raised"), "unknown"),   # tri-0467
    ((150, 150, 0, 10, 0, "agent_deploy"), "runaway_agent"),
    ((150, 150, 0, 10, 0, "cache_disabled"), "runaway_agent"),     # one cause dominates; the event does not explain the cost
    ((150, 150, None, 10, 0, "none"), "unknown"),                  # traffic hidden: cannot split calls from demand
    ((150, 150, 0, 60, 0, "none"), "unknown"),                     # extra calls but diverse prompts
    ((60, 60, 62, 80, 1, "none"), "expected_growth"),
    ((60, 60, 62, 10, 1, "none"), "unknown"),                      # growth numbers but mostly repeats
    ((60, 60, None, 80, 1, "none"), "unknown"),
    ((50, 3, 2, 70, 40, "none"), "price_change"),
    ((40, None, None, None, 40, "none"), "price_change"),          # price alone explains the whole increase
    ((50, 3, 2, 70, None, "none"), "unknown"),
    ((120, 60, 60, 70, 40, "none"), "unknown"),                    # growth and price comparable
    ((200, 20, 2, 70, 0, "cache_disabled"), "misconfiguration"),
    ((200, None, 2, None, None, "quota_raised"), "unknown"),       # cannot rule out calls or price
    ((200, 20, 2, 70, 0, "none"), "unknown"),                      # unexplained and no setting changed
    ((300, None, None, None, None, "none"), "unknown"),
]


class Triage(unittest.TestCase):
    def test_truth_table_holds_for_reference_and_generator(self):
        for (spend, c, t, u, pr, e), want in TRUTH:
            p = {"spend": spend, "calls": c, "traffic": t, "unique": u, "price": pr, "event": e}
            self.assertEqual(ref_classify(p), want, p)
            self.assertEqual(triage.classify(p), want, p)

    def test_a_dominant_cause_wins_even_when_a_second_cause_is_present(self):
        # +465% calls on flat traffic with 13% distinct prompts, price +21%: calls are about 88% of the increase
        p = {"spend": 486, "calls": 465, "traffic": 4, "unique": 13, "price": 21, "event": "none"}
        self.assertGreaterEqual(ref_shares(p)["runaway"], 0.85)
        self.assertEqual(triage.classify(p), "runaway_agent")
        # calls +149% against price +47%: the two are comparable, nothing reaches 3/4
        q = {"spend": 266, "calls": 149, "traffic": 4, "unique": 18, "price": 47, "event": "none"}
        self.assertLess(max(v for v in ref_shares(q).values() if v is not None), THREE_QUARTERS)
        self.assertEqual(triage.classify(q), "unknown")

    def test_a_label_does_not_demand_evidence_its_own_verdict_does_not_need(self):
        # the bug behind tri-0231: a setting change whose cost is all per-call cost needs calls and
        # price to be known, not traffic
        p = {"spend": 316, "calls": 2, "traffic": None, "unique": None, "price": 2, "event": "cache_disabled"}
        self.assertEqual(triage.classify(p), "misconfiguration")
        # and every setting event can be the cause
        for ev in triage.SETTING_EVENTS:
            self.assertEqual(triage.classify(dict(p, event=ev)), "misconfiguration", ev)

    def test_generator_classifier_agrees_with_the_reference_on_a_sweep(self):
        rng = random.Random(99)
        vals = [None, -30, -10, -4, 0, 4, 10, 20, 35, 60, 99, 100, 150, 250, 465, 900]
        uvals = [None, 0, 10, 25, 26, 40, 49, 50, 51, 90]
        checked = 0
        for _ in range(40000):
            p = {"spend": rng.choice([25, 40, 80, 120, 200, 316, 486, 800]), "calls": rng.choice(vals), "traffic": rng.choice(vals),
                 "unique": rng.choice(uvals), "price": rng.choice(vals), "event": rng.choice(triage.ALL_EVENTS)}
            near = any(v is not None and abs(v - THREE_QUARTERS) < 1e-9 for v in ref_shares(p).values())
            if near:
                continue
            checked += 1
            self.assertEqual(triage.classify(p), ref_classify(p), p)
        self.assertGreater(checked, 39000)

    def test_every_row_gold_is_the_label_of_its_parameters(self):
        rows = disk_rows_with_params("triage.anomaly_class")
        self.assertEqual(len(rows), 500)
        for row, p in rows:
            self.assertEqual(ref_classify(p), row["gold"], (row["id"], p))

    def test_every_share_is_clear_of_the_bar_so_no_row_turns_on_a_hair(self):
        for row, p in disk_rows_with_params("triage.anomaly_class"):
            for k, v in ref_shares(p).items():
                self.assertTrue(v is None or abs(v - THREE_QUARTERS) > 0.03, (row["id"], k, v))

    def test_the_headline_spend_reconciles_with_the_shown_calls_and_price(self):
        for row, p in disk_rows_with_params("triage.anomaly_class"):
            if p["calls"] is None or p["price"] is None:
                continue
            implied = round(100 * ((1 + p["calls"] / 100) * (1 + p["price"] / 100) - 1))
            if row["gold"] == "misconfiguration":
                self.assertGreaterEqual(p["spend"], implied, row["id"])       # per-call cost rose too
            elif row["gold"] != "unknown":
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

    def test_unknown_rows_come_in_the_three_flavours(self):
        rows = [(r, p) for r, p in disk_rows_with_params("triage.anomaly_class") if r["gold"] == "unknown"]
        hidden = sum(1 for _, p in rows if None in (p["calls"], p["traffic"], p["unique"], p["price"]))
        self.assertGreater(hidden, 10)
        full = [p for _, p in rows if None not in (p["calls"], p["traffic"], p["unique"], p["price"])]
        self.assertGreater(len(full), 10)


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
    """3: all N clear. 2: all N present, exactly one vague. 1: something
    missing, at least one correct item. 0: no item of the topic at all."""
    if clear == n and vague == 0:
        return 3
    if clear == n - 1 and vague == 1:
        return 2
    if vague == 0 and 1 <= clear <= n - 1:
        return 1
    if clear == 0 and vague == 0:
        return 0
    raise AssertionError((n, clear, vague))


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

    def test_level_rule_rejects_what_the_spec_does_not_define(self):
        with self.assertRaises(ValueError):
            quality.level_of(4, 2, 1, False)      # one missing AND one vague
        with self.assertRaises(ValueError):
            quality.level_of(4, 0, 0, False)      # nothing given, not off-topic
        with self.assertRaises(ValueError):
            quality.level_of(4, 2, 2, False)      # two vague

    def test_a_missing_item_is_never_level_two(self):
        # N-1 clear items and nothing else: one item missing -> 1, not 2
        self.assertEqual(quality.level_of(3, 2, 0, False), 1)
        self.assertEqual(reference_level(3, 2, 0), 1)
        self.assertEqual(quality.level_of(3, 2, 1, False), 2)
        self.assertEqual(reference_level(3, 2, 1), 2)
        for row, p in disk_rows_with_params("eval.answer_quality"):
            if row["gold"] == 2:
                self.assertEqual((p["clear"], p["vague"]), (p["n"] - 1, 1), row["id"])
            if row["gold"] == 1:
                self.assertTrue(1 <= p["clear"] < p["n"] and p["vague"] == 0, row["id"])

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
