"""Shared machinery for the six family generators.

Rules every generator follows (and tests/ enforces):

- stdlib only; all randomness comes from a `random.Random` built by `rng_for`
  from (seed, name), so the same seed gives byte-identical output and no
  family's draws shift another family's;
- never iterate a `set` of strings where order matters (hash randomisation);
- a generator returns `Case` objects. The row written to disk carries only
  the spec's keys; `Case.params` is the generator's own record of how the
  truth was built, used by the tests to recompute the label.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"

ROWS_PER_FAMILY = 500

#: Distractor fields: real-looking extras the templates do NOT name, so the
#: egress filter has something to drop. Values never depend on the label.
DISTRACTORS: dict[str, list[str]] = {
    "customer_email": [
        "jordan.lee@example.com", "priya.nair@example.org", "sam.okafor@example.net",
        "lena.fischer@example.com", "tomasz.kowal@example.org", "ana.ruiz@example.net",
        "mei.tanaka@example.com", "omar.haddad@example.org",
    ],
    "internal_note": [
        "escalated by oncall, ticket pending", "copied from the shared doc, unreviewed",
        "flagged for the weekly review", "do not forward outside the platform team",
        "added by the intake form", "raw paste, may contain typos",
        "low priority per triage rota", "reviewer asked to keep this verbatim",
    ],
    "requester_ip": [
        "203.0.113.17", "198.51.100.42", "203.0.113.88", "198.51.100.7",
        "203.0.113.240", "198.51.100.133",
    ],
    "trace_id": [
        "tr-7f3a91c2", "tr-0be44d10", "tr-c81f2a66", "tr-5d09e7b3", "tr-a2240f9e", "tr-19c7d5a4",
    ],
    "owner_team": [
        "platform", "payments", "data-eng", "support-tools", "sre", "ml-infra", "growth",
    ],
    "slack_handle": [
        "@dmitri", "@noor", "@kaveh", "@ingrid", "@bao", "@sofia", "@mateo",
    ],
}
DISTRACTOR_NAMES = list(DISTRACTORS)
DISTRACTOR_RATE = 0.20


def rng_for(seed: int, name: str) -> random.Random:
    # A str seed is hashed with sha512 by random.seed (version 2), which is
    # independent of PYTHONHASHSEED.
    return random.Random(f"typryx-evalset|{seed}|{name}")


def load_template(template_id: str) -> dict:
    return json.loads((TEMPLATES_DIR / f"{template_id}.json").read_text())


@dataclass
class Case:
    family: str
    template: str
    state: dict
    gold: object
    group: str
    params: dict = field(default_factory=dict)
    distractor: str | None = None  # name of the extra state key, if any


def spread(rng: random.Random, total: int, keys: list) -> dict:
    """Split `total` as evenly as possible over `keys`; the remainder goes
    to randomly chosen keys, so no key is systematically favoured."""
    base, rem = divmod(total, len(keys))
    out = {k: base for k in keys}
    for k in rng.sample(keys, rem):
        out[k] += 1
    return out


_SLOT = re.compile(r"\{(\w+)\}")


def fill(template: str, pools: dict, rng: random.Random) -> tuple[str, dict]:
    """Fill `{slot}` placeholders from `pools`. A pool entry may be a str or a
    dict of correlated slot values (under the key `_`). Returns the text and
    the chosen slot values."""
    chosen: dict = {}
    combos = pools.get("_")
    if combos:
        chosen.update(rng.choice(combos))
    for name in _SLOT.findall(template):
        if name in chosen:
            continue
        chosen[name] = rng.choice(pools[name])
    return _SLOT.sub(lambda m: str(chosen[m.group(1)]), template), chosen


def finalize(cases: list[Case], rng: random.Random, template_id: str, label_of=None) -> list[Case]:
    """Shuffle, then attach the distractor to exactly 20% of rows per label
    (so the distractor rate cannot correlate with the label). Checks that the
    state holds exactly the template's fields before any distractor."""
    tpl = load_template(template_id)
    fields = set(tpl["fields"])
    for c in cases:
        if set(c.state) != fields:
            raise ValueError(f"{template_id}: state keys {sorted(c.state)} != fields {sorted(fields)}")
    cases = list(cases)
    rng.shuffle(cases)
    by_label: dict = {}
    for c in cases:
        by_label.setdefault(json.dumps(c.gold), []).append(c)
    for key in sorted(by_label):
        members = by_label[key]
        k = round(DISTRACTOR_RATE * len(members))
        for c in rng.sample(members, k):
            name = rng.choice(DISTRACTOR_NAMES)
            c.state[name] = rng.choice(DISTRACTORS[name])
            c.distractor = name
    return cases


def rows_for(cases: list[Case], code: str) -> list[dict]:
    rows = []
    for i, c in enumerate(cases, 1):
        rows.append({
            "id": f"{code}-{i:04d}",
            "family": c.family,
            "template": c.template,
            "state": c.state,
            "gold": c.gold,
            "group": c.group,
            "source": "construct",
        })
    return rows


def dumps(row: dict) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def split_groups(rng: random.Random, strata: dict[str, list[str]]) -> dict[str, str]:
    """Assign whole groups to train/dev/test, about 70/15/15, per stratum.

    `strata` maps a stratum name (a label for families whose phrasings are
    label-specific, else one shared stratum) to its group ids. Within each
    stratum, groups are shuffled and the first n_dev go to dev, the next
    n_test to test, the rest to train, with at least one group each in dev
    and test. Nothing here looks at rows: a group is never divided.
    """
    out: dict[str, str] = {}
    for name in sorted(strata):
        groups = list(strata[name])
        rng.shuffle(groups)
        n = len(groups)
        n_dev = n_test = max(1, int(0.15 * n + 0.5))
        if n - n_dev - n_test < 1:
            raise ValueError(f"stratum {name!r}: {n} groups are too few to split")
        for g in groups[:n_dev]:
            out[g] = "dev"
        for g in groups[n_dev:n_dev + n_test]:
            out[g] = "test"
        for g in groups[n_dev + n_test:]:
            out[g] = "train"
    return out
