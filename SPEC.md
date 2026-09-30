# typryx-evalset: spec for the stage-2 dataset

Owner: the principal session. Implementer: one subagent. Private repository (local git
only until the owner says otherwise; do NOT create a GitHub repo, do NOT push).

## Purpose

A labelled set of typed questions that typryx's real consumers will ask, used to
(1) compare typryx's backends on the SAME questions (no typryx / local model / Jev) and
(2) fine-tune an open local model. Truth comes from construction, never from a model's
answer, and NEVER from Jev (TypeSafe's agreement forbids using Jev output to train another
model; nothing in this repo may call Jev or read Jev output).

## Shape

- Python 3 stdlib only (no pip installs). `random.Random(seed)` only; same seed gives
  byte-identical output. Tests with stdlib `unittest`.
- `templates/*.json`: six typryx templates, same schema as
  `~/Development/typryx/examples/templates/*.json` (copy the four existing ones verbatim,
  add the two new ones below). Validate them with the real typryx binary if convenient:
  `cd ~/Development/typryx && go run ./cmd/typryx templates check <dir>` (check the actual
  subcommand name in cmd/typryx/main.go before relying on it).
- `gen/<family>.py`: one generator per family. `gen/build.py` writes
  `data/all.jsonl`, then `data/train.jsonl`, `data/dev.jsonl`, `data/test.jsonl`, and
  `data/MANIFEST.json` (counts per family x split x label, seed, generator git commit,
  sha256 of each split file).
- One JSONL row: `{"id","family","template","state":{...},"gold":<label>,
  "group":"<phrasing-or-scenario group id>","source":"construct"}`.
  `gold` is an option key for choice, an integer index for score, `true`/`false` for noul.
  `state` holds ONLY the template's `fields` plus, in about 20% of rows, ONE extra
  distractor field (e.g. `customer_email`, `internal_note`) that the template does not
  name, so the egress filter is exercised.

## Families, 500 rows each, 3000 total, English

1. `request.complexity` (choice: cheap/default/hard/reasoning; field `prompt`).
   Build prompts from per-class slot templates with many phrasings: cheap = short
   factual lookup or trivial transform; default = ordinary writing/summarising/explaining
   of moderate length; hard = long-context, multi-step, domain-deep work (legal, infra
   migration, data pipeline design) WITHOUT an explicit ask for step-by-step proof;
   reasoning = explicitly asks for rigorous proof, formal derivation, or careful
   step-by-step reasoning (math, logic puzzles, algorithm correctness). Keep the classes
   separable by construction; balanced 125 each.
2. `triage.anomaly_class` (choice: expected_growth/runaway_agent/misconfiguration/
   price_change/unknown; fields `anomaly`, `recent_changes`). Generate from numeric
   scenario parameters (calls delta, unique-request ratio, unit price delta, traffic
   delta, a config event or none) and RENDER them as operator-style text; the label is a
   deterministic function of the parameters. `unknown` = parameters deliberately
   insufficient or contradictory. 100 each.
3. `eval.outcome_met` (noul; fields `task`, `final_answer`). Checkable tasks: arithmetic
   (+,-,x), unit conversion, weekday of a given date, counting items in a list, string
   ops (reverse, uppercase, letter count), sorting a short list. Right answer or a
   plausible near miss, guaranteed different. 250 true / 250 false, balanced per task kind.
4. `eval.answer_quality` (score 0..3; fields `task`, `final_answer`). Tasks that ask for
   N concrete items or steps (e.g. "List four causes of X", "Give three steps to Y") with
   a fixed fact bank per task; answer built at a level: 3 = all items correct and
   clear; 2 = all but one item, or one item vague; 1 = only one or two items; 0 =
   off-topic answer. 125 per level.
5. `action.risk_class` (NEW, choice; fields `tool`, `arguments`, `target`). Classifies an
   agent's pending tool call for a Wardryx policy signal. Options and criteria:
   - `read_only`: reads or lists data, changes nothing
   - `reversible_change`: changes state in a way that can be undone (create a draft,
     add a label, update a non-critical setting)
   - `destructive`: deletes or overwrites data or infrastructure, hard to undo
   - `external_send`: sends data or a message outside the organisation (email, webhook,
     public post, upload to a third party)
   - `financial`: moves money, buys, refunds, or changes billing
   Build from a tool catalogue (github, slack, email, s3, k8s, stripe, db, jira, ...)
   with argument variants; label by construction. 100 each.
6. `console.question_topic` (NEW, choice; field `question`). Routes an operator's question
   to the right Felyx data source. Options: `spend` (cost, budget, invoices, token spend),
   `incident` (outages, errors, alerts, degraded service), `identity` (agent identities,
   keys, credentials, suspicious logins, delegation), `approval` (pending approvals,
   holds, who must sign off), `other` (anything else, including general how-to).
   Many phrasings per topic; 100 each.

New template JSON for 5 and 6 follows the existing shape (`id`, `type`, `instructions`,
`criteria`, `fields`, `max_state_bytes: 16384`).

## Split, the part that matters most

Split by `group`, never by row: a group is one phrasing template (families 1, 3, 4, 5, 6)
or one scenario-rendering template (family 2). Assign whole groups to train/dev/test at
about 70/15/15 per family, stratified so every label appears in every split. So the test
set measures generalisation to phrasings the model never saw, not memorised templates.
Each family must have enough distinct phrasing templates for this to be meaningful: at
least 20 per family, more is better.

## Gates (scripts/, bash, each with a teeth case in scripts/gates-have-teeth.sh)

- `scripts/test-frozen.sh`: recomputes sha256 of `data/test.jsonl` and compares with
  `data/MANIFEST.json`; a changed test file fails. Teeth: flip one byte in a temp copy.
- `scripts/no-group-leak.sh`: no `group` appears in more than one split. Teeth: plant a
  duplicated group.
- `scripts/labels-by-construction.sh`: runs the unit tests that recompute every
  constructible `gold` from the row's own generator parameters (families 2, 3, 5 fully;
  others by their construction rule) and fail on any mismatch. Teeth: flip a gold label.
- `scripts/no-jev.sh`: no file in the repo mentions `api.typesafe.ai`, `jev` as a
  backend, or a Jev key path. Teeth: plant the URL.
- A gate must say "measured nothing" and fail if its subject file is missing.

## Tests (unittest)

Determinism (same seed, same bytes); balance per family x label; every gold valid for
its template; every row's `state` keys = template fields plus at most one distractor;
distractor rate 15-25%; ids unique; near-miss answers differ from the right one;
split proportions within tolerance; each of the tests above must be run once against a
deliberately broken generator and shown to fail (red first), then green.

## Deliverable back to the principal

Report: file tree, counts table (family x split x label), sha256 of test.jsonl, number of
groups per family per split, gates and tests output (with the red-first evidence), five
sample rows per family from test.jsonl, and a NOT PROVEN line. Commit locally with
`Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. No push, no GitHub repo.
