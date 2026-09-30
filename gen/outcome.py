"""Family 3: eval.outcome_met (noul: does the final answer achieve the task?).

Every task is checkable by construction: arithmetic (add, subtract, multiply),
unit conversion, weekday of a date, counting list items, and string work
(reverse, uppercase, count a letter), sorting a short list. The generator
computes the right answer itself and either states it or states a plausible
near miss that is guaranteed to differ. gold = (stated answer is the right
one).

Ten task kinds, 50 rows each, 25 true and 25 false per kind. Each kind has
seven task phrasings; a phrasing is the row's group. The way the final answer
is worded (bare number, sentence, working shown) is drawn per row and does not
depend on the label.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from fractions import Fraction

from .common import Case, finalize, rng_for, spread

FAMILY = "eval.outcome_met"
TEMPLATE = "eval.outcome_met"
CODE = "om"
LABELS = [True, False]
KINDS = ["add", "sub", "mul", "unit", "weekday", "count", "reverse", "upper", "letters", "sort"]
ROWS_PER_KIND = 50
PHRASINGS_PER_KIND = 7

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

# ---------------------------------------------------------------- task texts

TASKS = {
    "add": [
        "What is {a} + {b}?", "Add {a} and {b}.", "Calculate the sum of {a} and {b}.",
        "If one batch has {a} requests and another has {b}, how many requests is that in total?",
        "{a} plus {b} equals what?", "Our gateway logged {a} calls on Monday and {b} on Tuesday. What is the two-day total?",
        "Compute {a} + {b} and give just the number.",
    ],
    "sub": [
        "What is {a} - {b}?", "Subtract {b} from {a}.", "What's {a} minus {b}?",
        "The budget was {a} credits and we spent {b}. How many credits are left?", "Take {b} away from {a}. What remains?",
        "Calculate the difference between {a} and {b} (larger minus smaller).", "{a} tokens were allowed and {b} were used. How many tokens remain?",
    ],
    "mul": [
        "What is {a} x {b}?", "Multiply {a} by {b}.", "What is {a} times {b}?",
        "Each of {a} agents makes {b} calls per hour. How many calls per hour in total?", "Compute {a} * {b}.",
        "A batch has {a} rows and there are {b} batches. How many rows in total?", "Find the product of {a} and {b}.",
    ],
    "unit": [
        "Convert {v} {frm} to {to}.", "How many {to} are in {v} {frm}?", "{v} {frm} is how many {to}?", "Express {v} {frm} in {to}.",
        "I have {v} {frm}. What is that in {to}?", "What is {v} {frm} in {to}? Give the number only.", "Please convert: {v} {frm} -> {to}",
    ],
    "weekday": [
        "What day of the week was {date}?", "Which weekday is {date}?", "{date} falls on which day of the week?",
        "The release is scheduled for {date}. What weekday is that?", "Tell me the weekday for {date}.",
        "On what day of the week does {date} fall? One word answer.", "What day will it be on {date}?",
    ],
    "count": [
        "How many items are in this list: {lst}?", "Count the items: {lst}", "This list has how many entries? {lst}",
        "Here is a list of {noun}: {lst}. How many are there?", "How many of these are {cat}: {lst}?",
        "Count only the {cat} in this list: {lst}", "Out of {lst}, how many are {cat}?",
    ],
    "reverse": [
        "Reverse the string \"{w}\".", "What is \"{w}\" spelled backwards?", "Write {w} in reverse order of letters.",
        "Reverse this word: {w}", "Give me the letters of '{w}' in reverse.",
        "Please reverse the following string and return only the result: {w}", "What do you get if you reverse \"{w}\"?",
    ],
    "upper": [
        "Convert \"{w}\" to uppercase.", "Write {w} in capital letters.", "What is \"{w}\" in all caps?", "Uppercase the text: {w}",
        "Make this string uppercase: {w}", "Return the following in ALL CAPS: {w}", "Put this in capitals only: {w}",
    ],
    "letters": [
        "How many times does the letter '{l}' appear in \"{w}\"?", "Count the {l}s in {w}.", "How many {l}'s are in the word {w}?",
        "In the string \"{w}\", how often does '{l}' occur?", "Count occurrences of the letter {l} in: {w}",
        "Number of '{l}' characters in \"{w}\"?", "How many times is the letter {l} used in {w}?",
    ],
    "sort": [
        "Sort these numbers in ascending order: {lst}", "Put these in order from smallest to largest: {lst}",
        "Sort the following in descending order: {lst}", "Order this list from largest to smallest: {lst}",
        "Sort alphabetically: {lst}", "Arrange these words in alphabetical order: {lst}", "Sort ascending: {lst}",
    ],
}
#: For sort, the phrasing decides direction and item type (see _sort_mode).
SORT_MODE = ["num_asc", "num_asc", "num_desc", "num_desc", "word_asc", "word_asc", "num_asc"]
#: For count, phrasings 0-3 count everything, 4-6 count a category.
COUNT_CATEGORY_PHRASING = {4, 5, 6}

# ----------------------------------------------------------------- answer texts

ANSWER_STYLES = [
    "{v}", "{v}.", "The answer is {v}.", "It's {v}.", "I get {v}.", "Answer: {v}", "That comes to {v}.", "Result: {v}",
    "My answer: {v}", "After checking it twice, {v}.", "Final answer: {v}", "{v}, I believe.", "Looks like {v}.",
    "Done. {v}", "So the result is {v}, and I double-checked it.",
]
ALT_STYLES = {
    "add": ["{a} + {b} = {v}", "{a} plus {b} is {v}."],
    "sub": ["{a} - {b} = {v}", "{a} minus {b} leaves {v}."],
    "mul": ["{a} x {b} = {v}", "{a} times {b} is {v}."],
    "unit": ["{v_in} {frm} = {v}"],
    "weekday": ["{date} is a {v}.", "That date falls on a {v}."],
    "count": ["There are {v} of them."],
    "reverse": ["Reversed: {v}", "Backwards it reads {v}."],
    "upper": ["In capitals: {v}", "Uppercase: {v}"],
    "letters": ["'{w}' has {v} of the letter {l}.", "The letter {l} appears {v} times in {w}."],
    "sort": ["Sorted: {v}", "In order: {v}"],
}
ALT_P = 0.3

# ----------------------------------------------------------------------- pools

WORDS = ["latency", "throttle", "ledger", "approval", "passport", "budget", "gateway", "deploy", "rollback", "anomaly", "quota",
         "policy", "backoff", "checkpoint", "sandbox", "dispatch", "failover", "keyring", "manifest", "outage", "tracing",
         "console", "upstream", "webhook", "schedule", "payload", "cluster", "replica", "runbook", "timeout", "delegate", "telemetry"]
PHRASES_LOWER = ["spend report", "agent passport", "approval queue", "policy hold", "runaway agent", "rate limit", "cost center",
                 "safe to retry", "incident review", "budget cap", "model router", "audit trail", "pending sign off", "green build"]
CODES = ["x7k2p9", "agent-42", "req_8841", "node-b3", "k9-alpha", "tz-1750", "svc-q4z"]
FRUITS = ["apple", "banana", "cherry", "mango", "pear", "plum", "grape", "peach", "lemon", "fig"]
ANIMALS = ["otter", "heron", "lynx", "badger", "falcon", "gecko", "moose", "tapir", "viper", "whale"]
COLOURS = ["crimson", "teal", "amber", "violet", "indigo", "ochre", "scarlet", "olive", "azure", "coral"]
SERVICES = ["nginx", "redis", "postgres", "kafka", "grafana", "vault", "etcd", "envoy", "consul", "prometheus"]
TOOLS = ["hammer", "wrench", "chisel", "pliers", "spanner", "mallet", "drill", "saw", "level", "clamp"]
COUNT_DOMAINS = {"fruits": FRUITS, "animals": ANIMALS, "colours": COLOURS, "services": SERVICES, "tools": TOOLS}
UNIT_PAIRS = [  # (from, to, multiplier from->to)
    ("kilometres", "metres", Fraction(1000)), ("hours", "minutes", Fraction(60)), ("minutes", "seconds", Fraction(60)),
    ("days", "hours", Fraction(24)), ("weeks", "days", Fraction(7)), ("feet", "inches", Fraction(12)), ("yards", "feet", Fraction(3)),
    ("pounds", "ounces", Fraction(16)), ("kilograms", "grams", Fraction(1000)), ("litres", "millilitres", Fraction(1000)),
    ("gallons", "quarts", Fraction(4)), ("miles", "feet", Fraction(5280)), ("metres", "centimetres", Fraction(100)),
    ("metres", "kilometres", Fraction(1, 1000)), ("seconds", "minutes", Fraction(1, 60)), ("ounces", "pounds", Fraction(1, 16)),
    ("hours", "days", Fraction(1, 24)), ("inches", "feet", Fraction(1, 12)), ("grams", "kilograms", Fraction(1, 1000)),
    ("millilitres", "litres", Fraction(1, 1000)), ("days", "weeks", Fraction(1, 7)), ("quarts", "gallons", Fraction(1, 4)),
]
LETTER_WORDS = ["refrigerator", "mississippi", "approval", "anomaly", "environment", "committee", "throughput", "observability",
                "infrastructure", "rollback", "accelerate", "parallelism", "reconciliation", "deployment", "committed", "recursion"]


# --------------------------------------------------------------------- helpers

def fmt_fraction(f: Fraction) -> str:
    if f.denominator == 1:
        return str(f.numerator)
    d = Decimal(f.numerator) / Decimal(f.denominator)
    return format(d.quantize(Decimal("0.001")).normalize(), "f")


def _digit_swap(n: int, rng) -> int | None:
    s = str(n)
    idx = [i for i in range(len(s) - 1) if s[i] != s[i + 1]]
    if not idx:
        return None
    i = rng.choice(idx)
    return int(s[:i] + s[i + 1] + s[i] + s[i + 2:])


def _near_int(rng, right: int, extras: list[int]) -> int:
    for _ in range(100):
        strat = rng.choice(["off1", "off10", "off100", "swap", "extra", "extra"])
        if strat == "off1":
            v = right + rng.choice([-1, 1])
        elif strat == "off10":
            v = right + rng.choice([-10, 10])
        elif strat == "off100":
            v = right + rng.choice([-100, 100])
        elif strat == "swap":
            v = _digit_swap(right, rng)
        else:
            v = rng.choice(extras) if extras else right + 1
        if v is not None and v != right and v >= 0:
            return v
    return right + 1


def _near_words(rng, right: str, candidates: list[str]) -> str:
    cs = [c for c in candidates if c != right]
    if not cs:
        raise ValueError("no near miss available")
    return rng.choice(cs)


# ----------------------------------------------------------------------- kinds

def make_add(rng):
    hi = rng.choice([99, 999, 999, 9999])
    a, b = rng.randint(11, hi), rng.randint(11, hi)
    right = a + b
    return {"a": a, "b": b}, str(right), lambda: str(_near_int(rng, right, [right + 10 if (a % 10 + b % 10) >= 10 else right - 10, right + 11, right - 9]))


def make_sub(rng):
    hi = rng.choice([99, 999, 9999])
    b = rng.randint(11, hi // 2 + 10)
    a = b + rng.randint(11, hi)
    right = a - b
    return {"a": a, "b": b}, str(right), lambda: str(_near_int(rng, right, [a + b, right + 10, right - 10 if right > 10 else right + 11]))


def make_mul(rng):
    a, b = rng.randint(3, 99), rng.randint(3, 99)
    right = a * b
    return {"a": a, "b": b}, str(right), lambda: str(_near_int(rng, right, [right + a, right - a, right + b, right - b, a + b]))


def make_unit(rng):
    frm, to, mult = rng.choice(UNIT_PAIRS)
    if mult >= 1:
        v = Fraction(rng.choice([2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 45, 50, 75])) + rng.choice([0, 0, Fraction(1, 2)])
    else:
        k = rng.choice([2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 45, 50, 75])
        v = k / mult
    right = v * mult
    others = [m for (_, _, m) in UNIT_PAIRS if m != mult]

    def near():
        for _ in range(100):
            strat = rng.choice(["x10", "x0.1", "othermult", "inverse", "digits"])
            if strat == "x10":
                c = right * 10
            elif strat == "x0.1":
                c = right / 10
            elif strat == "othermult":
                c = v * rng.choice(others)
            elif strat == "inverse":
                c = v / mult
            else:
                n = int(right) if right.denominator == 1 else None
                s = _digit_swap(n, rng) if n is not None and n >= 10 else None
                c = Fraction(s) if s is not None else right + 1
            if c != right and c > 0:
                return fmt_fraction(c)
        return fmt_fraction(right + 1)

    params = {"v": fmt_fraction(v), "frm": frm, "to": to, "mult": str(mult)}
    return params, fmt_fraction(right), near


def make_weekday(rng):
    d = datetime.date(1990, 1, 1) + datetime.timedelta(days=rng.randint(0, 365 * 46))
    fmt = rng.choice(["{month} {day}, {year}", "{day} {month} {year}", "{year}-{mm:02d}-{day:02d}"])
    date = fmt.format(month=MONTHS[d.month - 1], day=d.day, year=d.year, mm=d.month)
    right = WEEKDAYS[d.weekday()]
    idx = d.weekday()
    cands = [WEEKDAYS[(idx + k) % 7] for k in (-2, -1, 1, 2, 3)]
    return {"date": date, "iso": d.isoformat()}, right, lambda: _near_words(rng, right, cands)


def make_count(rng, category_mode: bool):
    names = list(COUNT_DOMAINS)
    if not category_mode:
        dom = rng.choice(names)
        n = rng.randint(4, 13)
        items = rng.sample(COUNT_DOMAINS[dom], min(n, 10))
        while len(items) < n:
            items.append(rng.choice(COUNT_DOMAINS[dom]))
        rng.shuffle(items)
        right = len(items)
        return {"lst": ", ".join(items), "noun": dom, "cat": dom, "items": items, "category_mode": False}, str(right), \
            lambda: str(_near_int(rng, right, [right + 2, max(right - 2, 0)]))
    cat = rng.choice(names)
    others = [x for x in names if x != cat]
    n_in = rng.randint(1, 6)
    n_out = rng.randint(2, 7)
    inside = rng.sample(COUNT_DOMAINS[cat], n_in)
    outside = []
    for _ in range(n_out):
        outside.append(rng.choice(COUNT_DOMAINS[rng.choice(others)]))
    items = inside + outside
    rng.shuffle(items)
    right = n_in
    return {"lst": ", ".join(items), "noun": "items", "cat": cat, "items": items, "category_mode": True}, str(right), \
        lambda: str(_near_int(rng, right, [len(items), right + 2]))


def make_reverse(rng):
    w = rng.choice(WORDS + CODES + WORDS)
    right = w[::-1]
    cands = [w, right[:-1], right[1:]]
    for i in range(len(right) - 1):
        if right[i] != right[i + 1]:
            cands.append(right[:i] + right[i + 1] + right[i] + right[i + 2:])
    return {"w": w}, right, lambda: _near_words(rng, right, cands)


def make_upper(rng):
    w = rng.choice(WORDS + PHRASES_LOWER + PHRASES_LOWER)
    right = w.upper()
    cands = [w.title(), w.capitalize(), w]
    letters = [i for i, ch in enumerate(w) if ch.isalpha()]
    for i in rng.sample(letters, min(3, len(letters))):
        cands.append(right[:i] + right[i].lower() + right[i + 1:])
    return {"w": w}, right, lambda: _near_words(rng, right, cands)


def make_letters(rng):
    w = rng.choice(LETTER_WORDS)
    pool = sorted(set(w))
    letter = rng.choice(pool) if rng.random() < 0.9 else rng.choice("qzxj")
    right = w.count(letter)
    return {"w": w, "l": letter}, str(right), lambda: str(_near_int(rng, right, [len(w), right + 2]))


def make_sort(rng, mode: str):
    if mode.startswith("num"):
        n = rng.randint(5, 8)
        nums = rng.sample(range(1, 100), n)
        ordered = sorted(nums, reverse=(mode == "num_desc"))
        items = [str(x) for x in nums]
        right_items = [str(x) for x in ordered]
    else:
        n = rng.randint(5, 7)
        items = rng.sample(WORDS, n)
        right_items = sorted(items)
    sep = rng.choice([", ", ", ", " "])
    right = sep.join(right_items)

    def near():
        for _ in range(100):
            strat = rng.choice(["swap", "swap", "reverse", "move"])
            ri = list(right_items)
            if strat == "swap":
                i = rng.randrange(len(ri) - 1)
                ri[i], ri[i + 1] = ri[i + 1], ri[i]
            elif strat == "reverse":
                ri = ri[::-1]
            else:
                x = ri.pop(rng.randrange(len(ri)))
                ri.insert(rng.randrange(len(ri) + 1), x)
            cand = sep.join(ri)
            if cand != right:
                return cand
        raise RuntimeError("no near miss")

    return {"lst": sep.join(items), "mode": mode, "sep": sep, "items": items}, right, near


# ------------------------------------------------------------------ generation

def groups_for(kind: str) -> list[str]:
    return [f"{CODE}.{kind}.{i}" for i in range(1, PHRASINGS_PER_KIND + 1)]


def groups() -> list[str]:
    return [g for k in KINDS for g in groups_for(k)]


def _make(rng, kind: str, phrasing: int):
    if kind == "add":
        return make_add(rng)
    if kind == "sub":
        return make_sub(rng)
    if kind == "mul":
        return make_mul(rng)
    if kind == "unit":
        return make_unit(rng)
    if kind == "weekday":
        return make_weekday(rng)
    if kind == "count":
        return make_count(rng, phrasing in COUNT_CATEGORY_PHRASING)
    if kind == "reverse":
        return make_reverse(rng)
    if kind == "upper":
        return make_upper(rng)
    if kind == "letters":
        return make_letters(rng)
    return make_sort(rng, SORT_MODE[phrasing])


def _answer_text(rng, kind: str, params: dict, value: str) -> str:
    v = value
    if kind == "unit":
        v = f"{value} {params['to']}"
    if kind == "reverse" or kind == "upper":
        v = rng.choice([value, f"\"{value}\"", f"'{value}'"])
    fmt_args = dict(params)
    fmt_args["v"] = v
    fmt_args["v_in"] = params.get("v_in", params.get("v"))
    if kind == "unit":
        fmt_args["v_in"] = params["v"]
        fmt_args["v"] = v
    if rng.random() < ALT_P:
        style = rng.choice(ALT_STYLES[kind])
    else:
        style = rng.choice(ANSWER_STYLES)
    return style.format(**fmt_args)


def generate(seed: int) -> list[Case]:
    rng = rng_for(seed, FAMILY)
    cases: list[Case] = []
    seen: set[tuple[str, str]] = set()
    for kind in KINDS:
        gids = groups_for(kind)
        counts = spread(rng, ROWS_PER_KIND, gids)
        # trues per group: half of each group's rows, the odd ones topped up so the kind has 25.
        trues = {g: counts[g] // 2 for g in gids}
        odd = [g for g in gids if counts[g] % 2]
        for g in rng.sample(odd, ROWS_PER_KIND // 2 - sum(trues.values())):
            trues[g] += 1
        for gi, gid in enumerate(gids):
            labels = [True] * trues[gid] + [False] * (counts[gid] - trues[gid])
            rng.shuffle(labels)
            for is_right in labels:
                for _try in range(200):
                    raw, right, near = _make(rng, kind, gi)
                    params = dict(raw)
                    given = right if is_right else near()
                    task = TASKS[kind][gi].format(**params)
                    final = _answer_text(rng, kind, params, given)
                    if (task, final) not in seen:
                        break
                else:
                    raise RuntimeError(f"{gid}: cannot draw distinct items")
                seen.add((task, final))
                p = {k: v for k, v in params.items()}
                p.update(kind=kind, phrasing=gi, right=right, given=given)
                cases.append(Case(FAMILY, TEMPLATE, {"task": task, "final_answer": final}, is_right, gid, p))
    return finalize(cases, rng, TEMPLATE)


def strata() -> dict[str, list[str]]:
    return {k: groups_for(k) for k in KINDS}
