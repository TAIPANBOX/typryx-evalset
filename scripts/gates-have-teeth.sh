#!/usr/bin/env bash
# Every gate in scripts/ must be able to go red. For each gate this plants the
# gate's own fault in a throwaway copy of the repo and requires a failure; it
# also requires the gate NOT to fire on a change that is not a fault, and to
# say "measured nothing" (and fail) when its subject file is gone.
#
#   gate                     fault (must fail)              non-fault (must pass)        subject gone
#   test-frozen              flip one byte of test.jsonl    flip one byte of train.jsonl  rm test.jsonl
#   no-group-leak            plant a group in two splits    repeat a row inside a split   rm dev.jsonl
#   labels-by-construction   flip one gold label            edit the manifest's commit    rm all.jsonl
#   no-jev                   plant the vendor URL           plant "type safe" (two words) rm the data
#
# The fault strings are assembled from pieces so this file does not contain
# the pattern no-jev.sh looks for.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fails=0
cases=0

fresh() {  # fresh COPY_NAME -> prints the path of a fresh copy of the repo
  local d="$TMP/$1"
  mkdir -p "$d"
  (cd "$ROOT" && tar --exclude=.git --exclude=__pycache__ -cf - .) | (cd "$d" && tar -xf -)
  echo "$d"
}

expect() {  # expect LABEL WANT(pass|fail|nothing) DIR GATE
  local label="$1" want="$2" dir="$3" gate="$4" out rc
  cases=$((cases + 1))
  out="$(cd "$dir" && "./scripts/$gate.sh" 2>&1)" && rc=0 || rc=$?
  case "$want" in
    pass)    [ "$rc" -eq 0 ] && ok=1 || ok=0 ;;
    fail)    [ "$rc" -ne 0 ] && ! grep -q "measured nothing" <<<"$out" && ok=1 || ok=0 ;;
    nothing) [ "$rc" -ne 0 ] && grep -q "measured nothing" <<<"$out" && ok=1 || ok=0 ;;
  esac
  if [ "$ok" -eq 1 ]; then
    printf 'ok    %-22s %-34s -> %s\n' "$gate" "$label" "$(tail -1 <<<"$out" | cut -c1-110)"
  else
    printf 'FAIL  %-22s %-34s wanted %s, got rc=%s\n        %s\n' "$gate" "$label" "$want" "$rc" "$(tail -2 <<<"$out" | tr '\n' ' ' | cut -c1-200)"
    fails=$((fails + 1))
  fi
}

flip_byte() {  # flip_byte FILE: change the first byte, same length
  printf 'z' | dd of="$1" bs=1 count=1 conv=notrunc 2>/dev/null
}

# ---------------------------------------------------------------- test-frozen
d="$(fresh tf-clean)";   expect "untouched repo"                 pass    "$d" test-frozen
d="$(fresh tf-fault)";   flip_byte "$d/data/test.jsonl";         expect "one byte of test.jsonl flipped" fail "$d" test-frozen
d="$(fresh tf-nonfault)"; flip_byte "$d/data/train.jsonl";       expect "one byte of train.jsonl flipped (not a fault)" pass "$d" test-frozen
d="$(fresh tf-missing)"; rm "$d/data/test.jsonl";                expect "test.jsonl missing" nothing "$d" test-frozen

# -------------------------------------------------------------- no-group-leak
d="$(fresh gl-clean)";   expect "untouched repo"                 pass    "$d" no-group-leak
d="$(fresh gl-fault)";   head -1 "$d/data/train.jsonl" >> "$d/data/dev.jsonl"
expect "a train group duplicated into dev" fail "$d" no-group-leak
d="$(fresh gl-nonfault)"; head -1 "$d/data/train.jsonl" >> "$d/data/train.jsonl"
expect "a row repeated inside train (not a fault)" pass "$d" no-group-leak
d="$(fresh gl-missing)"; rm "$d/data/dev.jsonl";                 expect "dev.jsonl missing" nothing "$d" no-group-leak

# ------------------------------------------------------ labels-by-construction
d="$(fresh lc-clean)";   expect "untouched repo"                 pass    "$d" labels-by-construction
d="$(fresh lc-fault)"
python3 - "$d/data/all.jsonl" <<'PY'
import json, sys
p = sys.argv[1]
lines = open(p).read().splitlines()
row = json.loads(lines[0])
row["gold"] = "hard" if row["gold"] != "hard" else "cheap"   # first row is request.complexity
lines[0] = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
open(p, "w").write("\n".join(lines) + "\n")
PY
expect "one gold label flipped in all.jsonl" fail "$d" labels-by-construction
d="$(fresh lc-nonfault)"
python3 - "$d/data/MANIFEST.json" <<'PY'
import json, sys
p = sys.argv[1]
m = json.load(open(p))
m["generator_commit"] = "0" * 40
open(p, "w").write(json.dumps(m, indent=2, sort_keys=True) + "\n")
PY
expect "manifest commit edited (not a fault)" pass "$d" labels-by-construction
d="$(fresh lc-missing)"; rm "$d/data/all.jsonl";                 expect "all.jsonl missing" nothing "$d" labels-by-construction

# --------------------------------------------------------------------- no-jev
d="$(fresh nj-clean)";   expect "untouched repo"                 pass    "$d" no-jev
d="$(fresh nj-fault)";   planted="https://api.type""safe.ai/v1/ask"
printf 'endpoint = "%s"\n' "$planted" > "$d/gen/planted_notes.py"
expect "the vendor URL planted in gen/" fail "$d" no-jev
d="$(fresh nj-nonfault)"; printf '# keep the answers type safe, in two words\n' > "$d/gen/notes.py"
expect "\"type safe\" in two words (not a fault)" pass "$d" no-jev
d="$(fresh nj-missing)"; rm -r "$d/data";                        expect "data/ missing" nothing "$d" no-jev

echo
if [ "$fails" -eq 0 ]; then
  echo "gates-have-teeth: OK $cases cases, every gate fails on its fault, passes on a non-fault, and says so when it measured nothing"
else
  echo "gates-have-teeth: FAIL $fails of $cases cases"
  exit 1
fi
