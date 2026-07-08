#!/usr/bin/env bash
# Redeploy GeoVisLM on the VPS without recreating PostGIS through legacy docker-compose.
# Usage: sudo ./deploy_runbook.sh [--no-cache|--cache] [--remote REMOTE] [--branch BRANCH] [--skip-pull]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

NO_CACHE="${NO_CACHE:-0}"
SKIP_PULL="${SKIP_PULL:-0}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(basename "$SCRIPT_DIR")}"
DB_CONTAINER="${PROJECT_NAME}_db_1"
APP_IMAGE="geovis_lm_app:latest"

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
elif docker-compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  COMPOSE_CMD=(sudo docker-compose)
fi

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

ensure_postgres() {
  local network_name="${PROJECT_NAME}_default"
  local db_volume="${PROJECT_NAME}_geovis_postgis"

  echo "Ensure Docker network ${network_name} exists"
  if ! "${DOCKER_CMD[@]}" network inspect "$network_name" >/dev/null 2>&1; then
    "${DOCKER_CMD[@]}" network create "$network_name" >/dev/null
  fi

  echo "Remove stale GeoVisLM db containers, if any"
  local db_ids
  db_ids="$("${DOCKER_CMD[@]}" ps -aq --filter "name=${PROJECT_NAME}_db" || true)"
  if [[ -n "$db_ids" ]]; then
    while IFS= read -r container_id; do
      [[ -z "$container_id" ]] && continue
      local container_name
      local running
      container_name="$("${DOCKER_CMD[@]}" inspect -f "{{.Name}}" "$container_id" 2>/dev/null || true)"
      running="$("${DOCKER_CMD[@]}" inspect -f "{{.State.Running}}" "$container_id" 2>/dev/null || true)"
      if [[ "$container_name" != "/${DB_CONTAINER}" || "$running" != "true" ]]; then
        "${DOCKER_CMD[@]}" rm -f "$container_id" >/dev/null || true
      fi
    done <<< "$db_ids"
  fi

  if ! "${DOCKER_CMD[@]}" ps --format "{{.Names}}" | grep -qx "$DB_CONTAINER"; then
    echo "Start ${DB_CONTAINER} using the persistent ${db_volume} volume"
    "${DOCKER_CMD[@]}" run -d \
      --name "$DB_CONTAINER" \
      --network "$network_name" \
      --network-alias db \
      --label "com.docker.compose.project=${PROJECT_NAME}" \
      --label "com.docker.compose.service=db" \
      -e POSTGRES_DB=geovis_lm \
      -e POSTGRES_USER=geovis \
      -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
      -v "${db_volume}:/var/lib/postgresql/data" \
      --health-cmd="pg_isready -U geovis -d geovis_lm" \
      --health-interval=10s \
      --health-timeout=5s \
      --health-retries=5 \
      postgis/postgis:16-3.4 >/dev/null
  fi

  echo "Wait for PostGIS readiness"
  for _ in $(seq 1 30); do
    if "${DOCKER_CMD[@]}" exec "$DB_CONTAINER" pg_isready -U geovis -d geovis_lm >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  "${DOCKER_CMD[@]}" exec "$DB_CONTAINER" pg_isready -U geovis -d geovis_lm >/dev/null

  echo "Sync geovis database role password from .env"
  printf "ALTER USER geovis WITH PASSWORD :\047pw\047;\n" | \
    "${DOCKER_CMD[@]}" exec -i "$DB_CONTAINER" psql -U geovis -d postgres -v ON_ERROR_STOP=1 -v "pw=$POSTGRES_PASSWORD" >/dev/null
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

ensure_postgres

echo "Build shared app image ${APP_IMAGE}"
if [[ "$NO_CACHE" -eq 1 ]]; then
  "${COMPOSE_CMD[@]}" build --no-cache dashboard
else
  "${COMPOSE_CMD[@]}" build dashboard
fi

echo "Recreate dashboard and worker without touching PostGIS"
"${COMPOSE_CMD[@]}" up -d --no-deps --no-build --force-recreate dashboard worker

echo "Current containers"
"${DOCKER_CMD[@]}" ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo "Verify public endpoints"
curl -fsS "https://geovis.nextgenbytes.me/readyz"
echo
curl -fsS "https://geovis.nextgenbytes.me/login?next=/" | grep -E "Welcome back|Access token"

echo "Redeploy finished"
