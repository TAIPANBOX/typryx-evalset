"""Family 6: console.question_topic (choice: spend / incident / identity /
approval / other).

An operator's question, routed to the Felyx data source that should answer
it. Every label has its own list of phrasing templates (a template, or a few
surface forms of one, is a group); a row's gold is the label of the list its
group came from.

The construction rule the tests recompute: each topic has a vocabulary
(tests/test_labels.py holds the lexicons). A question matches the vocabulary
of its own topic and of no other, except for the few templates marked MIXED
in `MIXED_GROUPS`, where a modifier from a second topic appears but the thing
asked for is still the primary topic's ("Has the budget increase for X been
approved yet?" asks about an approval). `other` matches no lexicon at all.
"""

from __future__ import annotations

from .common import ROWS_PER_FAMILY, Case, fill, finalize, rng_for, spread

FAMILY = "console.question_topic"
TEMPLATE = "console.question_topic"
CODE = "cq"
LABELS = ["spend", "incident", "identity", "approval", "other"]

POOLS: dict[str, list[str]] = {
    "model": ["gpt-4.1", "claude-sonnet", "gemini-2.5-pro", "llama-3.3-70b", "mistral-large", "the small default model"],
    "window": ["24 hours", "7 days", "week", "month", "30 days", "hour"],
    "project": ["support-copilot", "payments-assistant", "doc-summarizer", "code-review-bot", "search-rerank", "sales-enrichment", "fraud-triage", "meeting-notes"],
    "team": ["platform", "payments", "data-eng", "support-tools", "sre", "ml-infra", "growth", "finance-ops"],
    "dim": ["team", "model", "project", "agent", "environment"],
    "day": ["Monday", "Tuesday", "last Thursday", "the 14th", "Friday", "the first of the month"],
    "month": ["August", "September", "July", "June", "last month", "this month"],
    "vendor": ["OpenAI", "Anthropic", "Bedrock", "Vertex AI", "our primary model provider", "the embeddings vendor"],
    "agent": ["payments-bot", "support-triage", "deploy-agent", "doc-extractor", "research-agent", "code-reviewer", "onboarding-assistant", "ticket-router"],
    "cap": ["monthly", "team", "project", "daily", "quarterly"],
    "k": ["3", "5", "10", "7"],
    "service": ["gateway", "checkout-api", "auth-service", "vector store", "search cluster", "ledger-writer", "workflow service"],
    "err": ["5xx", "429", "502", "timeout", "connection reset"],
    "time": ["9am", "noon", "this morning", "Tuesday night", "yesterday at 4pm", "the last deploy"],
    "route": ["/v1/chat", "/v1/embeddings", "/v1/agents/run", "/v1/search", "/v1/tools/call"],
    "date": ["March 12", "last Friday", "the 3rd", "May 28", "Monday", "September 14"],
    "event": ["tonight's release", "the board demo", "the quarter-end run", "tomorrow's migration", "the customer webinar"],
    "env": ["production", "staging", "sandbox"],
    "n": ["30", "60", "90", "14", "7"],
    "tool": ["delete_bucket", "send_email", "stripe.refund", "db.run_query", "k8s.scale", "github.merge"],
    "user": ["dana", "ruben", "priti", "kaveh", "ingrid", "mateo"],
    "thing": ["the vendor contract", "the policy exception", "the production deploy", "the data export", "the new agent rollout", "the retention change"],
    "action": ["refund workflow", "database migration", "bulk email send", "production deploy", "data export", "customer notification"],
    "change": ["config change", "model swap", "access request", "retention policy update", "firewall rule", "schema migration"],
    "person": ["Marta", "the security lead", "Devon", "the CFO", "the on-call manager", "Hana"],
    "policy": ["data residency", "external send", "destructive action", "high-risk tool", "weekend deploy"],
    "amount": ["5,000 euros", "10k", "2,400 dollars", "50 thousand", "1,000 euros"],
    "city": ["Lisbon", "Kyiv", "Toronto", "Osaka", "Berlin", "Nairobi"],
    "topic": ["Mondays", "on-call pagers", "a tired server", "spreadsheets", "coffee", "rubber ducks"],
    "phrase": ["good morning", "see you tomorrow", "thank you for your help", "where is the meeting room", "the report is ready"],
    "language": ["French", "German", "Spanish", "Polish", "Italian"],
    "lang": ["Python", "Go", "TypeScript", "Rust"],
    "thing2": ["a retry", "a router", "a gateway", "a webhook", "an embedding", "a context window"],
}

Templ = str | list[str]

TEMPLATES: dict[str, list[Templ]] = {
    "spend": [
        "How much did we spend on {model} over the last {window}?",
        "what's the burn rate on {project} this month",
        "Which team is over budget right now?",
        "Show token spend by {dim} for the last {window}.",
        "Why did our LLM bill jump on {day}? Was it more calls or a pricier model?",
        "Can you forecast end-of-month spend for {team} if we keep this pace?",
        "Do we have the invoice from {vendor} for {month} yet, and what's the total?",
        "What is the cost per request for {agent} compared with last week?",
        "are we going to hit the {cap} budget cap before Friday",
        "List the {k} most expensive agents by cost over the past {window}.",
        "I need the {month} spend report for finance, split by cost center.",
        "How much budget is left for {project}?",
        "Which models cost us the most per 1k tokens, and how many tokens did each burn?",
        "How much did the {service} outage cost us in extra tokens this week?",
        "What was the invoice total for the month of the {service} incident?",
    ],
    "incident": [
        ["Is the {service} down right now?", "is the {service} down?", "Anyone else seeing the {service} down?"],
        "We're seeing a spike in {err} errors from the {service}, what's going on?",
        "What alerts fired in the last {window}?",
        "Is there an ongoing outage with {vendor}?",
        "latency on the gateway doubled since {time}, is it degraded?",
        ["Show me the open incidents and their severity.", "Which incidents are open right now, and how severe are they?"],
        "When did the {service} outage start, and is it resolved?",
        "why are requests to {model} timing out",
        "Give me the error rate for {route} over the past {window}.",
        "Has the {service} recovered? Users still report failures.",
        "Did the postmortem for the incident on {date} get filed?",
        "{vendor} is returning 529s again, are we failing over?",
        "Any degraded services I should know about before {event}?",
    ],
    "identity": [
        "Which agent identities are active in {env}?",
        "When does the key for {agent} expire?",
        "Did anyone sign in from an unusual location in the last {window}?",
        "Who delegated access to {agent}, and what scopes did they grant?",
        "List credentials that haven't been rotated in {n} days.",
        "Is {agent}'s passport still valid?",
        "I think a key leaked for {agent}, can you show where it was used?",
        "Which service accounts can call {tool}?",
        "Show me suspicious logins for {user}.",
        "Has the delegation chain for {agent} been revoked?",
        "How many API keys does {team} own?",
        "What identity is {agent} using when it calls {vendor}?",
        ["Are there agents registered with no owner?", "which agents have no owner recorded"],
    ],
    "approval": [
        ["What's waiting for my approval?", "anything waiting on me to approve?", "Which requests need my approval?"],
        "Who needs to sign off on {thing}?",
        "Why is {agent}'s {action} on hold?",
        "List pending approvals older than {n} hours.",
        "Has {person} approved the {change} yet?",
        "Which holds are blocking {agent} right now?",
        "Can you release the hold on the {action}? Who has to approve?",
        "How many requests are in the approval queue for {team}?",
        "Who is the approver for {policy} exceptions?",
        "The {action} has been pending since {time}, who do I chase?",
        ["Show me approvals I've already granted this week.", "what have I approved this week"],
        "Do we need a second approver for anything over {amount}?",
        "Which policy put the {tool} call on hold?",
        "Has the budget increase for {project} been approved yet?",
        "Who has to sign off on rotating the key for {agent}?",
        "Is the new identity request for {agent} still waiting for approval?",
    ],
    "other": [
        ["How do I switch the console to dark mode?", "where is the dark mode toggle"],
        "Where can I find the docs for the MCP endpoint?",
        ["What can you help me with?", "what do you do exactly", "what can i ask you here"],
        ["hello", "hi there", "hey"],
        ["thanks, that's all for now", "thank you, nothing else", "great, thanks!"],
        "Can you explain what a router task class is?",
        "How do I export a table to CSV?",
        "What's the keyboard shortcut for search?",
        ["Who built this console?", "who maintains this tool"],
        "What's the weather like in {city} today?",
        "Write me a haiku about {topic}.",
        "How do I set my timezone in the console?",
        "Translate \"{phrase}\" into {language}.",
        "Explain what {thing2} is in one paragraph.",
        "Which language would you use to write a small CLI, {lang} or something else?",
        "The sidebar scrolls weirdly on my laptop, is that a known bug?",
    ],
}

#: Groups whose question carries a modifier from a second topic.
MIXED_GROUPS = {
    "spend": [13, 14],       # 0-based indexes into TEMPLATES["spend"]
    "approval": [13, 14, 15],
}

PREFIXES = ["Hey, ", "Hi, ", "Quick question: ", "Sorry to ask, ", "Hello, ", "Hey team, ", "One thing: "]
SUFFIXES = [" Thanks!", " thx", " please", " asap", " Cheers.", " Thank you."]
WRAP_P = 0.25


def groups() -> dict[str, list[str]]:
    return {lab: [f"{CODE}.{lab}.{i:02d}" for i in range(1, len(TEMPLATES[lab]) + 1)] for lab in LABELS}


def mixed_group_ids() -> list[str]:
    g = groups()
    return [g[lab][i] for lab, idxs in MIXED_GROUPS.items() for i in idxs]


def _wrap(text: str, rng) -> str:
    if rng.random() < WRAP_P:
        pre = rng.choice(PREFIXES)
        text = pre + text[0].lower() + text[1:]
    if rng.random() < WRAP_P:
        text += rng.choice(SUFFIXES)
    if rng.random() < 0.15:
        text = text.lower()
    return text


def generate(seed: int) -> list[Case]:
    rng = rng_for(seed, FAMILY)
    per_label = ROWS_PER_FAMILY // len(LABELS)
    mixed = set(mixed_group_ids())
    cases: list[Case] = []
    seen: set[str] = set()
    for lab in LABELS:
        gids = groups()[lab]
        counts = spread(rng, per_label, gids)
        for gi, gid in enumerate(gids):
            tpl = TEMPLATES[lab][gi]
            forms = tpl if isinstance(tpl, list) else [tpl]
            for _ in range(counts[gid]):
                for _try in range(300):
                    text, slots = fill(rng.choice(forms), POOLS, rng)
                    text = _wrap(text, rng)
                    if text not in seen:
                        break
                else:
                    raise RuntimeError(f"{gid}: cannot draw {counts[gid]} distinct questions")
                seen.add(text)
                cases.append(Case(FAMILY, TEMPLATE, {"question": text}, lab, gid, {"slots": slots, "mixed": gid in mixed}))
    return finalize(cases, rng, TEMPLATE)


def strata() -> dict[str, list[str]]:
    return groups()
