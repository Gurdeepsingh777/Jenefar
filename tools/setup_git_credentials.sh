#!/usr/bin/env bash
# One-time: stop git from asking username/password every push.
# Usage: bash tools/setup_git_credentials.sh
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

echo "== Git credential helper (cache 8 hours) =="
git config --global credential.helper 'cache --timeout=28800'

echo "== Prefer HTTPS with stored token =="
echo "Next push will ask ONCE for username + PAT; then cached for 8h."
echo ""
echo "Username: your GitHub username (e.g. Gurdeepsingh777)"
echo "Password: Personal Access Token with 'repo' scope (NOT account password)"
echo ""
echo "Create token: https://github.com/settings/tokens (classic, scope: repo)"
echo ""
echo "Optional permanent store (less secure on shared machines):"
echo "  git config --global credential.helper store"
echo ""
echo "Done. Try: git push origin main"
