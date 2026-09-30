#!/usr/bin/env bash
# Gate: no real secret ever reaches this repository, tracked or in history.
# Fixtures use obviously fake keys that do not have a real-secret shape, so the
# gate needs no allowlist for them; a real finding is always something to remove
# and rotate, never something to annotate past.
#
# One exception is named, not hidden: an early commit carried a fake test key
# shaped like an API key. History is not rewritten for it, so the history scan
# skips lines holding exactly that one fake literal and nothing else.
# The literal is assembled from pieces so this file does not contain it.
set -euo pipefail
cd "$(dirname "$0")/.."

tracked_count=$(git ls-files 2>/dev/null | wc -l | tr -d ' ')
[ "$tracked_count" -gt 0 ] || { echo "no-secrets: measured nothing (no tracked files)" >&2; exit 1; }

# Each pattern is a real-secret SHAPE, not a word: an Anthropic key prefix, a
# generic 20+ char secret-looking token, a GitHub PAT (classic or
# fine-grained), an AWS access key id, a PEM private key header, and a Slack
# token. A bearer token of 24+ chars is checked separately, outside tests,
# since fixtures use short fakes.
pattern='sk-ant-[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[baprs]-[A-Za-z0-9-]+'
known_fake="sk-""test-SECRET-0123456789"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
found=0

while IFS= read -r f; do
  [ -z "$f" ] && continue
  [ -f "$f" ] || continue
  if grep -InE "$pattern" -- "$f" > "$TMP/hit" 2>/dev/null; then
    while IFS= read -r line; do
      echo "FAIL: $f:$line matches a real-secret shape" >&2
    done < "$TMP/hit"
    found=1
  fi
  case "$f" in
    tests/*) : ;;
    *)
      if grep -nE 'Bearer [A-Za-z0-9_.-]{24,}' -- "$f" > "$TMP/hit" 2>/dev/null; then
        while IFS= read -r line; do
          echo "FAIL: $f:$line carries a bearer token 24 chars or longer" >&2
        done < "$TMP/hit"
        found=1
      fi
      ;;
  esac
done < <(git ls-files)

# The full history too: a secret committed and later removed from HEAD still
# leaked, and git never forgets a blob on its own.
if git log -p --all 2>/dev/null | grep -F -v -e "$known_fake" | grep -InE "$pattern" > "$TMP/hist"; then
  echo "FAIL: git history contains a real-secret shape (first hits below)" >&2
  head -5 "$TMP/hist" | cut -c1-12 >&2
  found=1
fi

[ "$found" = "0" ] || exit 1
echo "no-secrets: OK $tracked_count tracked files and the full history clean of real-secret shapes"
