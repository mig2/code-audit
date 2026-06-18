#!/usr/bin/env bash
# Install the code-audit skill into ~/.claude/skills/code-audit/
set -euo pipefail

SKILL_DIR="$HOME/.claude/skills/code-audit"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing code-audit skill..."
echo "  from: $SCRIPT_DIR"
echo "  to:   $SKILL_DIR"

# Remove previous installation
if [ -d "$SKILL_DIR" ]; then
  rm -rf "$SKILL_DIR"
fi

mkdir -p "$SKILL_DIR"

# Copy skill files
cp "$SCRIPT_DIR/SKILL.md" "$SKILL_DIR/"
cp -R "$SCRIPT_DIR/scripts" "$SKILL_DIR/"
cp -R "$SCRIPT_DIR/references" "$SKILL_DIR/"
cp -R "$SCRIPT_DIR/assets" "$SKILL_DIR/"

# Stamp with git hash
GIT_HASH=$(git -C "$SCRIPT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "$GIT_HASH" > "$SKILL_DIR/.installed-from"

echo "Installed from commit $GIT_HASH. Run again after making changes to update the live skill."
