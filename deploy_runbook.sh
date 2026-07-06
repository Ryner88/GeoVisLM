#!/usr/bin/env bash
# Minimal runbook for redeploying GeoVis LM on the VPS
# Usage: sudo ./deploy_runbook.sh [--no-cache|--cache] [--remote REMOTE] [--branch BRANCH]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

NO_CACHE="${NO_CACHE:-0}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
if [[ "$NO_CACHE" =~ ^(1|true|yes)$ ]]; then
  NO_CACHE=1
else
  NO_CACHE=0
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-cache)
      NO_CACHE=1
      shift
      ;;
    --cache)
      NO_CACHE=0
      shift
      ;;
    --remote)
      GIT_REMOTE="${2:?Missing value for --remote}"
      shift 2
      ;;
    --branch)
      GIT_BRANCH="${2:?Missing value for --branch}"
      shift 2
      ;;
    -h|--help)
      echo "Usage: sudo ./deploy_runbook.sh [--no-cache|--cache] [--remote REMOTE] [--branch BRANCH]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

echo "Pull latest code and update from ${GIT_REMOTE}/${GIT_BRANCH}"
git pull "$GIT_REMOTE" "$GIT_BRANCH"

echo "Ensure .env exists (copy example if missing)"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Copied .env.example to .env — edit as needed before continuing. Exiting."
  exit 0
fi

echo "Build and start stack"
docker-compose down
if [ "$NO_CACHE" -eq 1 ]; then
  docker-compose build --no-cache
else
  docker-compose build
fi
docker-compose up -d

echo "Run validations"
python3 scripts/validate_docker_deployment.py || true
python3 scripts/validate_docker_deployment.py --compose-config || true

echo "Run worker smoke test"
docker-compose exec -T dashboard python scripts/compose_worker_smoke.py || true

echo "Run non-interactive staging checks"
python3 scripts/verify_staging.py || true

echo "If you want automated Access login, run scripts/verify_staging_full.py with CF_USER/CF_PASS in env"
echo "Example: CF_USER=you@example.com CF_PASS=secret python3 scripts/verify_staging_full.py"

echo "Redeploy finished"
