#!/usr/bin/env bash
# Repeat the production redeploy path and verify Compose v2, service health,
# public readiness, and PostGIS cluster persistence.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

ATTEMPTS="${REDEPLOY_ATTEMPTS:-2}"
DEPLOY_COMMAND="${DEPLOY_COMMAND:-./deploy_runbook.sh --skip-pull --cache}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://geovis.nextgenbytes.me}"

if ! [[ "$ATTEMPTS" =~ ^[1-9][0-9]*$ ]]; then
  echo "REDEPLOY_ATTEMPTS must be a positive integer." >&2
  exit 2
fi

if [[ -n "${DOCKER_COMMAND:-}" ]]; then
  read -r -a DOCKER_CMD <<< "$DOCKER_COMMAND"
elif docker ps >/dev/null 2>&1; then
  DOCKER_CMD=(docker)
else
  DOCKER_CMD=(sudo docker)
fi
COMPOSE_CMD=("${DOCKER_CMD[@]}" compose)

compose_version="$("${COMPOSE_CMD[@]}" version)"
if ! grep -Eq '(^|[[:space:]])v?2([.[:space:]]|$)' <<< "$compose_version"; then
  echo "Docker Compose v2 is required; found: ${compose_version}" >&2
  exit 1
fi

cluster_id() {
  "${COMPOSE_CMD[@]}" exec -T db \
    psql -At -U geovis -d geovis_lm -c \
    "SELECT system_identifier FROM pg_control_system();"
}

verify_services() {
  local running_services
  running_services="$("${COMPOSE_CMD[@]}" ps --status running --services)"
  for service in dashboard worker db; do
    if ! grep -qx "$service" <<< "$running_services"; then
      echo "Compose service is not running: ${service}" >&2
      "${COMPOSE_CMD[@]}" ps >&2
      return 1
    fi
  done

  "${COMPOSE_CMD[@]}" exec -T db pg_isready -U geovis -d geovis_lm >/dev/null
  curl -fsS http://127.0.0.1:8000/readyz >/dev/null
  curl -fsS -A geovis-compose-redeploy-check/1.0 \
    "${PUBLIC_BASE_URL}/readyz" >/dev/null
  curl -fsS -A geovis-compose-redeploy-check/1.0 \
    "${PUBLIC_BASE_URL}/login?next=/" | grep -E "Welcome back|Access token" >/dev/null
}

initial_cluster_id="$(cluster_id)"
if [[ -z "$initial_cluster_id" ]]; then
  echo "Could not read the PostGIS cluster identifier before redeploy." >&2
  exit 1
fi

read -r -a DEPLOY_CMD <<< "$DEPLOY_COMMAND"
for attempt in $(seq 1 "$ATTEMPTS"); do
  echo "Compose v2 redeploy attempt ${attempt}/${ATTEMPTS}"
  if ! deploy_output="$("${DEPLOY_CMD[@]}" 2>&1)"; then
    printf '%s\n' "$deploy_output" >&2
    if grep -q "ContainerConfig" <<< "$deploy_output"; then
      echo "Legacy Compose ContainerConfig failure detected." >&2
    fi
    exit 1
  fi
  printf '%s\n' "$deploy_output"
  if grep -q "ContainerConfig" <<< "$deploy_output"; then
    echo "Legacy Compose ContainerConfig failure detected." >&2
    exit 1
  fi

  verify_services
  current_cluster_id="$(cluster_id)"
  if [[ "$current_cluster_id" != "$initial_cluster_id" ]]; then
    echo "PostGIS cluster changed during redeploy; persistent volume was not preserved." >&2
    exit 1
  fi
done

echo "Compose v2 repeated redeploy verification passed (${ATTEMPTS} attempts)."
