#!/usr/bin/env bash
# .claude/hooks/block-destructive.sh
#
# PreToolUse hook for Claude Code. Blocks obviously destructive shell commands
# before they run. Companion to .claude/settings.json `permissions.deny` —
# this hook adds belt-and-suspenders protection that fires even if the agent
# writes around the permission system.
#
# Reads the proposed Bash command from $CLAUDE_TOOL_INPUT (JSON) on stdin.
# Exits 0 to allow, exits 2 to block.

set -uo pipefail

INPUT="${CLAUDE_TOOL_INPUT:-}"

if [ -z "$INPUT" ]; then
    exit 0
fi

# Extract the command field if JSON, fall back to plain text.
CMD=$(printf '%s' "$INPUT" | grep -oE '"command"[[:space:]]*:[[:space:]]*"[^"]*"' 2>/dev/null | head -1 || true)
[ -z "$CMD" ] && CMD="$INPUT"

# Denylist — refuse these unconditionally.
DENY_PATTERNS=(
    "rm -rf /"
    "rm -rf ~"
    "rm -rf \${HOME}"
    "rm -rf \$HOME"
    "git reset --hard"
    "git push --force"
    "git push -f origin"
    "git clean -fdx"
    "dropdb "
    "format "
    "diskutil erase"
    "mkfs"
    "sudo rm"
    "sudo dd"
    "shutdown"
    "reboot"
    "halt "
    ":(){ :|:&};:"
)

for pat in "${DENY_PATTERNS[@]}"; do
    if printf '%s' "$CMD" | grep -qF "$pat"; then
        echo "block-destructive.sh: blocked command matching '$pat'" >&2
        echo "  full command: $CMD" >&2
        exit 2
    fi
done

# Default allow.
exit 0
