#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

source_branch="${1:-appAuth}"
target_branch="${2:-main}"
website_command="${GEOVIS_DEPLOY_WEBSITE_COMMAND:-}"
local_deploy_command="${GEOVIS_DEPLOY_LOCAL_COMMAND:-sudo ./deploy_runbook.sh --skip-pull --cache}"
verify_command="${GEOVIS_DEPLOY_VERIFY_COMMAND:-curl -fsS https://geovis.nextgenbytes.me/readyz}"

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
  echo
else
  echo "No website deployment command configured. Set GEOVIS_DEPLOY_WEBSITE_COMMAND to trigger an external deploy."
fi

if [[ -n "$local_deploy_command" ]]; then
  echo "Running local deployment command..."
  eval "$local_deploy_command"
else
  echo "No local deployment command configured. Set GEOVIS_DEPLOY_LOCAL_COMMAND to enable it."
fi

if [[ -n "$verify_command" ]]; then
  echo "Running website verification command..."
  eval "$verify_command"
  echo
else
  echo "No website verification command configured. Set GEOVIS_DEPLOY_VERIFY_COMMAND to enable it."
fi
