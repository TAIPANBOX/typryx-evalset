#!/usr/bin/env bash
# Gate: no `group` appears in more than one of train/dev/test. The test set
# measures generalisation to phrasings the model never saw, which only holds
# if a phrasing template is wholly on one side of the split.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for n in train dev test; do
  if [ ! -s "$ROOT/data/$n.jsonl" ]; then
    echo "no-group-leak: measured nothing ($ROOT/data/$n.jsonl is missing or empty)"
    exit 1
  fi
done

python3 - "$ROOT/data" <<'PY'
import json, sys
d = sys.argv[1]
owner, leaks, groups = {}, [], set()
for split in ("train", "dev", "test"):
    for line in open(f"{d}/{split}.jsonl"):
        g = json.loads(line)["group"]
        groups.add(g)
        if owner.setdefault(g, split) != split:
            leaks.append((g, owner[g], split))
if not groups:
    print("no-group-leak: measured nothing (no groups found)")
    sys.exit(1)
if leaks:
    for g, a, b in sorted(set(leaks))[:10]:
        print(f"no-group-leak: FAIL group {g} is in both {a} and {b}")
    sys.exit(1)
print(f"no-group-leak: OK {len(groups)} groups, none in more than one split")
PY
