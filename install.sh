#!/usr/bin/env bash
# Link this repo into ~/.claude/skills/code so Claude Code loads it as the `code` plugin
# (skills: /code:audit, /code:calibration). A symlink means `git pull` is the update.
set -euo pipefail

SKILLS_DIR="$HOME/.claude/skills"
LINK="$SKILLS_DIR/code"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
LEGACY="$SKILLS_DIR/code-audit"

mkdir -p "$SKILLS_DIR"

if [ -d "$LEGACY" ] && [ ! -L "$LEGACY" ]; then
  echo "Removing legacy copy at $LEGACY (superseded by the code plugin)."
  rm -rf "$LEGACY"
fi

if [ -L "$LINK" ]; then
  if [ "$(readlink -f "$LINK")" = "$REPO_DIR" ]; then
    echo "Already linked: $LINK -> $REPO_DIR"
    exit 0
  fi
  echo "Replacing existing link $LINK -> $(readlink "$LINK")"
  rm "$LINK"
elif [ -e "$LINK" ]; then
  echo "ERROR: $LINK exists and is not a symlink; move it aside first." >&2
  exit 1
fi

ln -s "$REPO_DIR" "$LINK"
echo "Linked $LINK -> $REPO_DIR"
echo "Restart Claude Code; the plugin loads as code@skills-dir with /code:audit and /code:calibration."
