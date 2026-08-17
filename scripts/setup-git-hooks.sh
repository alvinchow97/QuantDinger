#!/bin/bash
# Activate this repository's git hooks (commit-msg, pre-push).
# Usage: ./scripts/setup-git-hooks.sh
set -e

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
    echo "Error: not inside a git repository"
    exit 1
fi

HOOKS_DIR="$REPO_ROOT/.githooks"
if [ ! -d "$HOOKS_DIR" ]; then
    echo "Error: $HOOKS_DIR not found"
    exit 1
fi

chmod +x "$HOOKS_DIR"/* 2>/dev/null || true
git -C "$REPO_ROOT" config core.hooksPath .githooks

echo "[OK] core.hooksPath set to .githooks"
echo ""
echo "Active hooks:"
for hook in "$HOOKS_DIR"/*; do
    [ -f "$hook" ] && echo "  - $(basename "$hook")"
done
echo ""
echo "These hooks enforce conventional commit messages and branch naming."
echo "See CLAUDE.md and CONTRIBUTING.md for the full workflow rules."
