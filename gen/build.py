"""Build the dataset: data/all.jsonl, train/dev/test.jsonl and MANIFEST.json.

    python3 -m gen.build [--seed N] [--out DIR]

Same seed, same bytes. Splits are made by GROUP, never by row (see
common.split_groups), so the test file holds phrasings the train file never
showed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from . import action, complexity, console, outcome, quality, triage
from .common import ROOT, Case, dumps, rng_for, rows_for, split_groups

DEFAULT_SEED = 20260930
FAMILY_MODULES = [complexity, triage, outcome, quality, action, console]
SPLITS = ["train", "dev", "test"]


def generator_commit() -> str:
    """The last commit that touched the generator or the templates: stable
    across commits that only touch data, so rebuilding after committing the
    data does not change the manifest."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%H", "--", "gen", "templates"],
                             capture_output=True, text=True, check=True).stdout.strip()
        return out or "unversioned"
    except (OSError, subprocess.CalledProcessError):
        return "unversioned"


def build_family(seed: int, mod) -> tuple[list[Case], list[dict], dict[str, str]]:
    cases = mod.generate(seed)
    rows = rows_for(cases, mod.CODE)
    split_of = split_groups(rng_for(seed, mod.FAMILY + "|split"), mod.strata())
    return cases, rows, split_of


def build(seed: int = DEFAULT_SEED) -> dict:
    """Everything a build produces, in memory: per-family cases (with the
    generators' own parameters), rows, the group->split map, the four file
    blobs and the manifest."""
    per_family: dict[str, dict] = {}
    lines: dict[str, list[str]] = {"all": [], "train": [], "dev": [], "test": []}
    for mod in FAMILY_MODULES:
        cases, rows, split_of = build_family(seed, mod)
        per_family[mod.FAMILY] = {"cases": cases, "rows": rows, "split_of": split_of, "module": mod}
        for r in rows:
            line = dumps(r)
            lines["all"].append(line)
            lines[split_of[r["group"]]].append(line)
    blobs = {name: ("\n".join(ls) + "\n").encode() for name, ls in lines.items()}
    return {"per_family": per_family, "blobs": blobs, "manifest": make_manifest(seed, per_family, blobs, lines)}


def label_key(gold) -> str:
    """A gold label as a manifest key: strings as they are, bool/int as JSON."""
    return gold if isinstance(gold, str) else json.dumps(gold)


def make_manifest(seed: int, per_family: dict, blobs: dict[str, bytes], lines: dict[str, list[str]]) -> dict:
    fams = {}
    for mod in FAMILY_MODULES:
        info = per_family[mod.FAMILY]
        counts: dict[str, dict[str, int]] = {sp: {} for sp in SPLITS}
        groups: dict[str, set] = {sp: set() for sp in SPLITS}
        for r in info["rows"]:
            sp = info["split_of"][r["group"]]
            k = label_key(r["gold"])
            counts[sp][k] = counts[sp].get(k, 0) + 1
            groups[sp].add(r["group"])
        fams[mod.FAMILY] = {
            "template": mod.TEMPLATE,
            "rows": len(info["rows"]),
            "counts": {sp: dict(sorted(c.items())) for sp, c in counts.items()},
            "groups": {"total": sum(len(g) for g in groups.values()), **{sp: len(groups[sp]) for sp in SPLITS}},
            "rows_by_split": {sp: sum(counts[sp].values()) for sp in SPLITS},
        }
    return {
        "seed": seed,
        "generator_commit": generator_commit(),
        "rows": len(lines["all"]),
        "families": fams,
        "files": {f"{name}.jsonl": {"rows": len(lines[name]), "sha256": hashlib.sha256(blobs[name]).hexdigest()}
                  for name in ["all", *SPLITS]},
    }


def write(out: Path, built: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, blob in built["blobs"].items():
        (out / f"{name}.jsonl").write_bytes(blob)
    (out / "MANIFEST.json").write_text(json.dumps(built["manifest"], indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", type=Path, default=ROOT / "data")
    args = ap.parse_args(argv)
    built = build(args.seed)
    write(args.out, built)
    m = built["manifest"]
    print(f"seed {m['seed']}  commit {m['generator_commit'][:12]}  rows {m['rows']}")
    for name, info in m["files"].items():
        print(f"  {name:12s} {info['rows']:5d} rows  sha256 {info['sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
