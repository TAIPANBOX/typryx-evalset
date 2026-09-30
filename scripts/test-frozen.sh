#!/usr/bin/env bash
# Gate: data/test.jsonl is frozen. Its sha256 must equal the one recorded in
# data/MANIFEST.json. A gate that cannot find its subject says "measured
# nothing" and fails: it never reports OK on an empty measurement.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST="$ROOT/data/test.jsonl"
MANIFEST="$ROOT/data/MANIFEST.json"

for f in "$TEST" "$MANIFEST"; do
  if [ ! -s "$f" ]; then
    echo "test-frozen: measured nothing ($f is missing or empty)"
    exit 1
  fi
done

python3 - "$TEST" "$MANIFEST" <<'PY'
import hashlib, json, sys
test, manifest = sys.argv[1], sys.argv[2]
blob = open(test, "rb").read()
rec = json.load(open(manifest))["files"]["test.jsonl"]
got, rows = hashlib.sha256(blob).hexdigest(), blob.count(b"\n")
if got != rec["sha256"] or rows != rec["rows"]:
    print(f"test-frozen: FAIL data/test.jsonl changed: sha256 {got} ({rows} rows), manifest says {rec['sha256']} ({rec['rows']} rows)")
    sys.exit(1)
print(f"test-frozen: OK data/test.jsonl is the frozen file: {rows} rows, sha256 {got}")
PY
