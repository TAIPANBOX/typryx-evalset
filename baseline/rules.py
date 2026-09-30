"""Baseline 2, "no model": keyword and regex rules, an afternoon's work.

One short function per family, tuned on train only and checked on dev
(`python3 -m baseline.rules` prints train and dev accuracy per family).
"""
import datetime
import re

# ---------------------------------------------------------------- complexity
REASONING = (r"\b(prove|proof|derive|derivation|rigorous\w*|step by step|formally|induction|invariants?|justify each step|"
             r"show each step|work through it carefully|check your final answer)\b")
HARD = (r"\b(migrating|threat-model|postmortem|redesign|refactor\w*|propose|design (a|the)|evaluate whether|"
        r"fine-tune|exactly-once|zero-downtime|controls to|realistic options|trade-offs?|enumerate|across regions)\b")
DEFAULT = r"\b(summari[sz]e|rewrite|proofread|translate this|compare|checklist|explain|suggest|draft|write an?)\b"
CHEAP = (r"\b(stand for|capital of|synonym|translate \"|roman numerals|prime number|yes or no|fix the typo|"
         r"extract the email|what does .{1,30} (mean|do)|format this date|which is (bigger|larger))\b")


def complexity(s):
    p = s["prompt"].lower()
    n = len(p.split())
    if re.search(REASONING, p):
        return "reasoning"
    if re.search(HARD, p):
        return "hard"
    if re.search(CHEAP, p):
        return "cheap"
    if re.search(DEFAULT, p):
        return "default"
    if n <= 12:
        return "cheap"
    return "hard" if n >= 50 else "default"


# -------------------------------------------------------------------- triage
METRICS = [  # first match wins, so the specific ones come first
    ("price", r"price|pricing|rate card|per-1m|rate \$"),
    ("uniq", r"distinct|unique|repeat"),
    ("traffic", r"traffic|active users|sessions|customer|end-user|inbound"),
    ("calls", r"calls|request count|call count|call volume|requests"),
]
CONFIG = r"quota|limit|\bcap\b|routing|default route|model|setting|timeout|retr(y|ies)|throttl|max.?tokens|turned off|now allows|switched off|cache"
NOISE = r"\bno (releases|deploys)|nothing|unrelated|nobody|empty"


def _value(clause):
    """One number from a clause: a percent change, an Nx multiplier or a price move."""
    m = re.search(r"\$([\d.]+)\s*->\s*\$([\d.]+)", clause)
    if m:
        return (float(m[2]) / float(m[1]) - 1) * 100
    m = re.search(r"([\d.]+)([mk]?) [a-z ]+ versus ([\d.]+)([mk]?)", clause)
    if m:
        scale = {"": 1, "k": 1e3, "m": 1e6}
        return (float(m[1]) * scale[m[2]] / (float(m[3]) * scale[m[4]]) - 1) * 100
    m = re.findall(r"([+-]?\d+(?:\.\d+)?)\s*(%|x\b)", clause)
    if not m:
        return 0.0 if re.search(r"flat|unchanged|same|not really moved", clause) else None
    num, unit = m[-1]
    v = float(num) if unit == "%" else (float(num) - 1) * 100
    return -abs(v) if re.search(r"down|lower|fell|dropped", clause) else v


def triage(s):
    text = (s["anomaly"] + " | " + s["recent_changes"]).lower()
    seen, cfg = {}, False
    for clause in re.split(r"\.(?=\s|$)|[;|]|,\s+(?=and\b)|,\s(?=[a-z_]+=)", text):
        ev = re.search(r"event=(\w+)", clause)
        if not re.search(NOISE, clause) and ((ev and ev[1] not in ("none", "noise")) or (not ev and re.search(CONFIG, clause))):
            cfg = True
        for name, pat in METRICS:
            if re.search(pat, clause):
                v = _value(clause)
                if name == "uniq" and v is not None:
                    v = 100 - v if "repeat" in clause and "distinct" not in clause else v
                if v is not None:
                    seen.setdefault(name, v)
                break
        m = re.search(r"unique_ratio=([\d.]+)|unique-request ratio is ([\d.]+)", clause)
        if m:
            seen["uniq"] = float(m[1] or m[2]) * 100
    calls, traffic, price, uniq = (seen.get(k) for k in ("calls", "traffic", "price", "uniq"))
    if price is not None and price >= 15:
        return "price_change"
    if cfg:
        return "misconfiguration"
    if calls is not None and uniq is not None and uniq <= 25 and (
            calls >= 3 * traffic if traffic is not None else calls >= 300):
        return "runaway_agent"
    if calls is not None and traffic is not None and abs(calls - traffic) <= 10 and calls >= 20:
        return "expected_growth"
    return "unknown"


# --------------------------------------------------------------- outcome_met
UNITS = {("feet", "inches"): 12, ("yards", "feet"): 3, ("pounds", "ounces"): 16, ("weeks", "days"): 7,
         ("days", "hours"): 24, ("hours", "minutes"): 60, ("minutes", "seconds"): 60,
         ("metres", "centimetres"): 100, ("kilometres", "metres"): 1000, ("kilograms", "grams"): 1000,
         ("litres", "millilitres"): 1000, ("gallons", "quarts"): 4, ("miles", "feet"): 5280}
UNITS.update({(b, a): 1 / f for (a, b), f in list(UNITS.items())})
UNIT_WORDS = {u for pair in UNITS for u in pair}


def _expected_number(t):
    """The number the task asks for, or None when a regex cannot tell."""
    n = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t)]
    units = [w for w in re.findall(r"[a-z]+", t) if w in UNIT_WORDS]
    if len(n) == 1 and len(set(units)) == 2:
        src = re.search(r"\d(?:\.\d+)? ([a-z]+)", t)[1]
        dst = [u for u in units if u != src]
        return n[0] * UNITS[(src, dst[0])] if (src, dst[0]) in UNITS else None
    if len(n) != 2:
        return None
    a, b = n
    if re.search(r"subtract|away from", t):
        return b - a
    if re.search(r"remain|minus| - ", t):
        return a - b
    if re.search(r"product|times|\*|\bx\b|each|there are \d+ ", t):
        return a * b
    if re.search(r"sum|plus|\+|total", t):
        return a + b
    return None


def outcome_met(s):
    t, a = s["task"].lower(), s["final_answer"]
    nums = re.findall(r"-?\d+(?:\.\d+)?", a.replace(",", ""))
    quoted = re.search(r"\"([^\"]+)\"|'([a-z ]{2,})'", t)
    tail = re.search(r"(?:: |write |of )([a-z ]+?)(?: in reverse| in all caps| in capital letters|[.?]|$)", t)
    subject = (quoted and (quoted[1] or quoted[2])) or (tail and tail[1]) or ""
    if re.search(r"revers|backwards", t):
        return subject[::-1] in a.lower()
    if re.search(r"all caps|capital|upper", t):
        return subject.upper() in a
    if re.search(r"how many items|entries|how many are there", t):
        items = re.search(r"[a-z]+(?:, [a-z]+)+", t)
        return bool(items and nums) and int(nums[-1]) == items[0].count(",") + 1
    if re.search(r"letter|characters|how often|count the \w+s in", t):
        letter = re.search(r"letter '?(\w)\b|'(\w)'|count the (\w)s in ", t)
        if not letter:
            return True
        word = (re.search(r"\"(\w+)\"", t) or re.search(r"(\w+)[?.]*$", t))[1]
        return bool(nums) and int(nums[-1]) == word.count([g for g in letter.groups() if g][0])
    m = re.search(r"(?:sort|order|arrange)[^:]*: (.*)$", t)
    if m:
        items = re.findall(r"[a-z0-9]+", m[1])
        want = sorted(items, key=lambda w: (len(w), w) if w.isdigit() else (0, w))
        return [w for w in re.findall(r"[a-z0-9]+", a.lower()) if w in items] == want
    d = re.search(r"(\d{4})-(\d\d)-(\d\d)|(\d{1,2}) ([a-z]+) (\d{4})|([a-z]+) (\d{1,2}), (\d{4})", t)
    if d and re.search(r"day", t):
        g = d.groups()
        ds = "-".join(g[:3]) if g[0] else (f"{g[3]} {g[4]} {g[5]}" if g[3] else f"{g[7]} {g[6]} {g[8]}")
        for fmt in ("%Y-%m-%d", "%d %B %Y"):
            try:
                return datetime.datetime.strptime(ds, fmt).strftime("%A").lower() in a.lower()
            except ValueError:
                pass
    want = _expected_number(t)
    if want is not None and nums:
        return abs(float(nums[-1]) - want) < 0.0015
    return True  # nothing a regex can check: trust the agent


# ------------------------------------------------------------ answer_quality
NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5}
PADDING = (r"(let me know|hope|feel free|thanks|happy|tell me|i can|i am|i kept|this (is|answer)|that is the|"
           r"it (is worth|helps to)|your situation|different teams|there is usually|of course|sure,|good question|"
           r"here is|short version)")
CLOSER = (r"(?:Hope that|Let me|Feel free|Tell me|Happy to|Thanks for|I can |I am |I kept|This is|This answer|"
          r"That is the|It is worth|It helps to|Your situation|Different teams|There is usually)")
DEFLECT = r"clarify which|don't have enough information|not sure about|it varies a lot|circle back"


def answer_quality(s):
    n = next((v for k, v in NUMBERS.items() if re.search(r"\b" + k + r"\b", s["task"].lower())), 3)
    if re.search(DEFLECT, s["final_answer"].lower()):
        return 0
    text = re.sub(r"(?<=[a-z])\s(?=" + CLOSER + ")", "\n", s["final_answer"])  # a closer glued to an item
    parts = re.split(r"\n|;|(?<=[.!])\s+|\s(?=(?:first|second|third|fourth|fifth),)", text, flags=re.I)
    items = [p for p in (x.strip(" -*.,") for x in parts) if re.search(r"[a-z]{3}", p, re.I)
             and not re.match(PADDING, p.lower())]
    k = len(items)
    if k == 0:
        return 0
    if k >= n:
        return 3
    return 2 if k == n - 1 and n >= 4 else 1


# ---------------------------------------------------------------------- risk
READ = r"^(get|list|read|retrieve|search|tail|describe|fetch|show|view)\b"
RISK = [  # first pattern found decides
    ("financial", r"refund|charge|payout|subscription|purchase|\bbuy\b|top.up|pay.bill|transfer|\bpay\b"),
    ("destructive", r"delete|destroy|terminate|\bdrop\b|truncate|\brm\b|shred|wipe"),
    ("external_send", r"\bsend|publish|share|forward|upload|third.party|partner|\bpost\b|curl|webhook"),
    ("read_only", r"\b(get|select|explain|df|cat|tail|ps|ls)\b"),
]
GENERIC = ("db.run_query", "http.request", "shell.exec")


def risk(s):
    tool = s["tool"].lower()
    name = tool.split(".")[-1].replace("_", " ")
    if tool in GENERIC:  # the tool name says nothing, so read the arguments
        name = s["arguments"].lower()
    elif re.search(READ, name):
        return "read_only"
    for label, pat in RISK:
        if re.search(pat, name):
            return "reversible_change" if label == "external_send" and "(internal" in s["target"] else label
    return "reversible_change"


# ------------------------------------------------------------------- console
TOPICS = [
    ("approval", r"approv|sign off|sign-off|on hold|holds?\b|pending"),
    ("identity", r"identit|passport|credential|\bkeys?\b|login|delegat|sign-in|token scope|scopes|service accounts?|permissions?"),
    ("spend", r"cost|spend|budget|invoice|bill|\$|price|cheaper|tokens? (used|spent)|paying|expensive"),
    ("incident", r"outage|error|alert|degrad|incident|latency|\b5\d\d\b|down\b|failing|failures?|recover\w*|spike|timing out|timeouts?"),
]


def topic(s):
    q = s["question"].lower()
    for label, pat in TOPICS:
        if re.search(pat, q):
            return label
    return "other"


FAMILIES = {
    "request.complexity": complexity,
    "triage.anomaly_class": triage,
    "eval.outcome_met": outcome_met,
    "eval.answer_quality": answer_quality,
    "action.risk_class": risk,
    "console.question_topic": topic,
}


class Rules:
    def predict(self, family, state):
        return FAMILIES[family](state)


if __name__ == "__main__":
    import collections
    import os
    from .constant import ROOT, load_jsonl
    for split in ("train", "dev"):
        ok, tot = collections.Counter(), collections.Counter()
        for r in load_jsonl(os.path.join(ROOT, "data", split + ".jsonl")):
            tot[r["family"]] += 1
            ok[r["family"]] += FAMILIES[r["family"]](r["state"]) == r["gold"]
        for fam in FAMILIES:
            print(f"{split:5} {fam:24} {ok[fam]}/{tot[fam]} = {ok[fam] / tot[fam]:.3f}")
