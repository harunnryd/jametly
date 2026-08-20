#!/usr/bin/env bash
# .claude/hooks/strip-restate-comments.sh
#
# PreToolUse hook for Write|Edit|MultiEdit. Strips LLM-flavored "restate the code"
# comments from Python and Rust files just before they're committed.
# Best-effort, idempotent. Runs only when the diff actually has noise to strip.
#
# Strategy (deliberately simple):
# - Read the file
# - Use ast-grep if available, else fall back to grep flagging
# - If 0 flags → exit 0 (no-op)
# - If flags > 0 → print the locations, exit 0 (advisory, never blocks)
#
# We do NOT modify the file in this hook — that's the reviewer's job via
# `just verify` (the comment-density-guard pre-commit hook enforces the gate).

set -uo pipefail

INPUT="${CLAUDE_TOOL_INPUT:-}"
[ -z "$INPUT" ] && exit 0

FILE=$(printf '%s' "$INPUT" | grep -oE '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' 2>/dev/null | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' | head -1)
[ -z "$FILE" ] || [ ! -f "$FILE" ] && exit 0

case "$FILE" in
    *.py)
        # LLM-flavored patterns: "# First, we...", "# Now we...", "# This function..."
        FLAGS=$(grep -nE '^\s*#\s*(First,|Now,|This\s+(function|method|class|module)|Here\s+we|The\s+following|Let's|We\s+now)' "$FILE" 2>/dev/null || true)
        ;;
    *.rs)
        # Rust equivalent
        FLAGS=$(grep -nE '^\s*//\s*(First,|Now,|This\s+(function|method|struct|module)|Here\s+we|The\s+following|Let'\''s|We\s+now)' "$FILE" 2>/dev/null || true)
        ;;
    *)
        exit 0
        ;;
esac

if [ -n "$FLAGS" ]; then
    echo "strip-restate-comments.sh: $FILE has possible LLM-flavored restate-comments:" >&2
    printf '%s\n' "$FLAGS" >&2
    echo "Review the diff and delete comments that paraphrase the next line. See STYLE.md 'AI-authored comments'." >&2
fi

exit 0
