"""Family 1: request.complexity (choice: cheap / default / hard / reasoning).

Truth is by construction: each class has its own list of phrasing templates
(a "group" is one template); a row's gold is the class of the list its group
came from. The classes are kept separable by the rule the spec states:

- cheap: a short factual lookup or trivial transform;
- default: ordinary writing, summarising or explaining, moderate length;
- hard: long-context, multi-step, domain-deep work with NO explicit ask for
  step-by-step proof;
- reasoning: explicitly asks for rigorous proof, formal derivation or careful
  step-by-step reasoning.

The separating property the tests recompute: a prompt contains a reasoning
cue (REASONING_CUES) if and only if its gold is "reasoning". Length is NOT a
separator on purpose: neutral pre/suffixes pad any class, some default and
reasoning prompts are long, some hard prompts are short.
"""

from __future__ import annotations

import re

from .common import ROWS_PER_FAMILY, Case, fill, finalize, load_template, rng_for, spread

FAMILY = "request.complexity"
TEMPLATE = "request.complexity"
CODE = "cx"
LABELS = ["cheap", "default", "hard", "reasoning"]

#: Words that, by the spec's definition, mark an explicit ask for rigorous or
#: step-by-step reasoning. They appear in reasoning prompts and nowhere else.
REASONING_CUES = re.compile(
    r"\b(prove|proof|derive|derivation|step by step|step-by-step|rigorous\w*|formal\w*|"
    r"every step|each step|carefully|induction|invariant)\b",
    re.IGNORECASE,
)

#: Neutral wrappers, applied to any class with the same probability, so that
#: politeness and length carry no label information.
PREFIXES = ["Hey, ", "Hi - ", "Quick one: ", "Sorry to bother you, ", "Morning! ", "Hello, ", "One thing: ", "Could you help? "]
SUFFIXES = [" Thanks!", " Appreciate it.", " Cheers.", " Thank you.", " Much appreciated.", " Thanks in advance."]
#: Longer, chatty context sentences, also applied to every class with the same
#: probability so that a short ask is not always a short prompt.
PREAMBLES = [
    "I'm putting together a slide deck for our weekly sync and I'm a bit short on time. ",
    "My manager asked me about this earlier and I want to get it right. ",
    "Context: this is for an internal wiki page that new joiners read in their first week. ",
    "We had a long thread about this yesterday and nobody wrote down the answer. ",
    "I'm on call this week and trying to clear my queue before the handover. ",
    "This is for a document that finance and engineering will both read. ",
    "I've been staring at this for a while and would appreciate a fresh pair of eyes. ",
    "Background: our team is small, we move quickly, and we keep notes in a shared folder. ",
]
WRAP_PREFIX_P = 0.25
WRAP_SUFFIX_P = 0.25
WRAP_PREAMBLE_P = 0.22

COUNTRIES = ["Australia", "Canada", "Kenya", "Norway", "Peru", "Vietnam", "Portugal", "Chile", "Egypt", "Poland",
             "Thailand", "Argentina", "Ireland", "Morocco", "New Zealand", "Finland", "Ghana", "Malaysia"]
PORTS = ["PostgreSQL", "Redis", "MySQL", "MongoDB", "SSH", "HTTPS", "SMTP", "Elasticsearch", "RabbitMQ", "Memcached", "etcd", "Kafka"]
HTTP_CODES = ["404", "429", "503", "401", "502", "418", "301", "504", "403", "409", "500", "204"]
ACRONYMS = ["TLS", "SLA", "RBAC", "OIDC", "CIDR", "TTL", "MTTR", "IAM", "CDN", "DNS", "ACID", "SLO", "JWT", "gRPC"]
TYPO_SENTENCES = [
    "We will recieve the shipment on Thursday.", "The deploymnet finished without errors.",
    "Please adress the feedback before merging.", "Their is a typo in the config comments.",
    "The alert fired becuase the threshold was too low.", "She definately approved the request.",
    "Our team ocassionally rotates the keys.", "This is a seperate problem from the outage.",
    "The report is avaliable in the shared folder.", "Can you confrim the meeting time?",
]
PHRASES = ["good morning", "where is the train station", "the invoice is attached", "thank you for your patience",
           "see you next week", "the meeting is at noon", "please restart the service", "happy birthday",
           "how much does this cost", "the server is back online"]
LANGS = ["Spanish", "French", "German", "Italian", "Portuguese", "Dutch", "Polish", "Swedish"]
SYNONYM_WORDS = ["quick", "big", "start", "tired", "happy", "begin", "difficult", "cheap", "smart", "angry", "fix", "strange"]
CONVERSIONS = [
    {"n": "72", "a": "degrees Fahrenheit", "b": "Celsius"}, {"n": "5", "a": "miles", "b": "kilometres"},
    {"n": "180", "a": "pounds", "b": "kilograms"}, {"n": "3.5", "a": "litres", "b": "millilitres"},
    {"n": "100", "a": "kilometres per hour", "b": "miles per hour"}, {"n": "2", "a": "gigabytes", "b": "megabytes"},
    {"n": "36", "a": "inches", "b": "centimetres"}, {"n": "90", "a": "minutes", "b": "hours"},
    {"n": "14", "a": "ounces", "b": "grams"}, {"n": "0", "a": "degrees Celsius", "b": "Kelvin"},
]
DATES = ["March 4, 2025", "4th of July 2024", "12/31/2023", "Sept 9 2026", "1 Feb 2025", "Tuesday the 15th of April 2025"]
GIT_CMDS = ["git stash pop", "git rebase --abort", "git cherry-pick", "git reflog", "git bisect start", "git clean -fd",
            "git fetch --prune", "git tag -a", "git blame", "git restore --staged"]
ROMAN = ["14", "49", "88", "1994", "2025", "402", "37", "2048"]
PAIRS = [
    {"a": "a kilobyte", "b": "a megabyte"}, {"a": "Jupiter", "b": "Saturn"}, {"a": "1/3", "b": "0.4"},
    {"a": "a nanosecond", "b": "a microsecond"}, {"a": "Mount Everest", "b": "K2"}, {"a": "0.75", "b": "3/5"},
    {"a": "an hour", "b": "4000 seconds"}, {"a": "2 to the 10th power", "b": "1000"},
]
TRIVIA = ["When was the first iPhone released?", "Who wrote Pride and Prejudice?", "How many legs does a spider have?",
          "What is the chemical symbol for sodium?", "Which planet has the most moons?", "What is the tallest mountain in Africa?",
          "How many bits are in a byte?", "What language is spoken in Brazil?", "Who painted the Mona Lisa?",
          "What is the boiling point of water at sea level in Celsius?", "Which ocean is the largest?",
          "How many days are in a leap year?"]
EMAILS = ["Reach me at dana.weiss@example.com after 3pm.", "Contact: Support <help@northwind.example> or call 555-0134.",
          "Forwarded from ops-alerts@example.org on Monday.", "Please cc marcus.obi@example.net on the reply.",
          "Billing questions go to finance-team@example.com please."]
WORDS_UP = ["deployment complete", "all systems nominal", "rollback finished", "request approved", "budget under review", "ticket closed"]
PRIMES = ["17", "21", "29", "51", "97", "91", "13", "57"]
ABBREV = ["JSON", "CSV", "YAML", "SQL", "REST", "CLI", "SDK", "LLM"]

CHEAP: list[tuple[str, dict]] = [
    ("What is the capital of {country}?", {"country": COUNTRIES}),
    ("Convert {n} {a} to {b}.", {"_": CONVERSIONS}),
    ("Fix the typo: \"{s}\"", {"s": TYPO_SENTENCES}),
    ("Translate \"{p}\" into {l}.", {"p": PHRASES, "l": LANGS}),
    ("what does http {c} mean", {"c": HTTP_CODES}),
    ("Give me one synonym for \"{w}\".", {"w": SYNONYM_WORDS}),
    ("What's the default port for {svc}?", {"svc": PORTS}),
    ("Which is bigger, {a} or {b}?", {"_": PAIRS}),
    ("What does {x} stand for?", {"x": ACRONYMS}),
    ("Is {n} a prime number? Answer yes or no.", {"n": PRIMES}),
    ("Extract the email address from this and return only the address: \"{t}\"", {"t": EMAILS}),
    ("Format this date as ISO 8601: {d}", {"d": DATES}),
    ("tl;dr what does `{c}` do?", {"c": GIT_CMDS}),
    ("Quick trivia: {q}", {"q": TRIVIA}),
    ("Write {n} in Roman numerals.", {"n": ROMAN}),
    ("Convert to uppercase: {t}", {"t": WORDS_UP}),
]

PASSAGES = [
    "On Tuesday the payments team shipped the new retry policy. Two customers reported duplicate confirmations on Wednesday, and the team rolled back the change after lunch. A fix with an idempotency key is planned for next sprint.",
    "The quarterly review showed support volume down nine percent while average handling time rose slightly. Managers attribute the increase to the new escalation form, which asks for more detail upfront. Training sessions start next month.",
    "Our vendor announced a price change effective the first of the month. Volume discounts now start at a higher tier, and the prepaid commitment option was removed. Finance is reviewing whether the annual plan still makes sense.",
    "During the migration window the read replicas lagged by up to forty seconds. Dashboards showed stale numbers and two scheduled reports failed. The lag cleared once the bulk copy finished at about four in the morning.",
    "Three new hires start Monday: one backend engineer, one data analyst and one designer. Laptops are provisioned, but the analyst still needs access to the warehouse. The onboarding buddy rota is in the team wiki.",
    "The security review flagged that several service accounts have not rotated credentials in over a year. Owners have been notified and have thirty days to rotate or justify an exception. Unowned accounts will be disabled.",
    "Customer feedback on the new dashboard is mixed. People like the faster load times but miss the old export button, which moved into a menu. Product is considering restoring a visible shortcut in the next release.",
    "The batch job that builds the nightly report now takes three hours instead of one. Profiling points at a new join on the events table, which lacks an index. Adding one is cheap but needs a short maintenance window.",
]
INFORMAL = [
    "hey all, just a heads up the deploy is gonna be late cuz the tests keep flaking, we r looking at it, prob done by 5ish",
    "so basically the vendor messed up our invoice again and finance wants us to dispute it asap, can someone grab the contract",
    "i think the new onboarding flow is kinda confusing, like people dont know where to click after signup, we should fix it soon",
    "just fyi the standup is moved, same time tmrw but in the big room, bring ur laptops cuz we r doing the planning thing",
    "the report is mostly done but some numbers look off, might be the timezone thing again, will double check n let u know",
]
TOPICS_DOCS = [
    {"doc": "release note", "aud": "customers", "topic": "the new audit log export"},
    {"doc": "status update", "aud": "the leadership team", "topic": "the database migration"},
    {"doc": "FAQ entry", "aud": "new support agents", "topic": "how refunds are approved"},
    {"doc": "short announcement", "aud": "the engineering org", "topic": "the change freeze next week"},
    {"doc": "one-page summary", "aud": "the finance team", "topic": "how LLM usage is billed"},
    {"doc": "welcome message", "aud": "a new hire on the platform team", "topic": "what to expect in the first week"},
]
CONCEPTS = ["consistent hashing", "OAuth token refresh", "database connection pooling", "a circuit breaker", "eventual consistency",
            "rate limiting with a token bucket", "blue-green deployment", "a vector database", "prompt caching", "backpressure in queues"]
PY_TASKS = ["deduplicates a list while preserving order", "parses a log line into timestamp, level and message",
            "groups a list of dicts by a key", "retries a function with exponential backoff", "flattens a nested dictionary into dotted keys",
            "merges two sorted lists into one", "validates that a string is a well-formed semantic version", "chunks a list into batches of a given size"]
CHECKLISTS = ["handing over an on-call shift", "reviewing a pull request", "onboarding a new teammate", "preparing for a product demo",
              "closing out a sprint", "rotating a shared credential", "running a blameless retrospective", "launching a small feature"]
NAMEABLES = [
    {"n": "five", "thing": "an internal tool that tracks model costs"}, {"n": "four", "thing": "a newsletter for support engineers"},
    {"n": "six", "thing": "a hackathon team building a meeting summariser"}, {"n": "five", "thing": "a dashboard for agent approvals"},
    {"n": "four", "thing": "a podcast about infrastructure incidents"},
]
TRANSLATE_PARAS = [
    "Thanks for reaching out. We have received your request and will reply within two business days. If it is urgent, please call the number on our website.",
    "Your subscription renews next week. You can change or cancel your plan at any time from the billing page, and we will email you a receipt.",
    "We are sorry for the trouble. The issue has been fixed, and your account has been credited for the lost time.",
]
COMPARES = [
    {"a": "PostgreSQL", "b": "MySQL", "sit": "small team building an analytics-heavy internal app"},
    {"a": "a monorepo", "b": "many small repos", "sit": "team of twelve engineers"},
    {"a": "Terraform", "b": "Pulumi", "sit": "startup with mostly TypeScript developers"},
    {"a": "REST", "b": "gRPC", "sit": "set of internal services with mixed languages"},
    {"a": "Slack alerts", "b": "email digests", "sit": "finance team that wants spend notifications"},
]
TALK = [
    {"n": "five", "aud": "the executive team", "topic": "last quarter's incident trends"},
    {"n": "ten", "aud": "the all-hands", "topic": "the new approval workflow"},
    {"n": "three", "aud": "a customer advisory board", "topic": "our roadmap for agent governance"},
    {"n": "fifteen", "aud": "the security guild", "topic": "credential rotation lessons learned"},
]
SQL_TASKS = [
    {"task": "find the ten customers with the highest total refunds in the last 90 days", "table": "refunds", "cols": "customer_id, amount, created_at"},
    {"task": "count distinct agents per team that made at least one call yesterday", "table": "agent_calls", "cols": "agent_id, team, called_at"},
    {"task": "list requests whose latency was above the 95th percentile", "table": "requests", "cols": "id, route, latency_ms, ts"},
    {"task": "compute the week over week change in token usage per project", "table": "usage", "cols": "project, tokens, day"},
]
PROOFREAD = [
    "Our platform allows teams to govern agent spending in realtime, it also provides an audit trail which are useful for compliance. The setup is easy and takes only few minutes to complete.",
    "In order to get started you should first of all create an account, then after that you can invite your teammates who will be able to access to the dashboard right away.",
    "The new release includes several improvements, such as faster load times, better error messages, and also it fixes a bug that caused exports to fail sometimes.",
]

NOTES = [
    "we agreed to move the launch to the 14th; Sam will own the migration runbook; finance needs the vendor quote by Friday; support wants a macro for the new refund flow; nobody has tested the export on large accounts yet; Priya is out next week so reviews go to Dev",
    "the audit export is slow for accounts over 100k rows; Lena suggested paging the query; Omar thinks we should cache the summary table instead; we need a decision before the sprint ends; the customer success team keeps getting asked for an ETA and has none",
    "budget alerts fire too late for the weekend batch jobs; Ana will check the thresholds; we should add an owner field to every agent; legal asked whether logs can leave the EU region; Mateo will draft the answer and send it to Kai",
]
JOB_DESCRIPTIONS = [
    "We are looking for a rockstar backend ninja who can hit the ground running in a fast-paced environment. You will own services end to end, be on call for incidents, and work closely with product. Must have five or more years of experience, a degree in computer science, and the ability to thrive under pressure. Culture fit is important to us.",
    "The ideal candidate is a self-starter with a passion for data. Responsibilities include building dashboards, running ad hoc analyses, and supporting the finance team during month end. You should be fluent in SQL, comfortable presenting to executives, and willing to work long hours when needed.",
]
THREADS = [
    "Dana: The vendor says the price change starts on the 1st. Rui: That is not what the contract says, section 4 gives us 60 days notice. Dana: I checked, the notice was sent on the 3rd of last month. Rui: Then we have until the end of this month. Mina: Finance needs to know by Thursday whether to prepay. Dana: I will ask the vendor for written confirmation.",
    "Ops: The nightly job failed twice this week. Ben: Both times it ran out of memory during the join. Ops: Can we just raise the limit? Ben: We could, but the real fix is to stop loading the whole table. Kit: I can have a patch by Wednesday. Ops: Fine, raise the limit for now and revisit after the patch ships.",
]

DEFAULT: list[tuple[str, dict]] = [
    ("Write a short, friendly email to {who} letting them know that {news}. Keep it under {n} words.",
     {"who": ["a customer", "a vendor contact", "my manager", "the whole support team", "a new client"],
      "news": ["their invoice will arrive a day late", "the maintenance window has moved to Saturday", "we have finished the onboarding checklist",
               "the requested report is ready for review", "their account has been upgraded at no extra charge", "the demo has been rescheduled to next Thursday"],
      "n": ["80", "100", "120", "150"]}),
    ("Summarize the following in three bullet points: {t}", {"t": PASSAGES}),
    ("Explain the difference between {a} and {b} to someone who just started as a {r}.",
     {"_": [{"a": "TCP", "b": "UDP"}, {"a": "a process", "b": "a thread"}, {"a": "authentication", "b": "authorization"},
            {"a": "a cache", "b": "a database"}, {"a": "latency", "b": "throughput"}, {"a": "unit tests", "b": "integration tests"}],
      "r": ["junior developer", "product manager", "support engineer", "data analyst", "site reliability engineer"]}),
    ("Rewrite this so it sounds more professional but still friendly: {t}", {"t": INFORMAL}),
    ("Draft a {doc} for {aud} about {topic}.", {"_": TOPICS_DOCS}),
    ("Can you explain how {c} works in plain English? A couple of paragraphs is fine.", {"c": CONCEPTS}),
    ("Write a Python function that {t}. Include a docstring and two example calls.", {"t": PY_TASKS}),
    ("Give me a checklist for {a}.", {"a": CHECKLISTS}),
    ("Suggest {n} names for {thing} and say briefly why each works.", {"_": NAMEABLES}),
    ("Translate this paragraph into {l} and keep the tone friendly: {t}", {"l": LANGS, "t": TRANSLATE_PARAS}),
    ("Compare {a} and {b} for a {sit}. Which would you pick and why?", {"_": COMPARES}),
    ("I need talking points for a {n}-minute update to {aud} about {topic}.", {"_": TALK}),
    ("Write a SQL query to {task}. The table is {table}({cols}).", {"_": SQL_TASKS}),
    ("Proofread this and suggest edits for clarity: {t}", {"t": PROOFREAD}),
    ("Here are my notes from today's planning meeting: {n}. Turn them into a clear list of action items with owners and dates where they are mentioned.", {"n": NOTES}),
    ("Rewrite this job description so it is more inclusive and easier to skim: {j}", {"j": JOB_DESCRIPTIONS}),
    ("Summarize this email thread in three sentences and list any decisions that were made: {t}", {"t": THREADS}),
    ("Summarize each of these two notes in a sentence, then combine them into a short brief for the team. First note: {t} Second note: {u}",
     {"_": [{"t": PASSAGES[i], "u": PASSAGES[(i + k) % len(PASSAGES)]} for i in range(len(PASSAGES)) for k in (2, 5)]}),
]

SIZES = ["800 GB", "4 TB", "12 TB", "1.5 TB", "300 GB", "25 TB"]
HARD: list[tuple[str, dict]] = [
    ("We are migrating {size} of {db} from {src} to {dst} for a {org} with a {window} cutover window. Current setup: {setup}. Design the migration plan: replication approach, cutover sequence, rollback, validation, and the risks we are most likely to underestimate.",
     {"size": SIZES, "db": ["PostgreSQL data", "MySQL data", "Oracle data", "SQL Server data"],
      "src": ["an on-prem datacentre", "a colocation cage", "a legacy cloud account"], "dst": ["a managed cloud service", "a new Kubernetes-based platform", "a different cloud provider"],
      "org": ["payments company", "healthcare SaaS vendor", "retail marketplace", "logistics platform"],
      "window": ["two-hour", "six-hour", "weekend-long", "thirty-minute"],
      "setup": ["one primary with two asynchronous replicas and nightly logical dumps", "a sharded cluster with hand-rolled failover scripts and several cron jobs writing directly",
                "a primary-standby pair, plus reporting queries running against the standby all day", "three regions with conflicting schema versions and a legacy ETL reading the binlog"]}),
    ("Design a data pipeline that ingests {vol} events per second from {srcs}, enforces {req}, and serves {cons}. Cover schema evolution, backfills, late-arriving data, cost, and the failure modes we should plan for.",
     {"vol": ["40,000", "250,000", "1.2 million", "8,000"], "srcs": ["mobile apps, web clients and three partner webhooks", "IoT gateways and a legacy SOAP feed", "agent tool-call logs and gateway access logs"],
      "req": ["per-tenant data residency", "PII redaction before storage", "exactly-once aggregation for billing", "a 99.9 percent freshness SLO under five minutes"],
      "cons": ["a real-time dashboard and a nightly warehouse load", "fraud models and finance reporting", "customer-facing usage APIs and an internal feature store"]}),
    ("Review the following {n}-clause {k} for {party}'s exposure. Clauses: {cl}. Flag liability caps, indemnity asymmetries, termination rights and anything that conflicts with {reg}, and propose redlines with fallback positions.",
     {"n": ["five", "six", "four"], "k": ["master services agreement", "data processing addendum", "reseller agreement", "SaaS subscription agreement"],
      "party": ["the customer", "the vendor", "the reseller"],
      "cl": ["(1) liability capped at fees paid in the prior month, excluding data breach; (2) vendor may change pricing on thirty days notice; (3) customer indemnifies vendor for any use of the service; (4) termination for convenience by vendor only; (5) subprocessors may be added without notice",
             "(1) uncapped indemnity for IP claims; (2) auto-renewal for three years with a ninety-day notice window; (3) audit rights limited to once every five years; (4) governing law of a third country; (5) data returned only on request within ten days of termination; (6) service credits are the sole remedy for downtime",
             "(1) exclusivity in the EU territory; (2) minimum purchase commitments rising 20 percent yearly; (3) either party may terminate for insolvency; (4) confidentiality survives two years; (5) liability cap excludes gross negligence"],
      "reg": ["GDPR", "a financial-services outsourcing regime", "HIPAA", "our internal procurement policy"]}),
    ("Our Kubernetes cluster ({nodes} nodes, mixed {wl}) keeps {sym}. Facts so far: {facts}. Propose a diagnosis plan and remediation, and say what you would change in our infrastructure-as-code to stop it recurring.",
     {"nodes": ["40", "120", "18", "300"], "wl": ["batch and latency-sensitive services", "stateful sets and GPU inference jobs", "multi-tenant workloads"],
      "sym": ["evicting pods under memory pressure every few hours", "losing nodes during autoscaling events", "throttling CPU on services that show low utilisation", "restarting an ingress controller with no obvious crash reason"],
      "facts": ["requests and limits were last tuned a year ago, the problem began after a kernel upgrade, and only one availability zone is affected",
                "the cluster autoscaler logs show scale-ups timing out, the cloud quota dashboard is green, and spot instances were introduced last month",
                "the issue correlates with nightly batch jobs, node exporters show page cache spikes, and two namespaces have no resource quotas"]}),
    ("Here is the architecture of our multi-tenant agent platform: {arch}. Identify the tenant isolation weaknesses, propose a target architecture, and lay out a migration path that avoids downtime for the {n} largest tenants.",
     {"arch": ["a shared API tier, per-tenant schemas in one Postgres cluster, a shared vector store keyed by tenant id, and a pool of workers that pick jobs from one queue",
               "one Kubernetes namespace per tenant for the web tier but a single message broker and a shared secrets manager path prefix per tenant",
               "a gateway that authenticates with tenant API keys, stateless workers, and an object store with one bucket and tenant prefixes"],
      "n": ["three", "five", "ten"]}),
    ("Refactor the {mod} module to remove the circular dependency between {a} and {b} without breaking the public API. It is about {loc} lines, has {tests} tests, and several downstream packages import internals directly. Propose the new package layout, the order of moves, the deprecation plan, and the test strategy.",
     {"mod": ["billing", "policy engine", "ledger", "notification"], "a": ["the rules loader", "the session cache", "the event publisher"], "b": ["the evaluator", "the storage adapter", "the retry scheduler"],
      "loc": ["6,000", "12,000", "25,000"], "tests": ["roughly 400", "under 100 and mostly end to end", "about 900, many of them flaky"]}),
    ("Threat-model an agent platform where agents call third-party tools using delegated credentials: {details}. Enumerate the trust boundaries, realistic abuse cases, and mitigations ranked by cost and impact, and say what monitoring would catch each one.",
     {"details": ["user grants are OAuth scopes stored per agent, tools run in a shared sandbox pool, and agent-to-agent calls are allowed inside a tenant",
                  "credentials are minted per task with a fifteen-minute lifetime, but the tool registry accepts community-contributed tools",
                  "a long-running planner agent spawns sub-agents that inherit its full grant, and humans approve only the first action of each plan"]}),
    ("Our LLM spend is about {spend} per month across {n} teams on {prov}. Produce a cost reduction strategy covering model routing, caching, batching, commitments and governance, with expected savings ranges, sequencing, and the risks to quality.",
     {"spend": ["$180k", "$60k", "$1.2M", "$420k"], "n": ["eight", "fourteen", "thirty"], "prov": ["two proprietary providers and a self-hosted open model", "three providers with no central gateway", "a single provider under an enterprise commitment"]}),
    ("We need to fine-tune a {size} model for {task} with about {k} labelled examples, heavy class imbalance and a latency budget of {ms} milliseconds. Propose the data strategy, evaluation plan, training configuration, and rollout gates, including how we would detect regressions after launch.",
     {"size": ["7B-parameter", "3B-parameter", "13B-parameter"], "task": ["routing support tickets", "classifying agent tool calls by risk", "extracting fields from invoices", "triaging spend anomalies"],
      "k": ["2,000", "15,000", "600"], "ms": ["80", "250", "40"]}),
    ("Below is the timeline of an outage. {tl} Write a blameless postmortem with contributing factors, detection gaps, customer impact, and a prioritised action list with owners and rough effort.",
     {"tl": ["09:02 deploy of the gateway config; 09:10 error rate climbs to 4 percent; 09:25 first customer ticket; 09:41 on-call paged by a support escalation, not an alert; 10:05 rollback started; 10:30 errors gone; 11:15 cause found to be a typo in a route weight.",
             "02:14 certificate on the internal CA expired; 02:15 service-to-service calls fail; 02:40 alert fires but routes to a retired pager rotation; 03:30 a human notices; 04:10 new cert issued; 04:50 full recovery after connection pools drain.",
             "Friday 17:30 a retry storm begins after a vendor returns 529s; queue depth grows for two hours; 19:40 the broker disk fills; 19:55 producers blocked; 20:30 manual purge of the dead-letter queue; Saturday 01:00 backlog cleared."]}),
    ("Below are {n} support tickets. Cluster them into root-cause themes, identify which are probably the same underlying bug, and recommend the three engineering fixes that would remove the most tickets. {tickets}",
     {"n": ["six", "five", "seven"],
      "tickets": ["T1: export to CSV hangs at 90 percent for accounts with over 50k rows. T2: scheduled report never arrived, last run shows success. T3: CSV export truncated at 65,536 rows. T4: report email arrives but attachment is empty. T5: dashboard shows stale numbers until a hard refresh. T6: export link returns 404 after two hours.",
                  "T1: agent approvals time out if the approver is in a different timezone. T2: approval reminder sent twice. T3: approved request still shows as pending in the console. T4: approver cannot see requests from the EMEA team. T5: hold released automatically overnight without approval.",
                  "T1: invoice total differs from the usage page by about two percent. T2: usage page double counts cached requests. T3: invoice shows a model we never enabled. T4: credit applied twice then reversed. T5: usage export missing the last day of the month. T6: currency conversion rounds differently on invoice and report. T7: budget alert fired after the cap was already exceeded."]}),
    ("Map our controls to {fw}. Here is what we have today: {ctl}. Identify the gaps, the evidence we are missing, and a ninety-day remediation plan with sequencing and owners.",
     {"fw": ["SOC 2 Type II", "ISO 27001 Annex A", "the EU AI Act obligations for a limited-risk system", "PCI DSS v4 for a service that touches card data"],
      "ctl": ["annual pen tests, SSO for staff, quarterly access reviews done in spreadsheets, and no written vendor risk process",
              "infrastructure as code with peer review, centralised logs kept thirty days, manual offboarding, and an undocumented incident process",
              "model cards for two models, no data lineage tooling, and human review on a sample of outputs only"]}),
    ("Our {svc} p99 latency regressed from {a} to {b} after {chg}. Profile summary: {prof}. Rank the probable causes by likelihood and design experiments that isolate them with the least production risk.",
     {"svc": ["checkout API", "search service", "LLM gateway", "ledger writer"], "a": ["180 ms", "45 ms", "600 ms"], "b": ["900 ms", "310 ms", "2.4 s"],
      "chg": ["a dependency upgrade and a config change to connection limits", "moving to a new node type with more cores", "enabling request compression and a new tracing library"],
      "prof": ["more time in garbage collection, lock contention on a shared cache, and a new synchronous call to the feature-flag service",
               "CPU is flat but the wait on the database pool grew five times, and a hot key appears in the cache metrics",
               "most added time is in TLS handshakes to an upstream provider, with connection reuse disabled in the client since the change"]}),
    ("Design a {feat} for a multi-region ledger that needs exactly-once payout semantics, a {rpo} recovery point objective, and region failover. Discuss the consistency choices, idempotency, reconciliation with the bank, and the operational runbooks.",
     {"feat": ["payout scheduler", "settlement service", "refund pipeline", "balance reservation system"], "rpo": ["zero", "five-second", "one-minute"]}),
    ("Design the failure handling for {thing}: what breaks first, how do we detect it, and what do we do about partial writes?",
     {"thing": ["a cross-region replicated ledger", "an agent workflow that calls five external APIs", "a batch billing run over 40 million accounts", "a saga spanning inventory, payment and shipping"]}),
    ("Propose a zero-downtime schema change strategy for a {size} table that {serves}, including the backfill and the rollback path.",
     {"size": ["2 TB", "600 GB", "9 TB"], "serves": ["serves live checkout traffic", "is read by three downstream teams via replicas", "is written by both a legacy monolith and a new service"]}),
    ("Why would a {thing} fail only under load, and how would you redesign it to tolerate partial failure across regions?",
     {"thing": ["payment authorisation service", "distributed rate limiter", "agent orchestration queue", "multi-tenant search index", "ledger reconciliation job"]}),
    ("Draft a migration and rollback strategy for splitting a {size} monolith database into per-service databases with no write downtime.", {"size": SIZES}),
    ("We need exactly-once behaviour across a message queue and a database. What are our realistic options, and what does each one cost us operationally?", {}),
    ("Evaluate whether we should build or buy an agent policy engine, given audit requirements, a five-person team and a two-quarter deadline.", {}),
    ("Assess the trade-offs of moving {a} to {b} in a payments stack with strict audit requirements.",
     {"_": [{"a": "a synchronous approval flow", "b": "an event-driven one"}, {"a": "self-managed Kafka", "b": "a managed streaming service"},
            {"a": "per-service databases", "b": "a shared ledger database"}, {"a": "long-lived API keys", "b": "short-lived workload credentials"}]}),
]

CLAIMS = ["the square root of 2 is irrational", "the sum of two odd integers is even", "there are infinitely many prime numbers",
          "the product of any two consecutive integers is even", "every integer greater than 1 has a prime factorisation",
          "the sum of the first n odd numbers equals n squared", "there is no largest even number", "the cube of an odd integer is odd"]
SERIES = ["1 + 2 + 3 + ... + n", "1^2 + 2^2 + ... + n^2", "1 + 1/2 + 1/4 + ... (the geometric series with ratio 1/2)",
          "the sum of the first n Fibonacci numbers", "1*2 + 2*3 + ... + n*(n+1)", "the arithmetic series with first term a and difference d"]
PUZZLES = [
    "Three boxes are labelled 'apples', 'oranges' and 'mixed', and every label is wrong. You may draw one fruit from one box. Which box do you pick from, and how do you relabel all three?",
    "On an island, knights always tell the truth and knaves always lie. A says 'B is a knave.' B says 'A and I are the same kind.' What are A and B?",
    "Five houses in a row each have a different colour, and each owner drinks a different beverage. The tea drinker lives next to the green house, and the coffee drinker lives in the red house. Work out who can own the blue house.",
    "Two trains 300 km apart head toward each other at 70 and 80 km/h, and a bird flies between them at 100 km/h until they meet. How far does the bird travel?",
    "A farmer must ferry a wolf, a goat and a cabbage across a river in a boat that holds him and one item. Find a sequence of crossings where nothing gets eaten.",
    "Four people must cross a bridge at night with one torch, taking 1, 2, 5 and 10 minutes, and at most two can cross at once. What is the minimum total time?",
]
ALGOS = ["binary search on a sorted array", "insertion sort", "Euclid's algorithm for the greatest common divisor", "Dijkstra's shortest path algorithm with non-negative weights",
         "merge sort", "the Boyer-Moore majority vote algorithm", "Kadane's maximum subarray algorithm", "Floyd's tortoise and hare cycle detection"]
WORD_PROBLEMS = [
    "A tank is filled by pipe A in 6 hours and pipe B in 9 hours, and drained by pipe C in 12 hours. With all three open, how long to fill it from empty?",
    "A store raises a price by 20 percent and later discounts the new price by 20 percent. By what percent does the final price differ from the original?",
    "How many ways can 6 people sit around a circular table if two particular people must not sit next to each other?",
    "A loan of 10,000 at 6 percent annual interest compounded monthly is repaid in equal monthly payments over 3 years. What is the monthly payment?",
    "Two dice are rolled. Given that the sum is at least 9, what is the probability that at least one die shows a 6?",
]
STATEMENTS = ["the sum of the first n cubes equals the square of the sum of the first n integers", "2^n > n^2 for every integer n >= 5",
              "every tree with n vertices has exactly n - 1 edges", "n^3 - n is divisible by 6 for every integer n",
              "the nth Fibonacci number is less than 2^n", "a binary tree of height h has at most 2^(h+1) - 1 nodes"]
ARGUMENTS = [
    "All agents that hold a valid passport may call the tool. Agent K has no valid passport. Therefore agent K may not call the tool.",
    "If the budget cap is exceeded, the gateway returns 429. The gateway returned 429. Therefore the budget cap was exceeded.",
    "Every approved request is logged. Some logged requests are later revoked. Therefore some approved requests are later revoked.",
    "No unreviewed change ships on Friday. This change ships on Friday. Therefore this change is reviewed.",
    "If the cache is cold, latency is high. Latency is not high. Therefore the cache is not cold.",
]
CODE_SNIPPETS = [
    "T(n) = 2T(n/2) + n log n", "T(n) = 3T(n/4) + n", "T(n) = T(n-1) + log n", "T(n) = 4T(n/2) + n^2",
    "T(n) = T(n/2) + T(n/4) + n", "T(n) = 2T(n-1) + 1",
]
EVENTS = [
    "at least two of five fair coin flips land heads given that the first flip is tails",
    "a random permutation of 1 to 5 has no fixed point", "three cards drawn without replacement from a standard deck are all hearts",
    "two randomly chosen points on a unit interval are more than half a unit apart",
    "a fair die rolled four times shows a six at least once",
]
SYSTEMS = [
    {"prop": "mutual exclusion", "sys": "a lock service that grants a lease with a fencing token"},
    {"prop": "no two replicas commit different values for the same slot", "sys": "a simplified Paxos acceptor and proposer"},
    {"prop": "a message is never delivered twice", "sys": "an idempotent consumer that stores processed ids transactionally"},
    {"prop": "the balance never goes negative", "sys": "a ledger that reserves funds before confirming a payout"},
]
RIDDLES = [
    "You have 12 coins, one of which is counterfeit and either heavier or lighter. Using a balance scale three times, how can you find it and tell which it is?",
    "Ten prisoners each get a hat with a number from 1 to 10 (repeats allowed) and must each guess their own number, seeing only the others'. Can a strategy guarantee at least one is right?",
    "A clock's hour and minute hands overlap at 12:00. At what next time do they overlap exactly?",
    "100 lockers are all closed. Student k toggles every k-th locker for k = 1 to 100. Which lockers end up open?",
]
VARIABLES = ["a geometric random variable with success probability p", "the number of fixed points of a uniformly random permutation of n items",
             "the sum of two independent fair dice", "the number of trials to see the first six on a fair die", "a binomial random variable with n trials and probability p"]
PROOFS = [
    "Claim: n^2 + n is always even. Proof: if n is even then n^2 is even and n is even so the sum is even. If n is odd then n^2 is odd and n is odd so the sum is odd. Hence it is always even.",
    "Claim: the sum 1 + 2 + ... + n equals n(n+1)/2. Proof: true for n = 1. Assume true for n = k, then for n = k + 1 the sum is k(k+1)/2 + k + 1, which is (k+1)(k+2)/2 by algebra.",
    "Claim: every graph with n vertices and at least n edges contains a cycle. Proof: a graph with no cycle is a forest, which has at most n - 1 edges, so any graph with n or more edges must contain a cycle.",
]
CONJECTURES = ["for every prime p greater than 3, p^2 - 1 is divisible by 24", "every even integer greater than 2 is the sum of two primes below 100",
               "the product of four consecutive integers is always a perfect square", "n^2 + n + 41 is prime for every non-negative integer n",
               "for all real x, (1 + x)^n >= 1 + nx when n >= 1 and x >= -1"]

LONG_PUZZLES = [
    "Six engineers, Ada, Ben, Chloe, Dev, Eli and Fay, must each be assigned one of three on-call shifts, two per shift. Ada and Ben cannot share a shift. Chloe must be on the same shift as Dev. Eli refuses the third shift. Fay must not be on the first shift. Find every valid assignment.",
    "A warehouse has three conveyor belts feeding one packer. Belt A delivers 12 items a minute, belt B delivers 8, and belt C delivers 5, but the packer handles only 20 a minute and a queue of up to 30 items can build up. Starting from an empty queue, determine when it first overflows and what happens afterwards.",
    "Four agents each hold a different permission: read, write, approve, or deploy. The approver never holds write. The deployer is not agent 2. Agent 1 holds neither read nor deploy. Agent 3 holds write. Work out who holds what.",
]
REASONING_EXTRA = [
    ("Consider the following scheduling problem. {p} Work through it carefully, show each step of your reasoning, and check your final answer against every constraint.", {"p": LONG_PUZZLES}),
    ("Here is a puzzle from our on-call training. {p} Solve it step by step and prove that your solution is the only one.", {"p": LONG_PUZZLES}),
]

REASONING: list[tuple[str, dict]] = [
    ("Prove that {c}. Show every step of the argument.", {"c": CLAIMS}),
    ("Derive a closed form for {s} and justify each step.", {"s": SERIES}),
    ("Solve this logic puzzle step by step: {p}", {"p": PUZZLES}),
    ("Prove the correctness of {a}. State a loop invariant and show initialization, maintenance and termination.", {"a": ALGOS}),
    ("Think carefully and work through this problem step by step, then verify your result: {w}", {"w": WORD_PROBLEMS}),
    ("Show rigorously, by induction, that {s}.", {"s": STATEMENTS}),
    ("Use formal logic to decide whether this argument is valid, and show the derivation. {a}", {"a": ARGUMENTS}),
    ("Solve the recurrence {r} with a rigorous derivation, and state the resulting asymptotic bound.", {"r": CODE_SNIPPETS}),
    ("Compute the probability that {e}. Reason carefully through each case.", {"e": EVENTS}),
    ("Formally verify that {prop} holds for {sys}: state the invariants and prove every transition preserves them.", {"_": SYSTEMS}),
    ("Reason step by step and explain why your answer is right: {r}", {"r": RIDDLES}),
    ("Carefully derive the expected value and variance of {v}, showing each algebraic step.", {"v": VARIABLES}),
    ("Is the following proof correct? {p} Check every step and point out any flaw.", {"p": PROOFS}),
    ("Prove or disprove: {c}. Give a complete formal argument.", {"c": CONJECTURES}),
    *REASONING_EXTRA,
]

CLASS_GROUPS = {"cheap": CHEAP, "default": DEFAULT, "hard": HARD, "reasoning": REASONING}


def groups() -> dict[str, list[str]]:
    """label -> its group ids, in a fixed order."""
    return {lab: [f"{CODE}.{lab}.{i:02d}" for i in range(1, len(CLASS_GROUPS[lab]) + 1)] for lab in LABELS}


def _wrap(text: str, rng) -> str:
    if rng.random() < WRAP_PREAMBLE_P:
        text = rng.choice(PREAMBLES) + text
    elif rng.random() < WRAP_PREFIX_P:
        pre = rng.choice(PREFIXES)
        text = pre + (text[0].lower() + text[1:] if pre.endswith(", ") else text)
    if rng.random() < WRAP_SUFFIX_P:
        text += rng.choice(SUFFIXES)
    return text


def generate(seed: int) -> list[Case]:
    rng = rng_for(seed, FAMILY)
    per_class = ROWS_PER_FAMILY // len(LABELS)
    cases: list[Case] = []
    seen: set[str] = set()
    for lab in LABELS:
        gids = groups()[lab]
        counts = spread(rng, per_class, gids)
        for gi, gid in enumerate(gids):
            template, pools = CLASS_GROUPS[lab][gi]
            for _ in range(counts[gid]):
                for _try in range(200):
                    text, slots = fill(template, pools, rng)
                    text = _wrap(text, rng)
                    if text not in seen:
                        break
                else:
                    raise RuntimeError(f"{gid}: cannot draw {counts[gid]} distinct prompts")
                seen.add(text)
                cases.append(Case(FAMILY, TEMPLATE, {"prompt": text}, lab, gid, {"class": lab, "slots": slots}))
    return finalize(cases, rng, TEMPLATE)


def strata() -> dict[str, list[str]]:
    return groups()


def has_reasoning_cue(prompt: str) -> bool:
    return bool(REASONING_CUES.search(prompt))
