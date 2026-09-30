"""Family 4: eval.answer_quality (score 0..3).

A task asks for N concrete items ("List four causes of X"). Each task topic
has a fixed fact bank: six facts, each with a CLEAR wording and a VAGUE one.
The answer is built at a level, and the level is a pure function of how the
answer was built (`level_of`):

    defects = missing items + vague items (N - clear items)
    3  no defects
    2  exactly one defect and N >= 4, or exactly one vague item (none missing) when N = 3
    1  at least one correct clear item, but more defects than level 2 allows
    0  off-topic: items from another topic, or a non-answer

A group is one topic (its task phrasing and fact bank). Every topic renders
every level, so a split by group tests generalisation to unseen topics.
Length and item count are NOT a proxy for the level on purpose: neutral
filler sentences pad answers of any level.
"""

from __future__ import annotations

from .common import Case, finalize, rng_for, spread

FAMILY = "eval.answer_quality"
TEMPLATE = "eval.answer_quality"
CODE = "aq"
LABELS = [0, 1, 2, 3]
ROWS_PER_LEVEL = 125
NUMBER_WORDS = {3: "three", 4: "four", 5: "five"}

# (slug, [task phrasings with {n}], [(clear, vague) x 6])
TOPICS = [
    ("spend_spike", ["List {n} common causes of a sudden spike in LLM spend.", "What are {n} likely reasons an LLM bill suddenly jumps?"], [
        ("An agent stuck in a retry loop keeps re-sending the same request", "Some agent doing something over and over"),
        ("Caching was switched off, so every request pays full price", "A setting changed somewhere"),
        ("Traffic grew because a new feature or customer launched", "More people using things"),
        ("The default route moved to a more expensive model", "Different models being used"),
        ("Prompts grew longer because more context is stuffed into each call", "The requests got bigger somehow"),
        ("The vendor raised its per-token price", "Pricing is probably different now")]),
    ("rotate_key", ["Give {n} steps to rotate an API key safely.", "What {n} things should you do when rotating an API key?"], [
        ("Create the new key before revoking the old one", "Make a replacement at some point"),
        ("Update every service that uses the key to the new value", "Change things where it is used"),
        ("Confirm traffic succeeds with the new key", "Check that stuff still works"),
        ("Revoke the old key once nothing uses it", "Get rid of the old one eventually"),
        ("Store the new key in a secrets manager, not in code", "Keep it somewhere sensible"),
        ("Record the rotation in the audit log", "Write down that it happened")]),
    ("stuck_loop", ["Name {n} signs that an agent is stuck in a loop.", "How can you tell an agent is looping? Give {n} signs."], [
        ("The same tool call repeats with identical arguments", "It keeps doing the same sort of thing"),
        ("Token usage climbs while no new output appears", "Usage looks high"),
        ("The plan never advances past the same step", "It does not progress well"),
        ("Identical prompt hashes dominate the request log", "The logs look repetitive"),
        ("Latency per task keeps growing until it times out", "Things take a long while"),
        ("It alternates between two states, undoing its own edits", "It seems to go back and forth")]),
    ("policy_hold", ["List {n} reasons a tool call might be put on hold by policy.", "Why might an agent's action be held for approval? Give {n} reasons."], [
        ("The action is destructive, such as deleting data", "It could be risky"),
        ("It would send data outside the organisation", "It involves other people somehow"),
        ("The amount exceeds the spending threshold for that agent", "Money is involved in some way"),
        ("The agent lacks the scope required for that tool", "Permissions are off"),
        ("It targets production outside the change window", "The timing is wrong"),
        ("The caller's identity could not be verified", "Something about who is asking")]),
    ("http_429", ["Give {n} things to check when an API keeps returning 429 errors.", "An API returns 429s. What {n} things would you look at first?"], [
        ("Whether your client exceeds the documented rate limit", "Whether you are going too fast"),
        ("Whether several services share one key and its quota", "How the keys are set up"),
        ("Whether retries lack backoff and amplify the load", "How retries behave"),
        ("The Retry-After header for when to try again", "Some header in the response"),
        ("Whether a recent deploy increased request volume", "Whether something changed lately"),
        ("Whether the provider's plan tier lowered your limit", "Your account situation")]),
    ("reduce_tokens", ["List {n} ways to reduce prompt token usage.", "How can a team cut down the tokens it sends per request? Name {n} ways."], [
        ("Trim repeated boilerplate from the system prompt", "Make the prompt shorter somehow"),
        ("Retrieve only the relevant chunks instead of whole documents", "Use less context, I guess"),
        ("Summarise long conversation history instead of resending it", "Handle history differently"),
        ("Cache stable prefixes so they are not billed repeatedly", "Use some kind of caching"),
        ("Set a sensible max_tokens so replies stay bounded", "Limit the output somewhere"),
        ("Route simple requests to a smaller model", "Pick other models for some things")]),
    ("p99_latency", ["What are {n} common causes of high p99 latency in an LLM gateway?", "Give {n} reasons the slowest requests through a gateway get so slow."], [
        ("A slow upstream provider during peak hours", "Something upstream"),
        ("Queueing because concurrency limits are too low", "Not enough capacity, perhaps"),
        ("Very large prompts with long completions", "Big requests in general"),
        ("Cold connections because keep-alive is disabled", "Some connection trouble"),
        ("Retries and failover adding whole extra round trips", "Extra steps in the path"),
        ("Garbage collection or lock contention inside the gateway", "Something inside the gateway itself")]),
    ("leaked_credential", ["Give {n} steps to take after discovering a leaked credential.", "A credential leaked. List {n} actions to take."], [
        ("Revoke or disable the credential immediately", "Deal with it quickly"),
        ("Issue a replacement and deploy it to legitimate users", "Get a new one out there"),
        ("Search the logs for any use of the leaked credential", "Look into what happened"),
        ("Find and remove the place it leaked, such as a public repo", "Try to find the source"),
        ("Notify the owner and the security team", "Tell the right people, I think"),
        ("Write a short incident report and fix the process gap", "Document some of it")]),
    ("broad_credentials", ["Name {n} risks of giving an agent broad delegated credentials.", "What are {n} dangers of an agent holding wide-ranging credentials?"], [
        ("A prompt injection can trigger actions far beyond the task", "Bad input could cause problems"),
        ("One leaked token exposes every system it can reach", "Leaks could be bad"),
        ("Agent mistakes can delete or change production data", "The agent might make errors"),
        ("Actions are hard to attribute to a specific task or person", "It gets unclear who did what"),
        ("Compliance scopes are violated when data crosses boundaries", "Some rules may be broken"),
        ("Revoking access for one task means revoking it for all", "Access is hard to undo")]),
    ("postmortem", ["List {n} sections a blameless postmortem should include.", "What {n} sections belong in a blameless postmortem?"], [
        ("A timeline of events with timestamps", "Some history of what went on"),
        ("The customer impact and how long it lasted", "How bad it was, roughly"),
        ("Contributing factors rather than a single root cause", "Why it happened, I suppose"),
        ("How the problem was detected and what should have caught it", "How it was noticed"),
        ("Action items with owners and due dates", "Some follow-up things"),
        ("What went well during the response", "The good parts")]),
    ("safe_retries", ["Give {n} practices that make retries safe.", "What {n} practices keep a retry policy from causing harm?"], [
        ("Use idempotency keys so repeats do not duplicate effects", "Make repeats safe in some way"),
        ("Back off exponentially with jitter between attempts", "Wait a bit between attempts"),
        ("Cap the number of attempts and the total time", "Put some limit on it"),
        ("Retry only transient errors, not validation failures", "Retry the right sort of errors"),
        ("Use a circuit breaker to stop hammering a failing service", "Protect the service somehow"),
        ("Emit metrics on retry counts to spot storms early", "Keep an eye on things")]),
    ("failed_migration", ["What are {n} common causes of a failed database migration?", "Name {n} reasons a schema migration goes wrong in production."], [
        ("A long lock on a large table blocks live traffic", "Something locks up"),
        ("The schema change is incompatible with the running code version", "A version mismatch of some kind"),
        ("Existing data violates a new constraint and was never cleaned", "Problems with the data"),
        ("The migration runs out of disk space or memory", "A resource shortage"),
        ("No tested rollback path exists", "Nobody planned the undo"),
        ("Replication lag leaves replicas serving stale data", "Some replica trouble")]),
    ("onboard_agent", ["Give {n} steps to onboard a new agent identity.", "List {n} things to do when bringing a new agent into the platform."], [
        ("Register the agent with a unique, named identity", "Set it up in the system"),
        ("Assign a human owner who is accountable for it", "Decide who is responsible, more or less"),
        ("Grant only the minimum scopes the agent needs", "Sort out what it can access"),
        ("Issue a short-lived credential bound to that identity", "Give it some credentials"),
        ("Set a spending cap and rate limits", "Put some limits in place"),
        ("Turn on logging so its actions are auditable", "Make sure it is tracked somehow")]),
    ("cache_hit_drop", ["List {n} reasons a prompt cache hit rate might drop.", "Why could a cache hit rate suddenly fall? Give {n} reasons."], [
        ("A prompt prefix changed, such as a timestamp inserted at the top", "The prompts changed somehow"),
        ("The cache TTL expired during low traffic", "Entries do not last long enough"),
        ("A deploy flushed the cache", "A release did something to it"),
        ("Requests spread across more models or regions", "There are more places to go"),
        ("Personalised content made every prompt unique", "Prompts vary more than before"),
        ("The cache was resized and is evicting entries", "The capacity changed")]),
    ("delete_bucket", ["Give {n} things to check before deleting a storage bucket.", "Before deleting a bucket, which {n} checks would you make?"], [
        ("That no service or job still reads or writes it", "Whether anything uses it"),
        ("That a backup or copy of the data exists", "Whether you have a copy somewhere"),
        ("Retention and legal hold requirements", "Some rules that might apply"),
        ("That the owner knows and approves", "Whether it is okay with people"),
        ("Whether versioning or replication keeps extra copies", "Some settings on the bucket"),
        ("That its name is not referenced in configuration or DNS", "References elsewhere, maybe")]),
    ("prompt_injection", ["Name {n} signs of a prompt injection attempt.", "What {n} signs suggest someone is attempting prompt injection?"], [
        ("Input text telling the model to ignore its previous instructions", "Odd instructions in the input"),
        ("A document with hidden or invisible text aimed at the model", "Weird content inside documents"),
        ("A sudden request to reveal the system prompt or secrets", "Requests for private information"),
        ("Tool calls the user's task never called for", "Actions that seem off"),
        ("Outputs containing unexpected links or encoded data", "Strange things in the output"),
        ("Text impersonating the developer or an admin", "Claims of authority")]),
    ("flaky_tests", ["What are {n} common causes of flaky tests?", "List {n} reasons a test passes sometimes and fails other times."], [
        ("Tests depend on real time or sleep statements", "Something to do with timing"),
        ("Shared state leaks between tests", "Tests affecting each other"),
        ("Order-dependent tests that only pass in one sequence", "Some ordering issue"),
        ("Network calls to services that are not mocked", "Outside dependencies"),
        ("Race conditions in asynchronous code", "Concurrency stuff"),
        ("Test data that collides, such as fixed IDs", "Data problems, probably")]),
    ("oncall_prep", ["List {n} things to do before starting an on-call shift.", "You are about to go on call. Name {n} things to prepare."], [
        ("Read the handoff notes from the previous engineer", "Get up to speed"),
        ("Check that paging and VPN access work", "Test your access"),
        ("Review open incidents and recent deploys", "Look at what is going on"),
        ("Know where the runbooks and escalation contacts live", "Know where to find help"),
        ("Make sure your laptop is charged and you are reachable", "Just be ready"),
        ("Confirm who your secondary is", "Know the backup, sort of")]),
    ("choose_model", ["Name {n} factors to weigh when choosing a model for a task.", "What {n} factors matter when picking an LLM for a job?"], [
        ("Quality on your own evaluation set, not just public benchmarks", "How good it is"),
        ("Cost per million tokens at your expected volume", "The price, basically"),
        ("Latency, including tail latency under load", "How fast it is"),
        ("Context window size versus your longest inputs", "Some size limits"),
        ("Data handling terms and where the data is processed", "The provider's policies"),
        ("Availability and rate limits from the provider", "Whether it is reliable")]),
    ("runaway_batch", ["Give {n} ways to detect a runaway batch job.", "How would you spot a batch job that has gone off the rails? Name {n} signals."], [
        ("Runtime far exceeds the historical median", "It takes very long"),
        ("Spend or token counters grow faster than the baseline", "Usage looks odd"),
        ("Progress metrics stall while resource use stays high", "It is busy but nothing happens"),
        ("The same records are processed repeatedly", "There is repetition"),
        ("Queue depth or error counts climb without bound", "Numbers keep going up"),
        ("A budget alert fires for the job's cost centre", "Some alert goes off")]),
    ("memory_leak", ["List {n} common causes of memory leaks in a long-running service.", "What are {n} typical sources of a slow memory leak in a server?"], [
        ("Caches that grow without eviction", "Things that grow unbounded"),
        ("Event listeners or callbacks that are never removed", "Leftover handlers"),
        ("Connections or file handles that are never closed", "Resources not released"),
        ("Global collections that keep references to old objects", "Things being kept around"),
        ("Goroutines or threads that never exit", "Background workers of some kind"),
        ("Large buffers held by slow consumers", "Some buffers")]),
    ("runbook", ["Name {n} things every runbook should include.", "What {n} elements make a runbook useful at 3 a.m.?"], [
        ("A clear description of the symptom and how to confirm it", "What the problem is, more or less"),
        ("Step-by-step commands for diagnosis", "Some instructions"),
        ("Safe mitigation steps and their risks", "Some ways to fix things"),
        ("Escalation contacts and when to use them", "Who to call, I guess"),
        ("A rollback procedure", "How to undo stuff"),
        ("Links to the relevant dashboards and logs", "Where to look")]),
    ("rollback", ["Give {n} steps to roll back a bad deploy.", "A deploy went bad. List {n} steps to roll it back."], [
        ("Announce the rollback in the incident channel", "Let people know"),
        ("Identify the last known good version", "Find the right version"),
        ("Redeploy that version through the normal pipeline", "Put the old one back"),
        ("Verify health checks and error rates recover", "Check that it works again"),
        ("Check whether database changes need reverting too", "Think about the data"),
        ("Freeze further deploys until the cause is understood", "Hold off on more changes")]),
    ("tls_errors", ["What are {n} causes of TLS certificate errors?", "List {n} reasons a client rejects a server's TLS certificate."], [
        ("The certificate has expired", "It is out of date or something"),
        ("The hostname does not match the certificate's names", "Some naming trouble"),
        ("The chain is missing an intermediate certificate", "Something missing in the chain"),
        ("The client's clock is badly wrong", "Something time related"),
        ("The certificate authority is not trusted by the client", "Trust issues"),
        ("The certificate was revoked", "It was cancelled somehow")]),
    ("rate_limit_benefits", ["List {n} benefits of rate limiting an API.", "Why rate limit an API? Give {n} benefits."], [
        ("It protects the service from overload", "It keeps things safe"),
        ("It stops one client from starving the others", "It is fair, somehow"),
        ("It caps the cost of abusive or buggy clients", "It saves money, I think"),
        ("It slows brute-force attacks on credentials", "It helps with security"),
        ("It makes capacity planning more predictable", "It helps with planning"),
        ("It gives clients a clear signal to back off", "It communicates something to clients")]),
    ("data_drift", ["Give {n} causes of data drift in a deployed model.", "What are {n} reasons a model's input data drifts after launch?"], [
        ("User behaviour changes over time", "People change"),
        ("An upstream system changes its data format", "Sources change"),
        ("Seasonality shifts the input distribution", "Something about the time of year"),
        ("A new customer segment appears in the traffic", "New kinds of users"),
        ("A pipeline bug silently corrupts a feature", "Something is broken upstream"),
        ("Labels are produced with a changed definition", "Definitions move around")]),
    ("bug_report", ["Give {n} things a good bug report includes.", "What {n} details make a bug report actionable?"], [
        ("Exact steps to reproduce the problem", "How it happened, roughly"),
        ("What you expected versus what actually happened", "The difference, kind of"),
        ("Environment details such as version and operating system", "Some context"),
        ("Logs or screenshots that show the failure", "Some evidence"),
        ("How often it happens", "Frequency, more or less"),
        ("The impact and urgency", "How important it is")]),
    ("secure_webhook", ["Name {n} ways to secure a webhook endpoint.", "How do you harden a webhook receiver? Give {n} measures."], [
        ("Verify a signature on every request", "Check who sent it"),
        ("Reject old timestamps to prevent replays", "Deal with replays somehow"),
        ("Accept HTTPS only", "Use encryption"),
        ("Restrict source IPs where the sender publishes them", "Limit who can connect"),
        ("Respond quickly and process the payload asynchronously", "Be quick about it"),
        ("Rotate the signing secret periodically", "Change secrets now and then")]),
    ("feature_flags", ["List {n} reasons to use feature flags.", "What {n} benefits do feature flags give a team?"], [
        ("Ship code dark and enable it later", "Release things flexibly"),
        ("Roll out gradually to a percentage of users", "Staged rollouts of some kind"),
        ("Turn a broken feature off without a deploy", "A kind of kill switch"),
        ("Run experiments and A/B tests", "Testing things"),
        ("Give beta customers early access", "Early access for some people"),
        ("Separate deploy from release to reduce risk", "Less risk overall")]),
    ("disk_full", ["What are {n} common causes of a server's disk filling up?", "Name {n} reasons a disk fills up unexpectedly."], [
        ("Logs growing without rotation", "Log things, probably"),
        ("Temporary files that are never cleaned up", "Leftover files"),
        ("Database write-ahead logs or backups accumulating", "Data files piling up"),
        ("Container images and volumes piling up", "Container related stuff"),
        ("Core dumps from repeated crashes", "Crash files"),
        ("A runaway process writing output endlessly", "A process misbehaving")]),
    ("code_review", ["Give {n} tips for a good code review.", "List {n} habits of a helpful code reviewer."], [
        ("Read the description and understand the intent first", "Get some context"),
        ("Keep reviews small", "Mind the size"),
        ("Comment on behaviour and risk, not style nitpicks", "Be useful in comments"),
        ("Suggest alternatives instead of only objecting", "Be constructive"),
        ("Check that tests cover the change", "Look at testing"),
        ("Respond promptly so the author is not blocked", "Timing matters")]),
    ("productive_meeting", ["List {n} ways to run a more productive meeting.", "Give {n} tips for making meetings worth everyone's time."], [
        ("Share a clear agenda beforehand", "Plan ahead a bit"),
        ("Invite only the people who need to be there", "Get the right people"),
        ("Timebox each topic", "Watch the clock"),
        ("Assign an owner and a deadline to every action item", "Follow up on stuff"),
        ("Start and end on time", "Be punctual-ish"),
        ("Write and share notes afterwards", "Some kind of notes")]),
    ("day_hike", ["Name {n} things to pack for a day hike.", "What {n} items belong in a day-hike backpack?"], [
        ("Enough water for the whole trip", "Something to drink"),
        ("A map or offline navigation", "Something for directions"),
        ("Layers of clothing for changing weather", "Clothes of some sort"),
        ("A basic first aid kit", "Some medical things"),
        ("Sun protection such as a hat and sunscreen", "Stuff for the weather"),
        ("Snacks with enough calories", "Some food, I guess")]),
    ("better_sleep", ["Give {n} habits that improve sleep.", "List {n} things that help people sleep better."], [
        ("Keep a consistent bedtime and wake time", "Have some kind of routine"),
        ("Avoid caffeine in the afternoon", "Watch what you consume"),
        ("Keep the bedroom dark, cool and quiet", "Sort out the room"),
        ("Turn off screens an hour before bed", "Do something about devices"),
        ("Get daylight and exercise during the day", "Be active"),
        ("Avoid heavy meals late at night", "Mind your evenings")]),
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


def level_of(n_asked: int, clear: int, vague: int, offtopic: bool) -> int:
    """The scoring rule: how much of the task is done.

    Defects = missing items + vague items (= N - clear items).
    3: no defects. 2: exactly one defect, and either N >= 4 (one item missing
    or one vague) or N = 3 with that one defect a vague item (nothing
    missing). 1: at least one correct clear item but more defects than level 2
    allows (for example 2 of 3 given, 2 of 4 given, or a missing item out of
    only three). 0: off-topic, no requested item given."""
    if offtopic:
        return 0
    if clear < 1:
        raise ValueError(f"no level for asked={n_asked} clear={clear} vague={vague}")
    missing = n_asked - clear - vague
    if missing < 0 or vague > 2:
        raise ValueError(f"no level for asked={n_asked} clear={clear} vague={vague}")
    defects = missing + vague
    if defects == 0:
        return 3
    if defects == 1 and (n_asked >= 4 or (vague == 1 and missing == 0)):
        return 2
    return 1


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
                    n = rng.choice([3, 4, 5])
                    task = rng.choice(phrasings).format(n=NUMBER_WORDS[n])
                    order = rng.sample(range(len(bank)), len(bank))
                    clear_n = vague_n = 0
                    offtopic = False
                    other = None
                    if level == 3:
                        chosen = [bank[i][0] for i in order[:n]]
                        clear_n = n
                    elif level == 2:
                        clear_n, vague_n = (2, 1) if n == 3 else (n - 1, rng.choice([0, 1]))
                        chosen = [bank[i][0] for i in order[:clear_n]] + [bank[i][1] for i in order[clear_n:clear_n + vague_n]]
                        rng.shuffle(chosen)
                    elif level == 1:
                        if n == 3:
                            clear_n, vague_n = rng.choice([(2, 0), (1, 0), (1, 1), (1, 2)])
                        else:
                            clear_n = rng.randint(1, n - 2)
                            vague_n = rng.randint(0, min(2, n - clear_n))
                        chosen = [bank[i][0] for i in order[:clear_n]] + [bank[i][1] for i in order[clear_n:clear_n + vague_n]]
                        rng.shuffle(chosen)
                    else:
                        offtopic = True
                        if rng.random() < 0.7:
                            other = rng.choice([t for t in range(len(TOPICS)) if t != gi])
                            oorder = rng.sample(range(len(TOPICS[other][2])), len(TOPICS[other][2]))
                            chosen = [TOPICS[other][2][i][0] for i in oorder[:n]]
                        else:
                            chosen = None
                    answer = _compose(rng, chosen, rng.randint(*TARGET_WORDS))
                    if (task, answer) not in seen:
                        break
                else:
                    raise RuntimeError(f"{gid}: cannot draw distinct items")
                seen.add((task, answer))
                params = {"n": n, "clear": clear_n, "vague": vague_n, "offtopic": offtopic,
                          "other_topic": None if other is None else TOPICS[other][0], "topic": slug, "answer_items": chosen or []}
                cases.append(Case(FAMILY, TEMPLATE, {"task": task, "final_answer": answer}, level, gid, params))
    return finalize(cases, rng, TEMPLATE)


def strata() -> dict[str, list[str]]:
    return {"all": groups()}
