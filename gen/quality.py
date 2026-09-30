"""Family 4: eval.answer_quality (score 0..3).

A task asks for N concrete items ("List four causes of X"). Each task topic
has a fixed fact bank of six clear, correct facts. An answer gives k of the N
items, every one of them a clear correct fact from the bank (no vague items
are generated: readers did not perceive them as vague). The level is a pure
function of k and N (`level_of`):

    3  all N items given
    2  exactly N-1 given, only for N >= 4
    1  at least one given but at most half of N (1 of 3, 1 or 2 of 4, 1 or 2 of 5)
    0  off-topic: items from another topic, or a non-answer

The in-between shares (2 of 3, 3 of 5) are never generated. A group is one
topic (its task phrasing and fact bank); every topic renders every level, so a
split by group tests generalisation to unseen topics. Length and item count
are NOT a proxy for the level on purpose: neutral filler sentences pad answers
of any level up to a length drawn from one shared distribution.
"""

from __future__ import annotations

from .common import Case, finalize, rng_for, spread

FAMILY = "eval.answer_quality"
TEMPLATE = "eval.answer_quality"
CODE = "aq"
LABELS = [0, 1, 2, 3]
ROWS_PER_LEVEL = 125
NUMBER_WORDS = {3: "three", 4: "four", 5: "five"}

# (slug, [task phrasings with {n}], [six clear facts])
TOPICS = [
    ("spend_spike", ["List {n} common causes of a sudden spike in LLM spend.", "What are {n} likely reasons an LLM bill suddenly jumps?"], [
        "An agent stuck in a retry loop keeps re-sending the same request",
        "Caching was switched off, so every request pays full price",
        "Traffic grew because a new feature or customer launched",
        "The default route moved to a more expensive model",
        "Prompts grew longer because more context is stuffed into each call",
        "The vendor raised its per-token price",
    ]),
    ("rotate_key", ["Give {n} steps to rotate an API key safely.", "What {n} things should you do when rotating an API key?"], [
        "Create the new key before revoking the old one",
        "Update every service that uses the key to the new value",
        "Confirm traffic succeeds with the new key",
        "Revoke the old key once nothing uses it",
        "Store the new key in a secrets manager, not in code",
        "Record the rotation in the audit log",
    ]),
    ("stuck_loop", ["Name {n} signs that an agent is stuck in a loop.", "How can you tell an agent is looping? Give {n} signs."], [
        "The same tool call repeats with identical arguments",
        "Token usage climbs while no new output appears",
        "The plan never advances past the same step",
        "Identical prompt hashes dominate the request log",
        "Latency per task keeps growing until it times out",
        "It alternates between two states, undoing its own edits",
    ]),
    ("policy_hold", ["List {n} reasons a tool call might be put on hold by policy.", "Why might an agent's action be held for approval? Give {n} reasons."], [
        "The action is destructive, such as deleting data",
        "It would send data outside the organisation",
        "The amount exceeds the spending threshold for that agent",
        "The agent lacks the scope required for that tool",
        "It targets production outside the change window",
        "The caller's identity could not be verified",
    ]),
    ("http_429", ["Give {n} things to check when an API keeps returning 429 errors.", "An API returns 429s. What {n} things would you look at first?"], [
        "Whether your client exceeds the documented rate limit",
        "Whether several services share one key and its quota",
        "Whether retries lack backoff and amplify the load",
        "The Retry-After header for when to try again",
        "Whether a recent deploy increased request volume",
        "Whether the provider's plan tier lowered your limit",
    ]),
    ("reduce_tokens", ["List {n} ways to reduce prompt token usage.", "How can a team cut down the tokens it sends per request? Name {n} ways."], [
        "Trim repeated boilerplate from the system prompt",
        "Retrieve only the relevant chunks instead of whole documents",
        "Summarise long conversation history instead of resending it",
        "Cache stable prefixes so they are not billed repeatedly",
        "Set a sensible max_tokens so replies stay bounded",
        "Route simple requests to a smaller model",
    ]),
    ("p99_latency", ["What are {n} common causes of high p99 latency in an LLM gateway?", "Give {n} reasons the slowest requests through a gateway get so slow."], [
        "A slow upstream provider during peak hours",
        "Queueing because concurrency limits are too low",
        "Very large prompts with long completions",
        "Cold connections because keep-alive is disabled",
        "Retries and failover adding whole extra round trips",
        "Garbage collection or lock contention inside the gateway",
    ]),
    ("leaked_credential", ["Give {n} steps to take after discovering a leaked credential.", "A credential leaked. List {n} actions to take."], [
        "Revoke or disable the credential immediately",
        "Issue a replacement and deploy it to legitimate users",
        "Search the logs for any use of the leaked credential",
        "Find and remove the place it leaked, such as a public repo",
        "Notify the owner and the security team",
        "Write a short incident report and fix the process gap",
    ]),
    ("broad_credentials", ["Name {n} risks of giving an agent broad delegated credentials.", "What are {n} dangers of an agent holding wide-ranging credentials?"], [
        "A prompt injection can trigger actions far beyond the task",
        "One leaked token exposes every system it can reach",
        "Agent mistakes can delete or change production data",
        "Actions are hard to attribute to a specific task or person",
        "Compliance scopes are violated when data crosses boundaries",
        "Revoking access for one task means revoking it for all",
    ]),
    ("postmortem", ["List {n} sections a blameless postmortem should include.", "What {n} sections belong in a blameless postmortem?"], [
        "A timeline of events with timestamps",
        "The customer impact and how long it lasted",
        "Contributing factors rather than a single root cause",
        "How the problem was detected and what should have caught it",
        "Action items with owners and due dates",
        "What went well during the response",
    ]),
    ("safe_retries", ["Give {n} practices that make retries safe.", "What {n} practices keep a retry policy from causing harm?"], [
        "Use idempotency keys so repeats do not duplicate effects",
        "Back off exponentially with jitter between attempts",
        "Cap the number of attempts and the total time",
        "Retry only transient errors, not validation failures",
        "Use a circuit breaker to stop hammering a failing service",
        "Emit metrics on retry counts to spot storms early",
    ]),
    ("failed_migration", ["What are {n} common causes of a failed database migration?", "Name {n} reasons a schema migration goes wrong in production."], [
        "A long lock on a large table blocks live traffic",
        "The schema change is incompatible with the running code version",
        "Existing data violates a new constraint and was never cleaned",
        "The migration runs out of disk space or memory",
        "No tested rollback path exists",
        "Replication lag leaves replicas serving stale data",
    ]),
    ("onboard_agent", ["Give {n} steps to onboard a new agent identity.", "List {n} things to do when bringing a new agent into the platform."], [
        "Register the agent with a unique, named identity",
        "Assign a human owner who is accountable for it",
        "Grant only the minimum scopes the agent needs",
        "Issue a short-lived credential bound to that identity",
        "Set a spending cap and rate limits",
        "Turn on logging so its actions are auditable",
    ]),
    ("cache_hit_drop", ["List {n} reasons a prompt cache hit rate might drop.", "Why could a cache hit rate suddenly fall? Give {n} reasons."], [
        "A prompt prefix changed, such as a timestamp inserted at the top",
        "The cache TTL expired during low traffic",
        "A deploy flushed the cache",
        "Requests spread across more models or regions",
        "Personalised content made every prompt unique",
        "The cache was resized and is evicting entries",
    ]),
    ("delete_bucket", ["Give {n} things to check before deleting a storage bucket.", "Before deleting a bucket, which {n} checks would you make?"], [
        "That no service or job still reads or writes it",
        "That a backup or copy of the data exists",
        "Retention and legal hold requirements",
        "That the owner knows and approves",
        "Whether versioning or replication keeps extra copies",
        "That its name is not referenced in configuration or DNS",
    ]),
    ("prompt_injection", ["Name {n} signs of a prompt injection attempt.", "What {n} signs suggest someone is attempting prompt injection?"], [
        "Input text telling the model to ignore its previous instructions",
        "A document with hidden or invisible text aimed at the model",
        "A sudden request to reveal the system prompt or secrets",
        "Tool calls the user's task never called for",
        "Outputs containing unexpected links or encoded data",
        "Text impersonating the developer or an admin",
    ]),
    ("flaky_tests", ["What are {n} common causes of flaky tests?", "List {n} reasons a test passes sometimes and fails other times."], [
        "Tests depend on real time or sleep statements",
        "Shared state leaks between tests",
        "Order-dependent tests that only pass in one sequence",
        "Network calls to services that are not mocked",
        "Race conditions in asynchronous code",
        "Test data that collides, such as fixed IDs",
    ]),
    ("oncall_prep", ["List {n} things to do before starting an on-call shift.", "You are about to go on call. Name {n} things to prepare."], [
        "Read the handoff notes from the previous engineer",
        "Check that paging and VPN access work",
        "Review open incidents and recent deploys",
        "Know where the runbooks and escalation contacts live",
        "Make sure your laptop is charged and you are reachable",
        "Confirm who your secondary is",
    ]),
    ("choose_model", ["Name {n} factors to weigh when choosing a model for a task.", "What {n} factors matter when picking an LLM for a job?"], [
        "Quality on your own evaluation set, not just public benchmarks",
        "Cost per million tokens at your expected volume",
        "Latency, including tail latency under load",
        "Context window size versus your longest inputs",
        "Data handling terms and where the data is processed",
        "Availability and rate limits from the provider",
    ]),
    ("runaway_batch", ["Give {n} ways to detect a runaway batch job.", "How would you spot a batch job that has gone off the rails? Name {n} signals."], [
        "Runtime far exceeds the historical median",
        "Spend or token counters grow faster than the baseline",
        "Progress metrics stall while resource use stays high",
        "The same records are processed repeatedly",
        "Queue depth or error counts climb without bound",
        "A budget alert fires for the job's cost centre",
    ]),
    ("memory_leak", ["List {n} common causes of memory leaks in a long-running service.", "What are {n} typical sources of a slow memory leak in a server?"], [
        "Caches that grow without eviction",
        "Event listeners or callbacks that are never removed",
        "Connections or file handles that are never closed",
        "Global collections that keep references to old objects",
        "Goroutines or threads that never exit",
        "Large buffers held by slow consumers",
    ]),
    ("runbook", ["Name {n} things every runbook should include.", "What {n} elements make a runbook useful at 3 a.m.?"], [
        "A clear description of the symptom and how to confirm it",
        "Step-by-step commands for diagnosis",
        "Safe mitigation steps and their risks",
        "Escalation contacts and when to use them",
        "A rollback procedure",
        "Links to the relevant dashboards and logs",
    ]),
    ("rollback", ["Give {n} steps to roll back a bad deploy.", "A deploy went bad. List {n} steps to roll it back."], [
        "Announce the rollback in the incident channel",
        "Identify the last known good version",
        "Redeploy that version through the normal pipeline",
        "Verify health checks and error rates recover",
        "Check whether database changes need reverting too",
        "Freeze further deploys until the cause is understood",
    ]),
    ("tls_errors", ["What are {n} causes of TLS certificate errors?", "List {n} reasons a client rejects a server's TLS certificate."], [
        "The certificate has expired",
        "The hostname does not match the certificate's names",
        "The chain is missing an intermediate certificate",
        "The client's clock is badly wrong",
        "The certificate authority is not trusted by the client",
        "The certificate was revoked",
    ]),
    ("rate_limit_benefits", ["List {n} benefits of rate limiting an API.", "Why rate limit an API? Give {n} benefits."], [
        "It protects the service from overload",
        "It stops one client from starving the others",
        "It caps the cost of abusive or buggy clients",
        "It slows brute-force attacks on credentials",
        "It makes capacity planning more predictable",
        "It gives clients a clear signal to back off",
    ]),
    ("data_drift", ["Give {n} causes of data drift in a deployed model.", "What are {n} reasons a model's input data drifts after launch?"], [
        "User behaviour changes over time",
        "An upstream system changes its data format",
        "Seasonality shifts the input distribution",
        "A new customer segment appears in the traffic",
        "A pipeline bug silently corrupts a feature",
        "Labels are produced with a changed definition",
    ]),
    ("bug_report", ["Give {n} things a good bug report includes.", "What {n} details make a bug report actionable?"], [
        "Exact steps to reproduce the problem",
        "What you expected versus what actually happened",
        "Environment details such as version and operating system",
        "Logs or screenshots that show the failure",
        "How often it happens",
        "The impact and urgency",
    ]),
    ("secure_webhook", ["Name {n} ways to secure a webhook endpoint.", "How do you harden a webhook receiver? Give {n} measures."], [
        "Verify a signature on every request",
        "Reject old timestamps to prevent replays",
        "Accept HTTPS only",
        "Restrict source IPs where the sender publishes them",
        "Respond quickly and process the payload asynchronously",
        "Rotate the signing secret periodically",
    ]),
    ("feature_flags", ["List {n} reasons to use feature flags.", "What {n} benefits do feature flags give a team?"], [
        "Ship code dark and enable it later",
        "Roll out gradually to a percentage of users",
        "Turn a broken feature off without a deploy",
        "Run experiments and A/B tests",
        "Give beta customers early access",
        "Separate deploy from release to reduce risk",
    ]),
    ("disk_full", ["What are {n} common causes of a server's disk filling up?", "Name {n} reasons a disk fills up unexpectedly."], [
        "Logs growing without rotation",
        "Temporary files that are never cleaned up",
        "Database write-ahead logs or backups accumulating",
        "Container images and volumes piling up",
        "Core dumps from repeated crashes",
        "A runaway process writing output endlessly",
    ]),
    ("code_review", ["Give {n} tips for a good code review.", "List {n} habits of a helpful code reviewer."], [
        "Read the description and understand the intent first",
        "Keep reviews small",
        "Comment on behaviour and risk, not style nitpicks",
        "Suggest alternatives instead of only objecting",
        "Check that tests cover the change",
        "Respond promptly so the author is not blocked",
    ]),
    ("productive_meeting", ["List {n} ways to run a more productive meeting.", "Give {n} tips for making meetings worth everyone's time."], [
        "Share a clear agenda beforehand",
        "Invite only the people who need to be there",
        "Timebox each topic",
        "Assign an owner and a deadline to every action item",
        "Start and end on time",
        "Write and share notes afterwards",
    ]),
    ("day_hike", ["Name {n} things to pack for a day hike.", "What {n} items belong in a day-hike backpack?"], [
        "Enough water for the whole trip",
        "A map or offline navigation",
        "Layers of clothing for changing weather",
        "A basic first aid kit",
        "Sun protection such as a hat and sunscreen",
        "Snacks with enough calories",
    ]),
    ("better_sleep", ["Give {n} habits that improve sleep.", "List {n} things that help people sleep better."], [
        "Keep a consistent bedtime and wake time",
        "Avoid caffeine in the afternoon",
        "Keep the bedroom dark, cool and quiet",
        "Turn off screens an hour before bed",
        "Get daylight and exercise during the day",
        "Avoid heavy meals late at night",
    ]),
]

NON_ANSWERS = [
    "I'm not sure about that one, you may want to check the documentation.",
    "That really depends on your setup, so it is hard to say in general.",
    "Could you clarify which system you mean before I answer?",
    "I don't have enough information to answer that.",
    "Good question. Probably best to ask someone on the team who knows it well.",
    "It varies a lot, and there is no single answer I would stand behind.",
    "Let's circle back on this later, I want to look into it properly first.",
]
INTROS = ["Sure, here you go.", "Of course.", "Good question.", "Happy to help.", "", "", "", "Here is my answer.", "Short version:"]
#: Neutral padding, used to bring an answer of ANY level up to a length target
#: drawn from one shared distribution, so word count does not track the level.
FILLERS = [
    "Hope that helps.", "Happy to go deeper if that is useful.", "Let me know if you want more detail.",
    "This is a topic where the details matter.", "I can also put this into a checklist if you like.",
    "It is worth revisiting this from time to time.", "There is usually more nuance in a real system.",
    "Feel free to ask a follow-up.", "I kept this as brief as I could.", "Your situation may differ a little.",
    "This is based on what I have usually seen.", "Tell me if you want an example.", "I can expand on any part of that.",
    "That is the general picture.", "Thanks for asking.", "This answer is meant as a starting point.",
    "Different teams weigh these differently.", "I am happy to adjust the format if you prefer.",
    "It helps to write this down somewhere visible.", "Let me know how it goes.",
]
TARGET_WORDS = (18, 60)
INTRO_P = 0.5


def level_of(n_asked: int, given: int, offtopic: bool) -> int:
    """The scoring rule: how much of the task is done, `given` being the number
    of correct clear items in the answer.

    3: all N. 2: exactly N-1, only for N >= 4. 1: at least one but at most
    half of N. 0: off-topic. Shares in between (2 of 3, 3 of 5) are not
    defined and never generated."""
    if offtopic:
        return 0
    if not 1 <= given <= n_asked:
        raise ValueError(f"no level for asked={n_asked} given={given}")
    if given == n_asked:
        return 3
    if given == n_asked - 1 and n_asked >= 4:
        return 2
    if 2 * given <= n_asked:
        return 1
    raise ValueError(f"no level for asked={n_asked} given={given}")


def groups() -> list[str]:
    return [f"{CODE}.{slug}" for slug, _, _ in TOPICS]


def _items_text(rng, items: list[str]) -> str:
    style = rng.choice(["numbered", "bullets", "ordinal", "prose", "lines", "semicolon"])
    cap = [x[0].upper() + x[1:] for x in items]
    if style == "numbered":
        return "\n".join(f"{i}. {x}" for i, x in enumerate(cap, 1))
    if style == "bullets":
        return "\n".join(f"- {x}" for x in cap)
    if style == "lines":
        return "\n".join(f"{x}." for x in cap)
    if style == "ordinal":
        words = ["First", "Second", "Third", "Fourth", "Fifth"]
        return " ".join(f"{words[i]}, {x[0].lower() + x[1:]}." for i, x in enumerate(cap))
    if style == "semicolon":
        lows = [x[0].lower() + x[1:] for x in cap]
        if len(lows) == 1:
            return cap[0] + "."
        return cap[0] + "; " + "; ".join(lows[1:-1] + ["and " + lows[-1]]) + "." if len(lows) > 2 else cap[0] + "; and " + lows[-1] + "."
    return " ".join(f"{x}." for x in cap)


def _pad(rng, parts: list[str], body_index: int, target: int) -> list[str]:
    pool = list(FILLERS)
    rng.shuffle(pool)
    while sum(len(x.split()) for x in parts) < target and pool:
        parts.append(pool.pop())
    return parts


def _compose(rng, items: list[str] | None, target: int) -> str:
    parts = []
    if rng.random() < INTRO_P:
        intro = rng.choice(INTROS)
        if intro:
            parts.append(intro)
    parts.append(rng.choice(NON_ANSWERS) if items is None else _items_text(rng, items))
    body = parts[-1]
    parts = _pad(rng, parts, len(parts) - 1, target)
    sep = "\n" if "\n" in body else " "
    return sep.join(parts)


def _draw_shape(rng, level: int) -> tuple[int, int]:
    """(N asked, items given) for a level; never an in-between share."""
    if level == 3:
        n = rng.choice([3, 4, 5])
        return n, n
    if level == 2:
        n = rng.choice([4, 5])
        return n, n - 1
    if level == 1:
        n = rng.choice([3, 4, 5])
        return n, rng.randint(1, n // 2)
    return rng.choice([3, 4, 5]), 0


def generate(seed: int) -> list[Case]:
    rng = rng_for(seed, FAMILY)
    gids = groups()
    cases: list[Case] = []
    seen: set[tuple[str, str]] = set()
    for level in LABELS:
        counts = spread(rng, ROWS_PER_LEVEL, gids)
        for gi, gid in enumerate(gids):
            slug, phrasings, bank = TOPICS[gi]
            for _ in range(counts[gid]):
                for _try in range(200):
                    n, given = _draw_shape(rng, level)
                    task = rng.choice(phrasings).format(n=NUMBER_WORDS[n])
                    order = rng.sample(range(len(bank)), len(bank))
                    offtopic = level == 0
                    other = None
                    if not offtopic:
                        chosen = [bank[i] for i in order[:given]]
                    elif rng.random() < 0.7:
                        other = rng.choice([t for t in range(len(TOPICS)) if t != gi])
                        oorder = rng.sample(range(len(TOPICS[other][2])), len(TOPICS[other][2]))
                        chosen = [TOPICS[other][2][i] for i in oorder[:n]]
                    else:
                        chosen = None
                    answer = _compose(rng, chosen, rng.randint(*TARGET_WORDS))
                    if (task, answer) not in seen:
                        break
                else:
                    raise RuntimeError(f"{gid}: cannot draw distinct items")
                seen.add((task, answer))
                params = {"n": n, "given": given, "offtopic": offtopic,
                          "other_topic": None if other is None else TOPICS[other][0], "topic": slug, "answer_items": chosen or []}
                cases.append(Case(FAMILY, TEMPLATE, {"task": task, "final_answer": answer}, level, gid, params))
    return finalize(cases, rng, TEMPLATE)


def strata() -> dict[str, list[str]]:
    return {"all": groups()}
