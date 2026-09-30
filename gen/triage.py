"""Family 2: triage.anomaly_class.

Each row starts from numeric scenario parameters, the label is a deterministic
function of them (`classify`), and the parameters are RENDERED as operator
text by one of many rendering styles (the row's group). Every style can render
every label, so the group carries no label information; the model has to read
the numbers.

Parameters (percent deltas against the prior period unless noted):

    spend    headline spend change (always shown, never used by `classify`)
    calls    change in call count, or None if not known
    traffic  change in real end-user traffic, or None
    unique   share of requests with a distinct prompt, 0..100, or None
    price    change in unit price, or None
    event    "none" | "noise" | "agent_deploy" | a SETTING_EVENTS kind

Class signatures (a class matches only if its REQUIRED signals are known and
satisfy it, and every signal it EXCLUDES on, if known, is clear of it):

    price_change     price >= +10, calls flat; traffic (if known) flat; quiet event
    expected_growth  traffic >= +20, calls within 15 points of traffic;
                     price ~0 and unique >= 50 (if known); quiet event
    runaway_agent    calls >= +100, unique <= 25, traffic flat;
                     price ~0 (if known); event none/noise/agent_deploy
    misconfiguration a setting event, traffic flat; price ~0 (if known),
                     unique >= 40 (if known), calls < +100 (if known)

"flat" = within +-10, "~0" = within +-4. The label is the one matching class,
and `unknown` when none matches (insufficient or in-between evidence) or when
more than one does (contradictory). `unknown` rows are built on purpose in
three flavours: hidden required signals, contradictory evidence, gray zone.
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
RUNAWAY_OK_EVENTS = ["none", "noise", "agent_deploy"]
ALL_EVENTS = ["none", "noise", "agent_deploy"] + SETTING_EVENTS


# ---------------------------------------------------------------- the label

def _flat(x):
    return x is not None and -10 <= x <= 10


def matching_classes(p: dict) -> list[str]:
    c, t, u, pr, e = p["calls"], p["traffic"], p["unique"], p["price"], p["event"]
    out = []
    if pr is not None and pr >= 10 and _flat(c) and (t is None or _flat(t)) and e in QUIET_EVENTS:
        out.append("price_change")
    if (t is not None and t >= 20 and c is not None and abs(c - t) <= 15
            and (pr is None or abs(pr) <= 4) and (u is None or u >= 50) and e in QUIET_EVENTS):
        out.append("expected_growth")
    if (c is not None and c >= 100 and u is not None and u <= 25 and _flat(t)
            and (pr is None or abs(pr) <= 4) and e in RUNAWAY_OK_EVENTS):
        out.append("runaway_agent")
    if (e in SETTING_EVENTS and _flat(t) and (pr is None or abs(pr) <= 4)
            and (u is None or u >= 40) and (c is None or c < 100)):
        out.append("misconfiguration")
    return out


def classify(p: dict) -> str:
    m = matching_classes(p)
    return m[0] if len(m) == 1 else "unknown"


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


def _draw_base(rng, cls: str) -> dict:
    """Parameters inside one class's region; `classify` must agree (the
    caller re-checks and retries)."""
    p = {"calls": None, "traffic": None, "unique": None, "price": None, "event": "none"}
    if cls == "expected_growth":
        t = _rint(rng, 20, 260)
        p.update(traffic=t, calls=t + _rint(rng, -12, 12), price=_rint(rng, -4, 4),
                 unique=_rint(rng, 50, 95), event=rng.choice(QUIET_EVENTS))
        p["spend"] = t + _rint(rng, -8, 14)
        optional = ["price", "unique"]
    elif cls == "runaway_agent":
        c = int(100 * 10 ** rng.uniform(0, 1.2))
        p.update(calls=c, traffic=_rint(rng, -8, 8), unique=_rint(rng, 2, 25), price=_rint(rng, -4, 4),
                 event=rng.choice(RUNAWAY_OK_EVENTS))
        p["spend"] = c + _rint(rng, -10, 12)
        optional = ["price"]
    elif cls == "price_change":
        pr = _rint(rng, 10, 120)
        p.update(price=pr, calls=_rint(rng, -8, 8), traffic=_rint(rng, -8, 8), unique=_rint(rng, 40, 95),
                 event=rng.choice(QUIET_EVENTS))
        p["spend"] = pr + _rint(rng, -4, 6)
        optional = ["traffic", "unique"]
    elif cls == "misconfiguration":
        p.update(event=rng.choice(SETTING_EVENTS), traffic=_rint(rng, -8, 8), price=_rint(rng, -4, 4),
                 unique=_rint(rng, 40, 95), calls=_rint(rng, -5, 80))
        p["spend"] = _rint(rng, 30, 320)
        optional = ["price", "unique", "calls"]
    else:
        raise ValueError(cls)
    if rng.random() < 0.3:
        p[rng.choice(optional)] = None
    return p


def _draw_unknown(rng) -> dict:
    """Three flavours of `unknown`: hidden required signals, contradictory
    evidence, and a gray zone where nothing crosses a threshold."""
    flavour = rng.choice(["hidden", "hidden", "contradict", "contradict", "gray", "gray", "blank"])
    if flavour == "hidden":
        base = rng.choice(["expected_growth", "runaway_agent", "price_change", "misconfiguration"])
        p = _draw_base(rng, base)
        required = {"expected_growth": ["traffic", "calls"], "runaway_agent": ["traffic", "unique", "calls"],
                    "price_change": ["price", "calls"], "misconfiguration": ["traffic"]}[base]
        if base == "misconfiguration":
            p["traffic"] = None
        else:
            for k in rng.sample(required, rng.choice([1, 1, 2])):
                p[k] = None
        if rng.random() < 0.4:
            p[rng.choice(["price", "unique", "calls", "traffic"])] = None
        return p
    if flavour == "contradict":
        kind = rng.choice(["price_and_growth", "runaway_with_setting", "growth_with_setting", "calls_without_traffic", "price_and_runaway"])
        if kind == "price_and_growth":   # usage and price both moved
            t = _rint(rng, 30, 120)
            p = dict(traffic=t, calls=t + _rint(rng, -6, 6), price=_rint(rng, 12, 60), unique=_rint(rng, 55, 90), event="none")
            p["spend"] = t + p["price"]
        elif kind == "runaway_with_setting":  # looping calls, but a config change too
            c = _rint(rng, 120, 900)
            p = dict(calls=c, traffic=_rint(rng, -6, 6), unique=_rint(rng, 4, 22), price=_rint(rng, -3, 3), event=rng.choice(SETTING_EVENTS))
            p["spend"] = c
        elif kind == "growth_with_setting":
            t = _rint(rng, 30, 150)
            p = dict(traffic=t, calls=t + _rint(rng, -8, 8), unique=_rint(rng, 55, 90), price=_rint(rng, -3, 3), event=rng.choice(SETTING_EVENTS))
            p["spend"] = t + _rint(rng, 0, 40)
        elif kind == "calls_without_traffic":  # calls far above traffic but diverse prompts, no config
            t = _rint(rng, 25, 60)
            p = dict(traffic=t, calls=t + _rint(rng, 70, 400), unique=_rint(rng, 55, 90), price=_rint(rng, -3, 3), event="none")
            p["spend"] = p["calls"] // 2 + 20
        else:  # price_and_runaway
            c = _rint(rng, 110, 500)
            p = dict(calls=c, traffic=_rint(rng, -5, 5), unique=_rint(rng, 4, 20), price=_rint(rng, 10, 50), event="none")
            p["spend"] = c + p["price"]
        return p
    if flavour == "gray":
        p = dict(calls=_rint(rng, 11, 60), traffic=_rint(rng, 11, 19), unique=_rint(rng, 26, 39), price=_rint(rng, 5, 9),
                 event=rng.choice(QUIET_EVENTS))
        p["spend"] = _rint(rng, 25, 90)
        for k in rng.sample(["calls", "traffic", "unique", "price"], rng.choice([0, 0, 1])):
            p[k] = None
        return p
    # blank: a headline and nothing else
    p = dict(calls=None, traffic=None, unique=None, price=None, event=rng.choice(ALL_EVENTS))
    p["spend"] = _rint(rng, 25, 400)
    return p


def draw_params(rng: random.Random, label: str) -> dict:
    for _ in range(500):
        p = _draw_unknown(rng) if label == "unknown" else _draw_base(rng, label)
        if classify(p) == label:
            break
    else:
        raise RuntimeError(f"cannot draw parameters for {label}")
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
