#!/usr/bin/env bash
# Gate: nothing in this repository calls, names or reads the output of the
# third-party typed-answer service whose terms forbid training another model
# on it. Truth here comes from construction only. The gate scans every file in
# the repo (git metadata excluded). Two files may mention the pattern: this
# gate, which holds the pattern list, and SPEC.md, the statement of the
# prohibition itself. The gate's own name contains the pattern, so the token
# "no-jev" is blanked before matching and mentioning the gate is not a hit.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Case-insensitive substrings: the vendor's name, its API host, the backend
# name and any key path or variable built on it all contain one of these.
PATTERNS=('typesafe' 'jev')
ALLOW=('SPEC.md' 'scripts/no-jev.sh')

if [ ! -s "$ROOT/data/all.jsonl" ]; then
  echo "no-jev: measured nothing ($ROOT/data/all.jsonl is missing or empty)"
  exit 1
fi

python3 - "$ROOT" "${#PATTERNS[@]}" "${PATTERNS[@]}" "${ALLOW[@]}" <<'PY'
import os, re, sys
root, npat = sys.argv[1], int(sys.argv[2])
patterns = [p.lower() for p in sys.argv[3:3 + npat]]
allow = set(sys.argv[3 + npat:])
scanned, hits = 0, []
for d, dirs, files in os.walk(root):
    dirs[:] = [x for x in dirs if x not in (".git", "__pycache__")]
    for f in files:
        path = os.path.join(d, f)
        rel = os.path.relpath(path, root)
        scanned += 1
        if rel in allow:
            continue
        text = open(path, "rb").read().decode("utf-8", "ignore").lower().replace("no-jev", "")
        if any(p in text for p in patterns):
            hits.append(rel)
if scanned == 0:
    print("no-jev: measured nothing (no files scanned)")
    sys.exit(1)
if hits:
    print("no-jev: FAIL these files mention the forbidden service:")
    for h in sorted(hits):
        print("  " + h)
    sys.exit(1)
print(f"no-jev: OK {scanned} files scanned, none mention the forbidden service (allowed: {', '.join(sorted(allow))})")
PY
