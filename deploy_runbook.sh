#!/usr/bin/env bash
# Redeploy GeoVisLM on the VPS with Docker Compose v2.
# Usage: sudo ./deploy_runbook.sh [--no-cache|--cache] [--remote REMOTE] [--branch BRANCH] [--skip-pull]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

NO_CACHE="${NO_CACHE:-0}"
SKIP_PULL="${SKIP_PULL:-0}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
APP_IMAGE="geovis_lm_app:latest"
DEPLOY_WAIT_TIMEOUT="${DEPLOY_WAIT_TIMEOUT:-120}"

if [[ "$NO_CACHE" =~ ^(1|true|yes)$ ]]; then
  NO_CACHE=1
else
  NO_CACHE=0
fi

if [[ "$SKIP_PULL" =~ ^(1|true|yes)$ ]]; then
  SKIP_PULL=1
else
  SKIP_PULL=0
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
    --skip-pull)
      SKIP_PULL=1
      shift
      ;;
    -h|--help)
      echo "Usage: sudo ./deploy_runbook.sh [--no-cache|--cache] [--remote REMOTE] [--branch BRANCH] [--skip-pull]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -n "${DOCKER_COMMAND:-}" ]]; then
  read -r -a DOCKER_CMD <<< "$DOCKER_COMMAND"
elif docker ps >/dev/null 2>&1; then
  DOCKER_CMD=(docker)
else
  DOCKER_CMD=(sudo docker)
fi

if [[ -n "${COMPOSE_COMMAND:-}" ]]; then
  read -r -a COMPOSE_CMD <<< "$COMPOSE_COMMAND"
else
  COMPOSE_CMD=("${DOCKER_CMD[@]}" compose)
fi

if ! compose_version="$("${COMPOSE_CMD[@]}" version 2>&1)"; then
  echo "Docker Compose v2 is required. Install or enable the Docker Compose plugin." >&2
  echo "$compose_version" >&2
  exit 1
fi
if ! grep -Eq '(^|[[:space:]])v?2([.[:space:]]|$)' <<< "$compose_version"; then
  echo "Docker Compose v2 is required; refusing unsupported runner: ${compose_version}" >&2
  exit 1
fi
echo "Using ${compose_version}"

ensure_secret() {
  local key="$1"
  local value="$2"

  if grep -q "^${key}=" .env; then
    if [[ -z "$(sed -n "s/^${key}=//p" .env | tail -n 1)" ]]; then
      sed -i "s/^${key}=.*/${key}=${value}/" .env
      echo "Generated ${key} in .env."
    fi
  else
    printf "\\n%s=%s\\n" "$key" "$value" >> .env
    echo "Added ${key} to .env."
  fi
}

load_env() {
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
}

sync_postgres_password() {
  echo "Sync geovis database role password from .env"
  printf "ALTER USER geovis WITH PASSWORD :\047pw\047;\n" | \
    "${COMPOSE_CMD[@]}" exec -T db psql -U geovis -d postgres -v ON_ERROR_STOP=1 -v "pw=$POSTGRES_PASSWORD" >/dev/null
}

echo "Ensure .env exists"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Copied .env.example to .env. Generated deployment secrets will be added now."
fi

ensure_secret "POSTGRES_PASSWORD" "$(openssl rand -hex 32)"
ensure_secret "GEOVIS_AUTH_TOKEN" "$(openssl rand -hex 32)"
load_env

if [[ "$SKIP_PULL" -eq 0 ]]; then
  echo "Pull latest code from ${GIT_REMOTE}/${GIT_BRANCH}"
  git pull "$GIT_REMOTE" "$GIT_BRANCH"
else
  echo "Skipping git pull"
fi

echo "Validate Compose configuration"
"${COMPOSE_CMD[@]}" config --quiet

echo "Start PostGIS with its persistent Compose volume"
"${COMPOSE_CMD[@]}" up -d --wait --wait-timeout "$DEPLOY_WAIT_TIMEOUT" db
sync_postgres_password

echo "Build shared app image ${APP_IMAGE}"
if [[ "$NO_CACHE" -eq 1 ]]; then
  "${COMPOSE_CMD[@]}" build --no-cache dashboard
else
  "${COMPOSE_CMD[@]}" build dashboard
fi

echo "Recreate dashboard and worker without touching PostGIS"
"${COMPOSE_CMD[@]}" up -d --no-deps --no-build --force-recreate --wait \
  --wait-timeout "$DEPLOY_WAIT_TIMEOUT" dashboard worker

echo "Current containers"
"${COMPOSE_CMD[@]}" ps

echo "Verify public endpoints"
curl -fsS "https://geovis.nextgenbytes.me/readyz"
echo
curl -fsS "https://geovis.nextgenbytes.me/login?next=/" | grep -E "Welcome back|Access token"

echo "Redeploy finished"
