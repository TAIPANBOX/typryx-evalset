#!/usr/bin/env bash
# Gate: every gold label is recomputed from the row itself (or from the
# generator's own parameters for that row) by rules in tests/test_labels.py,
# and any mismatch fails. Families 2, 3 and 5 are recomputed fully; 1, 4 and 6
# by the construction rule the spec states for them.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -s data/all.jsonl ] || [ ! -s data/MANIFEST.json ]; then
  echo "labels-by-construction: measured nothing (data/all.jsonl or data/MANIFEST.json is missing or empty)"
  exit 1
fi
if [ ! -f tests/test_labels.py ]; then
  echo "labels-by-construction: measured nothing (tests/test_labels.py is missing)"
  exit 1
fi

out="$(python3 -m unittest tests.test_labels 2>&1)" && rc=0 || rc=$?
ran="$(printf '%s\n' "$out" | sed -n 's/^Ran \([0-9][0-9]*\) test.*/\1/p' | tail -1)"
if [ -z "$ran" ] || [ "$ran" -eq 0 ]; then
  printf '%s\n' "$out" | tail -5
  echo "labels-by-construction: measured nothing (no tests ran)"
  exit 1
fi
if [ "$rc" -ne 0 ]; then
  printf '%s\n' "$out" | tail -25
  echo "labels-by-construction: FAIL ($ran label tests, at least one gold does not match its construction)"
  exit 1
fi
echo "labels-by-construction: OK $ran label tests, all 3000 golds recomputed from their own rows or parameters"
