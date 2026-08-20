#!/usr/bin/env bash
# .claude/hooks/format-on-write.sh
#
# PostToolUse hook for Claude Code. After a Write/Edit to a code file, run the
# matching formatter. Best-effort: never fails the agent run, just runs the
# formatter if available.

set -uo pipefail

INPUT="${CLAUDE_TOOL_INPUT:-}"
[ -z "$INPUT" ] && exit 0

FILE=$(printf '%s' "$INPUT" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' 2>/dev/null | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' | head -1)
[ -z "$FILE" ] && exit 0
[ ! -f "$FILE" ] && exit 0

case "$FILE" in
    *.py)
        command -v ruff >/dev/null && ruff format "$FILE" 2>/dev/null && ruff check --fix "$FILE" 2>/dev/null
        ;;
    *.rs)
        command -v rustfmt >/dev/null && rustfmt "$FILE" 2>/dev/null
        ;;
    *.ts|*.tsx|*.js|*.jsx)
        command -v prettier >/dev/null && prettier --write "$FILE" 2>/dev/null
        ;;
esac

exit 0
