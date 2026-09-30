"""Shared fixtures for the tests: one in-memory build, the data on disk."""

from __future__ import annotations

import functools
import json
from pathlib import Path

from gen import build as B

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TEMPLATES = ROOT / "templates"

FAMILIES = [m.FAMILY for m in B.FAMILY_MODULES]


@functools.lru_cache(maxsize=None)
def built(seed: int = B.DEFAULT_SEED) -> dict:
    return B.build(seed)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise AssertionError(f"{path} is missing: nothing was measured")
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if not rows:
        raise AssertionError(f"{path} is empty: nothing was measured")
    return rows


def disk(name: str) -> list[dict]:
    return read_jsonl(DATA / f"{name}.jsonl")


def manifest() -> dict:
    p = DATA / "MANIFEST.json"
    if not p.exists():
        raise AssertionError(f"{p} is missing: nothing was measured")
    return json.loads(p.read_text())


def template(tid: str) -> dict:
    return json.loads((TEMPLATES / f"{tid}.json").read_text())


def by_family(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {f: [] for f in FAMILIES}
    for r in rows:
        out[r["family"]].append(r)
    return out


def disk_rows_with_params(family: str) -> list[tuple[dict, dict]]:
    """Rows as they sit in data/all.jsonl, paired with the generator's own
    parameters for the same id. The pairing is only trusted after checking
    the on-disk row equals the regenerated one byte for byte, so a row edited
    on disk cannot borrow a healthy row's parameters."""
    regen = built(manifest()["seed"])["per_family"][family]
    params_by_id = {r["id"]: c.params for r, c in zip(regen["rows"], regen["cases"])}
    regen_rows = {r["id"]: r for r in regen["rows"]}
    out = []
    for row in by_family(disk("all"))[family]:
        if regen_rows.get(row["id"]) != row:
            raise AssertionError(f"{row['id']}: the row on disk differs from the regenerated one")
        out.append((row, params_by_id[row["id"]]))
    return out
