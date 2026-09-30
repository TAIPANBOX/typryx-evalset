"""Family 2: triage.anomaly_class.

Only CLEAR-CUT scenarios are generated: a careful reader should not be able to
reasonably pick another label. Each row starts from numeric scenario
parameters, the label is a deterministic function of them (`classify`), and
the parameters are RENDERED as operator text by one of many rendering styles
(the row's group). Every style can render every label, so the group carries no
label information; the model has to read the numbers.

Parameters (percent deltas against the prior period unless noted):

    spend    headline spend change (derived from calls, price and any per-call factor)
    calls    change in call count, or None if not stated
    traffic  change in real end-user traffic, or None
    unique   share of requests with a distinct prompt, 0..100, or None
    price    change in unit price, or None
    event    "none" | "noise" (an unrelated change) | a SETTING_EVENTS kind

"flat" = within +-10 percent (price: +-5). The rules (amended twice after blind
re-labels; there is no dominance arithmetic, no mixing of causes, no gray zone):

    expected_growth   calls and real traffic both up (>= +20) within 10 points of
                      each other; price flat; unique >= 50 if stated; no setting change
    runaway_agent     prompts are mostly repeats (unique <= 25, stated); price flat; no
                      setting change; and either traffic is stated and calls are up
                      >= +100 and >= 3x traffic's growth, or traffic is not stated and
                      calls are up >= +400 (5x)
    price_change      calls and traffic flat, unit price up >= +15; unique >= 40 if
                      stated; no setting change
    misconfiguration  a setting, quota, cap, routing or model change is recorded (an
                      intentional one counts) and it is the only thing that changed:
                      calls, traffic and price flat or not stated; unique >= 40 if stated
    unknown           spend is up but nothing informative is given: no call, traffic,
                      price or prompt figures, and no change beyond unrelated ones

A parameter set that fits none of these (mixed causes, contradictions, a missing
figure next to otherwise decisive data) has no label: `classify` returns None
and the generator never draws one. The tests check both.
"""

from __future__ import annotations

import random

from .common import ROWS_PER_FAMILY, Case, finalize, rng_for, spread

FAMILY = "triage.anomaly_class"
TEMPLATE = "triage.anomaly_class"
CODE = "tri"
LABELS = ["expected_growth", "runaway_agent", "misconfiguration", "price_change", "unknown"]

SETTING_EVENTS = ["cache_disabled", "max_tokens_raised", "model_route_changed", "quota_raised", "rate_limit_removed", "context_cap_raised"]
QUIET_EVENTS = ["none", "noise"]
ALL_EVENTS = QUIET_EVENTS + SETTING_EVENTS


# ---------------------------------------------------------------- the label

def _flat(x):
    return x is not None and -10 <= x <= 10


def _price_flat(x):
    return x is not None and -5 <= x <= 5


def classify(p: dict):
    """The label of a parameter set, or None if it is not a clear-cut case."""
    c, t, u, pr, e = p["calls"], p["traffic"], p["unique"], p["price"], p["event"]
    if e in SETTING_EVENTS:
        if (c is None or _flat(c)) and (t is None or _flat(t)) and (pr is None or _price_flat(pr)) and (u is None or u >= 40):
            return "misconfiguration"
        return None
    if e not in QUIET_EVENTS:
        return None
    if c is None and t is None and u is None and pr is None:
        return "unknown"
    if c is not None and t is not None and pr is not None and c >= 20 and t >= 20 and abs(c - t) <= 10 and _price_flat(pr) and (u is None or u >= 50):
        return "expected_growth"
    if c is not None and u is not None and u <= 25 and _price_flat(pr):
        if t is not None and c >= 100 and c >= 3 * max(t, 0):
            return "runaway_agent"
        if t is None and c >= 400:
            return "runaway_agent"
    if c is not None and t is not None and pr is not None and _flat(c) and _flat(t) and pr >= 15 and (u is None or u >= 40):
        return "price_change"
    return None


# ------------------------------------------------------------ parameter draw

PROJECTS = ["support-copilot", "billing-assistant", "doc-summarizer", "code-review-bot", "search-rerank", "sales-enrichment",
            "invoice-extractor", "onboarding-flow", "fraud-triage", "meeting-notes", "ticket-router", "kb-answerer",
            "release-notes-writer", "data-labeler"]
WINDOWS = ["week over week", "day over day", "versus the 7-day average", "since last Monday", "month over month", "against the prior 24 hours"]
MODELS_BIG = ["gpt-4.1", "claude-opus", "gemini-2.5-pro", "llama-3.3-70b", "mistral-large"]
MODELS_SMALL = ["gpt-4.1-mini", "claude-haiku", "gemini-2.5-flash", "llama-3.1-8b", "mistral-small"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "last weekend", "yesterday afternoon"]


def _rint(rng, lo, hi):
    return rng.randint(lo, hi)


def _with_spend(p: dict, cfg: float = 1.0) -> dict:
    """The headline spend follows from the true calls, price and per-call
    factor, so the numbers a reader sees reconcile."""
    p["spend"] = round(100 * ((1 + p["calls"] / 100) * (1 + p["price"] / 100) * cfg - 1))
    return p


def draw_scenario(rng, label: str) -> dict:
    """Parameters well inside one class's region (away from every threshold)."""
    if label == "expected_growth":
        t = _rint(rng, 30, 260)
        p = dict(traffic=t, calls=t + _rint(rng, -6, 6), price=_rint(rng, -3, 3), unique=_rint(rng, 58, 95), event=rng.choice(QUIET_EVENTS))
        if rng.random() < 0.25:
            p["unique"] = None
        return _with_spend(p)
    if label == "runaway_agent":
        p = dict(calls=int(150 * 10 ** rng.uniform(0, 1.0)), traffic=_rint(rng, -5, 8), unique=_rint(rng, 2, 18), price=_rint(rng, -3, 3), event=rng.choice(QUIET_EVENTS))
        if rng.random() < 0.3:          # traffic not stated: the jump must be very large
            p["calls"] = int(450 * 10 ** rng.uniform(0, 0.55))
            _with_spend(p)
            p["traffic"] = None
            return p
        return _with_spend(p)
    if label == "price_change":
        p = dict(price=_rint(rng, 25, 150), calls=_rint(rng, -6, 6), traffic=_rint(rng, -6, 6), unique=_rint(rng, 55, 95), event=rng.choice(QUIET_EVENTS))
        if rng.random() < 0.25:
            p["unique"] = None
        return _with_spend(p)
    if label == "misconfiguration":
        p = dict(event=rng.choice(SETTING_EVENTS), traffic=_rint(rng, -6, 6), price=_rint(rng, -3, 3), unique=_rint(rng, 55, 95), calls=_rint(rng, -6, 6))
        _with_spend(p, cfg=rng.uniform(1.8, 4.5))
        for k in ("calls", "traffic", "price", "unique"):   # any of the figures may simply not be stated
            if rng.random() < 0.35:
                p[k] = None
        return p
    if label == "unknown":
        return dict(calls=None, traffic=None, unique=None, price=None, event=rng.choice(QUIET_EVENTS), spend=_rint(rng, 25, 400))
    raise ValueError(label)


def draw_params(rng: random.Random, label: str) -> dict:
    p = draw_scenario(rng, label)
    if classify(p) != label:
        raise RuntimeError(f"drew {label} parameters that classify as {classify(p)}: {p}")
    p["project"] = rng.choice(PROJECTS)
    p["window"] = rng.choice(WINDOWS)
    p["big"], p["small"] = rng.choice(MODELS_BIG), rng.choice(MODELS_SMALL)
    p["day"] = rng.choice(DAYS)
    p["base_calls"] = rng.choice([12_000, 48_000, 210_000, 640_000, 1_200_000, 3_400_000])
    p["base_cost"] = rng.choice([85, 240, 610, 1_900, 7_400])
    p["base_price"] = rng.choice([0.6, 1.2, 2.5, 3.0, 5.0, 10.0])
    p["ver"] = f"{rng.randint(1, 4)}.{rng.randint(0, 19)}.{rng.randint(0, 9)}"
    return p


# ------------------------------------------------------------ clause banks

def _flat(x):
    """Wording only: a change this small is described as 'flat' in the text."""
    return x is not None and -10 <= x <= 10


def _dir(v, up="up", down="down"):
    return up if v >= 0 else down


def _mult(v):
    return f"{1 + v / 100:.1f}x"


def _human(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


# Each bank entry: fn(p) -> str (a clause) for a KNOWN signal value.
SPEND = [
    lambda p: f"{p['project']} spend is up {p['spend']}% {p['window']}",
    lambda p: f"Cost for {p['project']} jumped {p['spend']}% ({p['window']})",
    lambda p: f"{p['project']} is running at {_mult(p['spend'])} its normal spend ({p['window']})",
    lambda p: f"we are paying {p['spend']}% more than baseline on {p['project']}",
    lambda p: f"Budget alert: {p['project']} is tracking {p['spend']}% above its average",
    lambda p: f"daily LLM cost for {p['project']} went from ${p['base_cost']:,} to ${round(p['base_cost'] * (1 + p['spend'] / 100)):,}",
]
SPEND_KV = lambda p: f"project={p['project']} spend_delta={p['spend']:+d}% window=\"{p['window']}\""

CALLS = [
    lambda p: f"calls {_dir(p['calls'])} {abs(p['calls'])}%" if not _flat(p["calls"]) else f"call count basically flat ({p['calls']:+d}%)",
    lambda p: f"request count went from {_human(p['base_calls'])} to {_human(round(p['base_calls'] * (1 + p['calls'] / 100)))} ({p['calls']:+d}%)",
    lambda p: (f"{_mult(p['calls'])} the usual call volume" if p["calls"] >= 30 else f"call volume about the same as before ({p['calls']:+d}%)" if _flat(p["calls"]) else f"call volume {_dir(p['calls'])} {abs(p['calls'])}%"),
    lambda p: f"{_human(round(p['base_calls'] * (1 + p['calls'] / 100)))} calls in the window versus {_human(p['base_calls'])} before",
    lambda p: f"API calls {_dir(p['calls'], 'rose', 'fell')} by {abs(p['calls'])}%",
]
CALLS_KV = lambda p: f"calls_delta={p['calls']:+d}%"

TRAFFIC = [
    lambda p: f"end-user traffic is {_dir(p['traffic'])} {abs(p['traffic'])}%" if not _flat(p["traffic"]) else f"end-user traffic is flat ({p['traffic']:+d}%)",
    lambda p: f"real customer requests: {p['traffic']:+d}%",
    lambda p: f"product analytics show sessions {_dir(p['traffic'])} {abs(p['traffic'])}% over the same period",
    lambda p: (f"inbound volume from customers is {_mult(p['traffic'])} what it was" if p["traffic"] >= 20 else f"customer-facing volume has not really moved ({p['traffic']:+d}%)" if _flat(p["traffic"]) else f"customer-facing volume {_dir(p['traffic'])} {abs(p['traffic'])}%"),
    lambda p: f"active users {_dir(p['traffic'])} {abs(p['traffic'])}%" if not _flat(p["traffic"]) else f"active users about the same ({p['traffic']:+d}%)",
]
TRAFFIC_KV = lambda p: f"traffic_delta={p['traffic']:+d}%"

UNIQUE = [
    lambda p: f"{p['unique']}% of requests carry a unique prompt hash",
    lambda p: (f"only {p['unique']}% of prompts are distinct, the rest are exact repeats" if p["unique"] <= 50 else f"{p['unique']}% of prompts are distinct"),
    lambda p: f"the dedupe report shows {100 - p['unique']}% of requests repeat an earlier prompt verbatim",
    lambda p: f"unique-request ratio is {p['unique'] / 100:.2f}",
]
UNIQUE_KV = lambda p: f"unique_ratio={p['unique'] / 100:.2f}"

PRICE = [
    lambda p: f"unit price {_dir(p['price'])} {abs(p['price'])}%" if abs(p["price"]) > 4 else f"unit price unchanged ({p['price']:+d}%)",
    lambda p: f"per-1M-token rate ${p['base_price']:.2f} -> ${p['base_price'] * (1 + p['price'] / 100):.2f}",
    lambda p: f"the vendor rate card shows {p['price']:+d}% this period",
    lambda p: (f"pricing is {_dir(p['price'], 'higher', 'lower')} by {abs(p['price'])}% on the invoice line" if abs(p["price"]) > 4 else "effective price per token has not changed"),
]
PRICE_KV = lambda p: f"price_delta={p['price']:+d}%"

MISSING = {
    "calls": ["we have not pulled call counts yet", "no call volume breakdown available", "calls: n/a"],
    "traffic": ["no traffic breakdown is available yet", "we could not get end-user traffic for this window", "traffic: n/a"],
    "unique": ["prompt dedupe has not been run", "no unique-prompt data for this window", "unique_ratio: n/a"],
    "price": ["nobody has checked the price sheet", "unit price not verified", "price: n/a"],
}

EVENTS = {
    "none": ["No deploys or config changes in the window.", "The change log is empty for this period.", "Nothing shipped or reconfigured on our side.",
             "No releases, config edits or quota changes this week.", "Deploy history for {project}: nothing in the window."],
    "noise": ["The status page theme was refreshed and a new analyst was added to the billing alias.", "Only change: the on-call rota was updated.",
              "Docs site redeployed and a dashboard renamed; nothing touching the gateway.", "Certificate renewed on the staging proxy (unrelated)."],
    "agent_deploy": ["The {project} agent v{ver} was deployed {day}.", "A new planner build rolled out to {project}.", "Code release for the {project} agent went out {day}."],
    "cache_disabled": ["Response caching was switched off for {project} on {day}.", "The semantic cache flag was set to false in the {project} gateway config.",
                       "Someone turned off the prompt cache while debugging and it was never re-enabled."],
    "max_tokens_raised": ["The max_tokens default was raised from 1024 to 4096 in the gateway config.", "Output token limit for {project} was increased on {day}.",
                          "A config push lifted the completion cap for {project} from 512 to 2048 tokens."],
    "model_route_changed": ["The default route for {project} now points at {big} instead of {small}.", "Routing rule updated: {project} traffic moved to {big}.",
                            "The team switched {project} from {small} to {big} in settings."],
    "quota_raised": ["The per-key quota for {project} was raised from 100 to 1000 requests per minute.", "Rate quota bumped 10x for the {project} key on {day}.",
                     "Quota change request approved for {project}: concurrency ceiling doubled."],
    "rate_limit_removed": ["The rate limit on the {project} route was removed during load testing.", "Throttle config deleted for {project} in a config push on {day}.",
                           "The per-minute cap on the {project} key was disabled and never restored."],
    "context_cap_raised": ["Context window cap raised from 8k to 32k tokens for {project}.", "The gateway now allows 128k-token prompts for {project} (was 16k).",
                           "Prompt truncation was turned off for {project} on {day}."],
}
EVENT_KV_KEY = "event"

SIGNALS = ["calls", "traffic", "unique", "price"]
BANKS = {"calls": (CALLS, CALLS_KV), "traffic": (TRAFFIC, TRAFFIC_KV), "unique": (UNIQUE, UNIQUE_KV), "price": (PRICE, PRICE_KV)}


# ------------------------------------------------------------------ styles

def _build_styles() -> list[dict]:
    """A fixed, seed-independent table of rendering styles. A style fixes the
    voice (prose or key=value), which bank entry renders each signal, how the
    clauses are joined, what frames the two fields, and which signals go in
    `anomaly` versus `recent_changes`. Built by a private RNG so the table is
    identical in every build."""
    r = random.Random("typryx-evalset|triage-styles")
    prose_frames = [
        ("Heads up: ", "{}.", ". ", "Changes since then: ", ". "),
        ("", "{}.", "; ", "Context: ", "; "),
        ("ALERT - ", "{}", " | ", "Recent changes: ", " | "),
        ("Hi all, ", "{}.", ". ", "For context, ", ". "),
        ("FYI: ", "{}.", ", and ", "Also noted: ", ". "),
        ("Spend anomaly on {project}. ", "{}.", ". ", "What we know about changes: ", ". "),
        ("", "{}", "\n- ", "Changes:\n- ", "\n- "),
        ("Finance flagged this morning: ", "{}.", ". ", "Engineering notes: ", ". "),
        ("Ticket summary - ", "{}.", ". ", "Findings so far: ", ". "),
        ("Dashboard note: ", "{}", "; ", "Timeline: ", "; "),
    ]
    kv_frames = [("alert: ", "{}", " ", "context: ", " "), ("[anomaly] ", "{}", ", ", "[changes] ", ", "), ("", "{}", " | ", "recent: ", " | ")]
    allocations = [
        (["calls"], ["traffic", "unique", "price"]),
        (["calls", "unique"], ["traffic", "price"]),
        (["calls", "traffic"], ["price", "unique"]),
        ([], ["calls", "traffic", "unique", "price"]),
        (["price", "calls"], ["traffic", "unique"]),
        (["unique"], ["calls", "traffic", "price"]),
        (["calls", "unique", "price"], ["traffic"]),
        (["traffic", "calls"], ["unique", "price"]),
    ]
    styles, seen = [], set()
    while len(styles) < 32:
        kv = len(styles) % 6 == 5
        frame = r.choice(kv_frames if kv else prose_frames)
        a_keys, c_keys = r.choice(allocations)
        style = {
            "kv": kv, "frame": frame, "a_keys": a_keys, "c_keys": c_keys,
            "spend_i": r.randrange(len(SPEND)),
            "bank_i": {s: r.randrange(len(BANKS[s][0])) for s in SIGNALS},
            "show_missing": r.random() < 0.5,
            "event_first": r.random() < 0.35,
        }
        key = (kv, frame, tuple(a_keys), tuple(c_keys), style["spend_i"], tuple(style["bank_i"].values()), style["event_first"])
        if key in seen:
            continue
        seen.add(key)
        style["id"] = f"{CODE}.s{len(styles) + 1:02d}"
        styles.append(style)
    return styles


STYLES = _build_styles()


def _cap(s: str, p: dict) -> str:
    if not s or s.startswith(p["project"]):
        return s
    return s[0].upper() + s[1:]


def _lc(s: str, p: dict) -> str:
    """Lower-case a clause's first letter unless it is a name or an acronym."""
    if not s or s.startswith(p["project"]) or not s[0].isupper() or (len(s) > 1 and s[1].isupper()):
        return s
    return s[0].lower() + s[1:]


def _compose(intro: str, parts: list[str], join: str, p: dict) -> str:
    """Join clauses into one field. Sentence-like joins (". " or a new line)
    capitalise every clause and end with a full stop; clause-like joins
    (";", "|", ", and ") keep the clauses lower case after the first."""
    sentence_like = join.startswith(".") or join.startswith("\n")
    if sentence_like:
        parts = [_cap(x.rstrip("."), p) for x in parts]
    else:
        parts = [x.rstrip(".") for x in parts]
        first_capital = intro == "" or intro.endswith((": ", ". ", "- "))
        parts = [_cap(x, p) if (i == 0 and first_capital) else _lc(x, p) for i, x in enumerate(parts)]
    text = intro.format(project=p["project"]) + join.join(parts)
    return text + "." if sentence_like and not join.startswith("\n") else text


def _clause(style: dict, p: dict, sig: str, rng: random.Random) -> str | None:
    bank, kv = BANKS[sig]
    if p[sig] is None:
        if not style["show_missing"]:
            return None
        m = MISSING[sig][2 if style["kv"] else rng.randrange(2)]
        return m
    if style["kv"]:
        return kv(p)
    return bank[style["bank_i"][sig]](p)


def _event_text(style: dict, p: dict, rng: random.Random) -> str:
    text = rng.choice(EVENTS[p["event"]]).format(**{k: p[k] for k in ("project", "ver", "day", "big", "small")})
    if style["kv"]:
        return f"event={p['event']} note=\"{text}\""
    return text


def render(style: dict, p: dict, rng: random.Random) -> tuple[str, str]:
    a_intro, a_fmt, a_join, c_intro, c_join = style["frame"]
    kv = style["kv"]
    spend = SPEND_KV(p) if kv else SPEND[style["spend_i"]](p)
    a_parts = [spend] + [c for c in (_clause(style, p, s, rng) for s in style["a_keys"]) if c]
    c_parts = [c for c in (_clause(style, p, s, rng) for s in style["c_keys"]) if c]
    ev = _event_text(style, p, rng)
    c_parts = [ev] + c_parts if style["event_first"] else c_parts + [ev]
    if kv:
        anomaly = a_intro + a_join.join(a_parts)
        changes = c_intro + c_join.join(c_parts)
    else:
        anomaly = _compose(a_intro, a_parts, a_join, p)
        changes = _compose(c_intro, c_parts, c_join, p)
    return anomaly.strip(), changes.strip()


# --------------------------------------------------------------- generate

def groups() -> list[str]:
    return [s["id"] for s in STYLES]


def generate(seed: int) -> list[Case]:
    rng = rng_for(seed, FAMILY)
    per_label = ROWS_PER_FAMILY // len(LABELS)
    style_ids = groups()
    # Each label's 100 rows are spread over the styles as evenly as possible.
    plan: list[tuple[str, str]] = []
    for lab in LABELS:
        counts = spread(rng, per_label, style_ids)
        for sid in style_ids:
            plan += [(lab, sid)] * counts[sid]
    by_id = {s["id"]: s for s in STYLES}
    cases, seen = [], set()
    for lab, sid in plan:
        for _ in range(100):
            p = draw_params(rng, lab)
            anomaly, changes = render(by_id[sid], p, rng)
            if (anomaly, changes) not in seen:
                break
        else:
            raise RuntimeError("could not draw a distinct scenario")
        seen.add((anomaly, changes))
        cases.append(Case(FAMILY, TEMPLATE, {"anomaly": anomaly, "recent_changes": changes}, lab, sid, p))
    return finalize(cases, rng, TEMPLATE)


def strata() -> dict[str, list[str]]:
    return {"all": groups()}
