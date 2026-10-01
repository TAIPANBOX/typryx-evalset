# typryx-evalset

A labelled set of 3000 synthetic typed questions, for measuring how well a backend
answers them: a question goes in, a choice, a score or a yes/no comes out, and the
truth is known because the question was built from it.

[![check](https://github.com/TAIPANBOX/typryx-evalset/actions/workflows/check.yml/badge.svg)](https://github.com/TAIPANBOX/typryx-evalset/actions/workflows/check.yml)
![python 3, stdlib only](https://img.shields.io/badge/python-3%20stdlib%20only-4493f8)
![license Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-9aa7b8)

It is the test bench for [typryx](https://github.com/TAIPANBOX/typryx), the optional
typed-answers service of the TAIPANBOX agent stack. typryx asks a backend (a hosted
typed-decision API, or any OpenAI-compatible model a customer runs themselves) for a
typed answer with a probability. This repository lets you put numbers on a backend
before you rely on it: accuracy, calibration and latency, on questions it has never seen.

## What is in the set

3000 rows, English, six families, 500 rows each. Each family mirrors a place where the
stack asks a typed question.

| Family | Answer type | Options |
|---|---|---|
| `request.complexity` | choice | cheap, default, hard, reasoning |
| `triage.anomaly_class` | choice | expected_growth, runaway_agent, misconfiguration, price_change, unknown |
| `eval.outcome_met` | yes/no | true, false |
| `eval.answer_quality` | score | 0, 1, 2, 3 |
| `action.risk_class` | choice | read_only, reversible_change, destructive, external_send, financial |
| `console.question_topic` | choice | spend, incident, identity, approval, other |

The six typryx templates are in `templates/`. A row looks like this:

```json
{"family":"request.complexity","gold":"cheap","group":"cx.cheap.16","id":"cx-0004","source":"construct","state":{"prompt":"Hey, convert to uppercase: rollback finished"},"template":"request.complexity"}
```

**Truth is by construction.** Every row is generated from parameters that decide the
label: a scenario with numbers for calls, traffic and price, an arithmetic task with a
right answer or a guaranteed near miss, a fact bank with a known number of correct
items. No model's opinion is ever the label. The unit tests recompute every gold from
the row's own parameters with an independent reference rule.

**Distractor fields.** About one row in five carries one extra field the template does
not name (a `customer_email`, an `internal_note`). typryx must not send it to the
backend, so the set also exercises the egress filter. All such values are made up.

**The split is by group, not by row.** A group is one phrasing template, or one
scenario-rendering template. Whole groups go to train, dev or test, about 70/15/15 per
family, with every label present in every split. The test split therefore contains
phrasings that the train split never showed, which is what makes it a measure of
generalisation and not of memory. 366 groups in total, none in more than one split
(`scripts/no-group-leak.sh`).

| Split | Rows |
|---|---|
| train | 2141 |
| dev | 425 |
| test | 434 |

**The test split is frozen.** `data/MANIFEST.json` records its sha256:

```
bd5f3cf42b81bb1ba14938b84c0bf321df4ed1f6ec96015950c1357033bab03f  data/test.jsonl
```

`scripts/test-frozen.sh` fails if the file changes, and the benchmark runner refuses to
run the test split against a file that does not match. Each re-freeze, and why, is one
line in `data/CHANGELOG.md`.

## How the labels were checked

Construction guarantees that a label follows from the parameters. It does not guarantee
that a reader looking only at the rendered text would pick the same label, so the text
was checked separately. An independent annotator model, reading the question text and the
options without seeing the gold, re-labelled rows blind in four passes. The later passes
covered the rows that earlier rule fixes had regenerated, and the last one covered the
whole test split.

The first three passes found disagreements. The defects were traced to rules in the
generator and fixed there, not patched row by row: how a vague item in an answer counts,
how a dominant cause in a cost anomaly is decided, where the gray zones sit. The affected
families were regenerated and the test file was re-frozen. The three re-freezes
and their reasons are in `data/CHANGELOG.md`. The fourth pass agreed with the gold label
on 434 of 434 rows of the test split.

All three re-freezes happened before any backend was run on the test split.

## Regenerate it

```sh
python3 -m gen.build
```

Python 3, standard library only. The same seed (20260930) gives byte-identical files:
running the command on a clean checkout changes nothing in `data/`. `--seed` and `--out`
build a different set in a different place.

## Run the checks

```sh
scripts/check.sh
```

This runs the unit tests, five gates, and the gates' own teeth test:

| Gate | What it holds |
|---|---|
| `test-frozen.sh` | `data/test.jsonl` matches the sha256 in the manifest |
| `no-group-leak.sh` | no group appears in more than one split |
| `labels-by-construction.sh` | every gold is recomputed from its row and matches |
| `no-jev.sh` | no file but this README and the spec names the hosted service, its host or a key path |
| `no-secrets.sh` | no key-shaped string in any tracked file or anywhere in git history |

`scripts/gates-have-teeth.sh` plants each gate's own fault in a throwaway copy of the
repository and requires the gate to fail, requires it to stay quiet on a change that is
not a fault, and requires it to say "measured nothing" when its subject is gone.
`scripts/red_first.py` runs the tests against a set of deliberately broken generators and
requires each one to turn a test red.

Set `TYPRYX_DIR` to a typryx checkout and `check.sh` also runs typryx's own template
checker over `templates/`.

## Benchmark a typryx deployment

Start typryx with the backend you want to measure, then:

```sh
python3 bench/run.py --typryx-url http://127.0.0.1:4320 --key-file PATH \
    --backend-name NAME --split test --out results/NAME.jsonl

python3 bench/metrics.py results/NAME.jsonl
```

- One `POST /v1/ask` per row, with the credential read from the key file. The key is
  never printed, logged or written to the output.
- A row that fails (HTTP error, timeout, unreadable body) is recorded as unanswered and
  never aborts the run. The run can be resumed: ids already in the output are skipped.
- The runner talks only to the URL you give it. Proxy environment variables are ignored.
- `bench/metrics.py` takes any number of result files and groups rows by backend name,
  overall and per family. It reports accuracy with a Wilson 95% interval, Brier score,
  expected calibration error (10 equal-width bins on the highest probability), p50 and p95
  latency, cost, unanswered count and held-back fields. An unanswered row counts as wrong
  for accuracy and is left out of Brier and ECE, and both counts are shown.

`results/` is in `.gitignore`. Results files stay on the machine that produced them.

## The two no-model baselines

Two baselines need no model and no service, so a backend has something to be compared
with. Both write the same result shape the runner writes, and both refuse the test split
if it has changed.

```sh
python3 -m baseline.predict --which constant --split test --out results/constant.jsonl
python3 -m baseline.predict --which rules    --split test --out results/rules.jsonl
```

- **constant**: for every family, always answer the most frequent label in the train
  split. It stands for what the stack does without typryx: one default answer.
- **rules**: a short keyword and regex function per family, an afternoon's work. Written
  by reading train rows and checked on dev.

The rules baseline flatters itself. It was tuned on train rows from the same generator
that produced the test rows, so it knows the vocabulary the generator draws from, even
though it has not seen the test phrasings. Read its number as an upper bound on what
rules of that kind would do on real operator text, not a typical result.

## The CPU VM recipe

`vm/setup.sh` is the script used to stand up the machine for the local-model run: Debian
12 on an 8-vCPU machine, Ollama with `qwen2.5:7b`, bound to `127.0.0.1` so nothing
listens on a public interface. Read it before running
it: it installs packages and pulls model weights, and it is meant for a throwaway VM, not
your workstation.

## Results

Measured 2026-09-30 on the frozen test split (434 rows, sha256 above). Overall accuracy
with a 95% Wilson interval, expected calibration error (lower is better), and p50
latency as typryx itself measured it per ask (`latency_ms`). One run per row of the table.

| Backend | Accuracy | 95% interval | ECE | p50 latency | Where it ran |
|---|---|---|---|---|---|
| constant (no model) | 25.1% | [21.3, 29.4] | 0.749 | n/a | locally, `baseline/predict.py` |
| rules (no model) | 82.3% | [78.4, 85.6] | 0.177 | n/a | locally, `baseline/predict.py` |
| typryx + Jev (TypeSafe AI, `jev-1.13.0`) | 87.1% | [83.6, 89.9] | 0.042 | 229 ms | hosted service, called from a developer laptop |
| typryx + qwen2.5:7b via Ollama | 70.0% | [65.6, 74.2] | 0.273 | 2130 ms | 8-vCPU CPU VM (n2-standard-8), model on the VM's loopback |

How to read it:

- The two baselines answer with probability 1.0, so their ECE is simply 1 minus their
  accuracy. They are certain and often wrong.
- The hosted service is the most accurate and by far the best calibrated of the four. The
  local 7B model on CPU is less accurate than the rules baseline and poorly calibrated
  here, and slow on this hardware. It is also the only model row where nothing leaves the
  machine.
- The hosted latency includes the network path from a laptop, so it depends on where you
  call from. The local latency is what an 8-vCPU machine without a GPU does with a 7B
  model. Both are one setup each, not load tests.
- The questions are synthetic, so nothing private was sent to the hosted service.
- Per-family intervals are wide. Each family has about 70 test rows, and at that size an
  accuracy near 87% carries a 95% interval roughly 16 points across, and one near 70%
  roughly 21. Differences between backends on a single family are mostly within noise.
  Within one backend a family can still stand clear of another: see the next table.
  The overall figures, at 434 rows, are the ones to read.

The hosted service by family, the same run (accuracy with its 95% Wilson interval, and
ECE):

| Family | Rows | Accuracy | 95% interval | ECE |
|---|---|---|---|---|
| `action.risk_class` | 69 | 100.0% | [94.7, 100.0] | 0.023 |
| `console.question_topic` | 69 | 100.0% | [94.7, 100.0] | 0.038 |
| `request.complexity` | 71 | 98.6% | [92.4, 99.8] | 0.102 |
| `triage.anomaly_class` | 77 | 87.0% | [77.7, 92.8] | 0.085 |
| `eval.outcome_met` | 73 | 69.9% | [58.6, 79.2] | 0.165 |
| `eval.answer_quality` | 75 | 69.3% | [58.2, 78.6] | 0.153 |

The three families where an answer is recognised (risk, topic, complexity) sit clear of
the two where work has to be checked (outcome met, answer quality): their intervals do
not overlap. Triage sits between the two groups.

The result files behind these numbers are kept outside the repository.

## What is in this repository, and what is not

This repository contains no output of any hosted model. Results files are kept outside
the repository. The hosted typed-decision service's terms forbid using its output to
train another model, and nothing here does that: the truth of every row comes from
construction, no row was labelled or altered by a model's answer, and `no-jev.sh` fails
if any file names the service, its host or a key path outside this README and the spec.
(The annotator model in the label check above read the question text and the options
only, and decided nothing in the set by itself: a disagreement led to a change in a
generator rule, never to an edited label.)

`@decided 2026-09-30`: a customer of the stack chooses one of three data modes for typed
answers. Use the hosted typed-decision service, where only the fields a template names
leave for the vendor. Use their own model on their own hardware, where nothing leaves.
Or turn typed answers off.

`@decided 2026-09-30`: we do not fine-tune or ship models for customers. A customer can
fine-tune and calibrate their own model on their own data, and this repository is one of
the tools for measuring that: a frozen test, a calibration-aware metric and two baselines
to beat. Keep the test split out of any tuning, or its number stops meaning anything.

## Not proven

- **Real traffic.** Every question is synthetic and generated from templates. How any
  backend does on real operator text, which varies more than a generator does, has not
  been measured here.
- **Human agreement.** The labels were checked by an annotator model, not by people. It
  shows the labels read the way the text says they do, to that model.
- **One run each.** Each row of the results table is a single run on one day. Run-to-run
  variance is not measured. A hosted service can change under you, so its number is a
  statement about 2026-09-30.
- **One local model, one machine.** Only one open model at one size, on one CPU setup, was
  measured. Nothing here says how other models, quantisations or GPUs compare.
- **Latency under load.** The latencies are sequential single-setup figures, not load
  tests.
- **Calibration outside this distribution.** ECE is measured on this set only.
- **Per-family comparisons between backends.** Not made here. The per-family table above
  is for one backend, and only the separations whose intervals do not overlap are read
  from it.
- **Contamination from here on.** The test split is public and frozen. Anything tuned on
  it, or on a model that saw this repository, makes its own result here meaningless.
- **Downstream value.** That a better typed answer improves an agent's outcome, or lowers
  its cost, is not measured. Cost figures are not part of the table.

## Layout

| Path | What lives there |
|---|---|
| `SPEC.md` | the specification the set was built to |
| `templates/` | the six typryx templates the questions are asked under |
| `gen/` | one generator per family, and `gen/build.py`, the builder and splitter |
| `data/` | `all`, `train`, `dev` and `test` as JSONL, `MANIFEST.json`, `CHANGELOG.md` |
| `bench/` | `run.py` (ask a typryx every row) and `metrics.py` |
| `baseline/` | the constant and rules baselines |
| `scripts/` | the gates, their teeth test, `check.sh`, `red_first.py` |
| `tests/` | unit tests, standard library `unittest` only |
| `vm/` | the CPU VM recipe |
| `.github/workflows/` | `check.yml`, which runs `scripts/check.sh` on push and pull request |

## License

Apache-2.0. See [LICENSE](LICENSE).
