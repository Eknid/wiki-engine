#!/usr/bin/env bash
# Stop hook: if wiki pages changed this session, ask Claude to refresh the matching hot.md.
# Plain bash, no jq.
input=$(cat)
root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
marker="$root/.vault-meta/.touched-wikis"
[ -n "$root" ] && [ -s "$marker" ] || exit 0

# Second stop after the reminder: let Claude finish.
if printf '%s' "$input" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then : > "$marker"; exit 0; fi

wikis=$(sort -u "$marker" | paste -sd ',' - | sed 's/,/, /g')
: > "$marker"
printf '{"decision": "block", "reason": "Wiki pages changed this session in: %s. Refresh the hot cache of each (<Domain>/wiki/hot.md; hub = wiki/hot.md) in under 500 words: Last Updated, Key Recent Facts, Recent Changes, Active Threads. Overwrite it, it is a cache, not a journal."}\n' "$wikis"
