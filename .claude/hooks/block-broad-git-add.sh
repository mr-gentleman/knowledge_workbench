#!/bin/sh
# PreToolUse(Bash): refuse catch-all staging; agents stage explicit paths (AGENTS.md → Collaboration).
cmd=$(jq -r '.tool_input.command // ""')
if printf '%s' "$cmd" | grep -qE 'git( -C [^ ]+)? (add( [^;&|]*)? (-A|--all|-u|\.|:/)( |$|[;&|])|commit( [^;&|]*)? -[a-zA-Z]*a)'; then
  echo "Blocked: stage explicit paths (git add <file>...), not -A/./-u or commit -a. Run git status first." >&2
  exit 2
fi
exit 0
