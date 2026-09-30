#!/usr/bin/env bash
# Everything in one go: unit tests, the five gates, the gates' teeth, and (if
# TYPRYX_DIR points at a typryx checkout) the real typryx template checker.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m unittest discover -s tests -t . 2>&1 | tail -4
for g in test-frozen no-group-leak labels-by-construction no-jev no-secrets; do "./scripts/$g.sh"; done
./scripts/gates-have-teeth.sh | tail -1
if [ -n "${TYPRYX_DIR:-}" ]; then
  (cd "$TYPRYX_DIR" && go run ./cmd/typryx templates check "$ROOT/templates")
fi
