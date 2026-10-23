#!/usr/bin/env bash
# One-screen health readout: size, complexity, lint, tests, docs ratio, feature
# maturity, and the change since the last run. Read-only except output/health-last.txt.
# Needs .venv (README.md → Local dev) and uv; ruff/radon run via uvx at pinned versions, so
# nothing is added to pyproject.toml, which ships with the app.
set -uo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
# Limits flag hotspots to look at; they are smoke alarms, not gates.
MAX_FILE=300   # lines per file
MAX_FUNC=50    # lines per function
MAX_CC=10      # cyclomatic complexity per function
LAST=output/health-last.txt
RUFF="uvx -q ruff@0.17.0"
RADON="uvx -q radon@6.0.1"
[ -x "$PY" ] || { echo "No .venv — see README.md → Local dev." >&2; exit 1; }
NOW=$(mktemp)
metric() { echo "$1 $2" >> "$NOW"; printf '  %-22s %s\n' "$1" "$2"; }
fail() { echo "$1" >> "$NOW.fail"; echo "  ! FAILED: $1"; }
lines() { [ $# -gt 0 ] && cat "$@" | wc -l | tr -d ' ' || echo 0; }

CODE=$(git ls-files '*.py' '*.sql' ':!tests/')
TESTS=$(git ls-files 'tests/*.py')
DOCS=$(git ls-files '*.md')

echo "== Size"
metric code_lines "$(lines $CODE)"
metric test_lines "$(lines $TESTS)"
metric doc_lines "$(lines $DOCS)"
metric files "$(echo "$CODE" | wc -l | tr -d ' ')"
for f in $CODE; do
  n=$(lines "$f"); [ "$n" -gt $MAX_FILE ] && echo "  ! $f: $n lines (> $MAX_FILE)"
done

echo "== Functions (radon)"
if command -v uvx >/dev/null; then
  $RADON cc -j $(echo "$CODE" | grep '\.py$') | $PY -c "
import json, sys
fns = [b for blocks in json.load(sys.stdin).values() if isinstance(blocks, list)
       for b in blocks if b['type'] in ('function', 'method')]
for b in fns:
    n = b['endline'] - b['lineno'] + 1
    if b['complexity'] > $MAX_CC or n > $MAX_FUNC:
        print(f\"  ! {b['name']} (line {b['lineno']}): complexity {b['complexity']}, {n} lines\")
cc = sorted(b['complexity'] for b in fns) or [0]
print(f'functions {len(fns)}'); print(f'max_complexity {cc[-1]}')
print(f\"over_limits {sum(b['complexity'] > $MAX_CC or b['endline'] - b['lineno'] >= $MAX_FUNC for b in fns)}\")
" | while read -r k v; do [ "$k" = "!" ] && echo "  ! $v" || metric "$k" "$v"; done
  grep -q '^functions ' "$NOW" || fail "radon produced no result"
else echo "  (skipped: uv not installed)"; fi

echo "== Lint (ruff)"
if command -v uvx >/dev/null; then
  lint=$($RUFF check --quiet --output-format concise $(git ls-files '*.py') 2>&1); rc=$?
  n=$(echo "$lint" | grep -cE ':[0-9]+:[0-9]+: ')
  # 0 = clean; 1 with findings listed = problems found; anything else = ruff/uvx did not run.
  { [ $rc -eq 0 ] || { [ $rc -eq 1 ] && [ "$n" -gt 0 ]; }; } && metric lint_findings "$n" \
    || fail "ruff did not run (exit $rc): $(echo "$lint" | head -1)"
else echo "  (skipped: uv not installed)"; fi

echo "== Tests"
out=$($PY -m unittest discover -s tests 2>&1 | tail -3)
run=$(echo "$out" | sed -n 's/^Ran \([0-9]*\).*/\1/p')
[ -n "$run" ] && metric tests_run "$run" || fail "tests did not run: $(echo "$out" | tail -1)"
metric tests_passing "$(echo "$out" | grep -q '^OK' && echo yes || echo NO)"

echo "== Ratios (per 100 code lines)"
code=$(awk '$1=="code_lines"{print $2}' "$NOW")
metric tests_per_100 $(( $(awk '$1=="test_lines"{print $2}' "$NOW") * 100 / code ))
metric docs_per_100 $(( $(awk '$1=="doc_lines"{print $2}' "$NOW") * 100 / code ))

echo "== Features (docs/features.md)"
for s in TODO DOING VERIFY BLOCKED DONE; do
  metric "features_$s" "$(grep -cE "^\| [A-Z]+-[0-9]+ \| $s \|" docs/features.md)"
done

if [ -f "$LAST" ]; then
  echo "== Change since $(head -1 "$LAST")"
  tail -n +2 "$LAST" | while read -r k old; do
    new=$(awk -v k="$k" '$1==k{print $2}' "$NOW")
    [ -n "$new" ] && [ "$new" != "$old" ] && printf '  %-22s %s -> %s\n' "$k" "$old" "$new"
  done
fi
if [ -f "$NOW.fail" ]; then
  echo "Some measurements failed; snapshot not saved, so the next diff stays honest."
  rm -f "$NOW" "$NOW.fail"; exit 1
fi
mkdir -p output && { date '+%Y-%m-%d %H:%M'; cat "$NOW"; } > "$LAST" && rm -f "$NOW"
