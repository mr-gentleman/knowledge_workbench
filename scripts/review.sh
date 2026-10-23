#!/usr/bin/env bash
# Single-shot Astra review of a branch via the Cortex Code CLI.
# Each run costs Snowflake credits: Chris approves every run (AGENTS.md → Astra reviews),
# and there is no automatic re-review. Without --yes this only prints what would be sent.
#   scripts/review.sh <branch> [--yes]
set -euo pipefail
cd "$(dirname "$0")/.."

BRANCH="${1:?usage: scripts/review.sh <branch> [--yes]}"
CONN="${CONN:-activecampaign-fm00411}"
MODEL="${MODEL:-openai-gpt-6-astra}"
MAX_DIFF=2000   # lines; a bigger diff is too big for one useful review — split the branch

git fetch -q origin
BASE=$(git merge-base origin/main "$BRANCH")
DIFF=$(git diff "$BASE" "$BRANCH" -- . ':!output/')
LINES=$(echo "$DIFF" | wc -l | tr -d ' ')
[ "$LINES" -gt $MAX_DIFF ] && { echo "Diff is $LINES lines (> $MAX_DIFF). Split the branch." >&2; exit 1; }

ID=$(echo "$BRANCH" | sed -E 's#^[^/]+/##; s#^([A-Z]+-[0-9]+).*#\1#')
OUT="docs/reviews/$(date +%F)-$ID-astra.md"
PROMPT=$(mktemp)
{ cat <<'EOF'
You are the independent reviewer for the branch below of the Knowledge Workbench
(Streamlit in Snowflake app). This is a single review pass: there is no follow-up round,
so be complete now. You may read files in this repo for context; do not edit anything.

Review the diff against: (1) the intent stated in the commit messages, (2) the layer rules
and bloat check in AGENTS.md, (3) data safety: transactions, grants, owner rights, writes
outside AI_PLATFORM.WORKBENCH, concurrency.

Report only real findings, most severe first. For each: severity (high/medium/low),
file:line, a concrete failure scenario, and the smallest fix. Flag unnecessary complexity,
but do not ask for extra abstraction or scope. "No findings" is a valid answer.
End with exactly one line: "Verdict: approve" or "Verdict: changes requested".
Keep it under 400 words. Markdown.
EOF
  echo; echo "## Branch: $BRANCH"; echo; echo "## Commits"
  git log --format='- %s%n%b' "$BASE..$BRANCH" | grep -v '^Agent:' | sed '/^$/d'
  echo; echo "## Diff ($LINES lines)"; echo '```diff'; echo "$DIFF"; echo '```'
} > "$PROMPT"

if [ "${2:-}" != "--yes" ]; then
  echo "Would send $(wc -c < "$PROMPT" | tr -d ' ') chars ($LINES diff lines) to $MODEL via $CONN."
  echo "Output: $OUT. Re-run with --yes once Chris approves."
  rm -f "$PROMPT"; exit 0
fi

# Astra reads the branch from a throwaway worktree, so this checkout stays where it is.
TREE=$(mktemp -d); git worktree add -q --detach "$TREE" "$BRANCH"
trap 'git worktree remove --force "$TREE"' EXIT
mkdir -p docs/reviews
{ echo "# Astra review — $BRANCH ($(git rev-parse --short "$BRANCH"), $(date +%F))"; echo; } > "$OUT"
~/.local/bin/cortex exec -m "$MODEL" -c "$CONN" -w "$TREE" --mode code --no-mcp \
  --allowed "Read,Grep,Glob" --max-turns 15 --private -o "$OUT.tmp" < "$PROMPT" >/dev/null
cat "$OUT.tmp" >> "$OUT" && rm -f "$OUT.tmp" "$PROMPT"
echo "Saved $OUT (commit it on $BRANCH)"; tail -1 "$OUT"
