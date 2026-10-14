#!/usr/bin/env bash
# SessionStart hook (startup, resume, clear, compact): put the hub hot cache in Claude's context,
# so every session starts from the latest cross-domain state. Plain bash, no dependencies.
root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$root" ] && [ -f "$root/wiki/hot.md" ] || exit 0
echo "Wiki — recent context from wiki/hot.md (read the root CLAUDE.md for routing):"
echo
cat "$root/wiki/hot.md"
exit 0
