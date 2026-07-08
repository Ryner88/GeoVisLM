#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

source_branch="${1:-appAuth}"
target_branch="${2:-main}"
website_command="${GEOVIS_DEPLOY_WEBSITE_COMMAND:-}"

if ! git rev-parse --verify "$source_branch" >/dev/null 2>&1; then
  echo "Source branch '$source_branch' does not exist locally." >&2
  exit 1
fi

echo "Pushing '$source_branch' to 'origin/$target_branch'..."
git checkout "$source_branch"
git pull --ff-only origin "$source_branch"
git push origin "$source_branch:$target_branch"

if [[ -n "$website_command" ]]; then
  echo "Running website deployment command..."
  eval "$website_command"
else
  echo "No website deployment command configured. Set GEOVIS_DEPLOY_WEBSITE_COMMAND to enable it."
fi
