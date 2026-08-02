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

# Provenance stamp. A bare hash names a commit but not the repo it belongs to,
# and git hashes only resolve inside a known repo — so the source location is
# recorded too, making it possible to check whether this payload is current.
# `dirty` matters most: installing from an uncommitted tree makes the recorded
# commit describe something other than what was actually copied.
COMMIT=$(git -C "$SCRIPT_DIR" rev-parse HEAD 2>/dev/null || echo "unknown")
BRANCH=$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
REMOTE=$(git -C "$SCRIPT_DIR" remote get-url origin 2>/dev/null || echo "")
if [ -n "$(git -C "$SCRIPT_DIR" status --porcelain 2>/dev/null)" ]; then
  DIRTY=true
else
  DIRTY=false
fi

cat > "$SKILL_DIR/.installed-from" <<JSON
{
  "source_path": "$SCRIPT_DIR",
  "source_remote": "$REMOTE",
  "commit": "$COMMIT",
  "branch": "$BRANCH",
  "dirty": $DIRTY,
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON

echo "Installed from ${COMMIT:0:7} on $BRANCH. Run again after making changes to update the live skill."
if [ "$DIRTY" = true ]; then
  echo "WARNING: source tree had uncommitted changes — the recorded commit does not fully describe this payload."
fi
