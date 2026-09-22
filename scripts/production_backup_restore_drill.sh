#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/root/geovis-backups}"
DEPLOYMENT_ROOT="${DEPLOYMENT_ROOT:-/opt/geovis_lm}"
DRILL_ID="${DRILL_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
BACKUP_DIR="${BACKUP_ROOT}/production-drill-${DRILL_ID}"
RESTORE_DB_CONTAINER="geovis-restore-db-${DRILL_ID}"
RESTORE_APP_CONTAINER="geovis-restore-app-${DRILL_ID}"
RESTORE_DB_VOLUME="geovis_restore_postgis_${DRILL_ID}"
RESTORE_OUTPUT_VOLUME="geovis_restore_outputs_${DRILL_ID}"
RESTORE_PASSWORD="restore-only-${DRILL_ID}"
VERIFY_SCRIPT="${VERIFY_SCRIPT:-/tmp/backup_restore_verify.py}"
API_VERIFY_SCRIPT="${API_VERIFY_SCRIPT:-/tmp/backup_restore_api_verify.py}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root so production volumes can be read without changing them." >&2
  exit 1
fi

if [[ ! -f "${VERIFY_SCRIPT}" ]]; then
  echo "Missing verifier: ${VERIFY_SCRIPT}" >&2
  exit 1
fi
if [[ ! -f "${API_VERIFY_SCRIPT}" ]]; then
  echo "Missing API verifier: ${API_VERIFY_SCRIPT}" >&2
  exit 1
fi

cd "${DEPLOYMENT_ROOT}"
PRODUCTION_DB_CONTAINER="$(docker compose ps -q db)"
PRODUCTION_OUTPUT_VOLUME="geovis_lm_geovis_outputs"
PRODUCTION_DB_VOLUME="geovis_lm_geovis_postgis"
PRODUCTION_OUTPUT_PATH="$(docker volume inspect "${PRODUCTION_OUTPUT_VOLUME}" --format '{{.Mountpoint}}')"

if [[ -z "${PRODUCTION_DB_CONTAINER}" ]]; then
  echo "Production database container was not found." >&2
  exit 1
fi

cleanup_scratch() {
  docker rm -f "${RESTORE_APP_CONTAINER}" >/dev/null 2>&1 || true
  docker rm -f "${RESTORE_DB_CONTAINER}" >/dev/null 2>&1 || true
  docker volume rm "${RESTORE_DB_VOLUME}" >/dev/null 2>&1 || true
  docker volume rm "${RESTORE_OUTPUT_VOLUME}" >/dev/null 2>&1 || true
}
trap cleanup_scratch EXIT

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

database_fingerprint() {
  local container="$1"
  local destination="$2"
  : > "${destination}"
  docker exec "${container}" psql -U geovis -d geovis_lm -Atc \
    "select extname || '|' || extversion from pg_extension order by extname" \
    | sed 's/^/extension|/' >> "${destination}"
  while IFS= read -r table_name; do
    [[ "${table_name}" =~ ^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$ ]] || exit 1
    docker exec "${container}" psql -U geovis -d geovis_lm -Atc \
      "select '${table_name}|' || count(*) || '|' || coalesce(md5(string_agg(md5(row_to_json(t)::text), '' order by md5(row_to_json(t)::text))), md5('')) from ${table_name} t" \
      >> "${destination}"
  done < <(
    docker exec "${container}" psql -U geovis -d geovis_lm -Atc \
      "select schemaname || '.' || tablename from pg_tables where schemaname not in ('pg_catalog', 'information_schema') order by 1"
  )
}

record_production_state() {
  local destination="$1"
  {
    echo "git_commit=$(git rev-parse HEAD)"
    echo "db_cluster_id=$(docker exec "${PRODUCTION_DB_CONTAINER}" psql -U geovis -d geovis_lm -Atc 'select system_identifier from pg_control_system()')"
    echo "db_volume=${PRODUCTION_DB_VOLUME}"
    echo "output_volume=${PRODUCTION_OUTPUT_VOLUME}"
    {
      docker ps -q --filter "volume=${PRODUCTION_DB_VOLUME}"
      docker ps -q --filter "volume=${PRODUCTION_OUTPUT_VOLUME}"
    } | sort -u | while IFS= read -r container_id; do
      docker inspect "${container_id}" --format \
        'container={{.Name}}|{{.Id}}|{{.Image}}|running={{.State.Running}}|health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|mounts={{range .Mounts}}{{.Name}}:{{.Destination}};{{end}}'
    done
  } > "${destination}"
}

record_production_state "${BACKUP_DIR}/production-state-before.txt"
database_fingerprint "${PRODUCTION_DB_CONTAINER}" "${BACKUP_DIR}/production-db-before.tsv"
python3 "${VERIFY_SCRIPT}" manifest "${PRODUCTION_OUTPUT_PATH}" \
  > "${BACKUP_DIR}/production-outputs-before.tsv"

backup_started_ns="$(date +%s%N)"
database_backup_started_ns="$(date +%s%N)"
docker exec "${PRODUCTION_DB_CONTAINER}" pg_dump -U geovis -d geovis_lm -Fc \
  > "${BACKUP_DIR}/postgis.dump"
database_backup_finished_ns="$(date +%s%N)"

outputs_backup_started_ns="$(date +%s%N)"
tar -C "${PRODUCTION_OUTPUT_PATH}" -czf "${BACKUP_DIR}/outputs.tar.gz" .
outputs_backup_finished_ns="$(date +%s%N)"
backup_finished_ns="$(date +%s%N)"

database_fingerprint "${PRODUCTION_DB_CONTAINER}" "${BACKUP_DIR}/production-db-after.tsv"
python3 "${VERIFY_SCRIPT}" manifest "${PRODUCTION_OUTPUT_PATH}" \
  > "${BACKUP_DIR}/production-outputs-after.tsv"
cmp "${BACKUP_DIR}/production-db-before.tsv" "${BACKUP_DIR}/production-db-after.tsv"
cmp "${BACKUP_DIR}/production-outputs-before.tsv" "${BACKUP_DIR}/production-outputs-after.tsv"

(
  cd "${BACKUP_DIR}"
  sha256sum postgis.dump outputs.tar.gz > checksums.sha256
)

restore_started_ns="$(date +%s%N)"
docker volume create "${RESTORE_DB_VOLUME}" >/dev/null
docker volume create "${RESTORE_OUTPUT_VOLUME}" >/dev/null
RESTORE_OUTPUT_PATH="$(docker volume inspect "${RESTORE_OUTPUT_VOLUME}" --format '{{.Mountpoint}}')"

docker run -d --name "${RESTORE_DB_CONTAINER}" --network none \
  -e POSTGRES_DB=bootstrap \
  -e POSTGRES_USER=geovis \
  -e POSTGRES_PASSWORD="${RESTORE_PASSWORD}" \
  -v "${RESTORE_DB_VOLUME}:/var/lib/postgresql/data" \
  postgis/postgis:16-3.4 >/dev/null

for _ in $(seq 1 60); do
  if docker logs "${RESTORE_DB_CONTAINER}" 2>&1 \
      | grep -q 'PostgreSQL init process complete; ready for start up.' \
      && docker exec "${RESTORE_DB_CONTAINER}" pg_isready -U geovis -d bootstrap >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker logs "${RESTORE_DB_CONTAINER}" 2>&1 \
  | grep -q 'PostgreSQL init process complete; ready for start up.'
docker exec "${RESTORE_DB_CONTAINER}" pg_isready -U geovis -d bootstrap >/dev/null
docker exec "${RESTORE_DB_CONTAINER}" createdb -U geovis geovis_lm
docker exec -i "${RESTORE_DB_CONTAINER}" pg_restore -U geovis -d geovis_lm \
  --exit-on-error --no-owner < "${BACKUP_DIR}/postgis.dump"

tar -C "${RESTORE_OUTPUT_PATH}" -xzf "${BACKUP_DIR}/outputs.tar.gz"
restore_finished_ns="$(date +%s%N)"

database_fingerprint "${RESTORE_DB_CONTAINER}" "${BACKUP_DIR}/restored-db.tsv"
python3 "${VERIFY_SCRIPT}" manifest "${RESTORE_OUTPUT_PATH}" \
  > "${BACKUP_DIR}/restored-outputs.tsv"
python3 "${VERIFY_SCRIPT}" validate "${RESTORE_OUTPUT_PATH}" \
  > "${BACKUP_DIR}/restored-content-validation.json"

docker run -d --name "${RESTORE_APP_CONTAINER}" --network none --read-only \
  --tmpfs /tmp \
  -e GEOVIS_OUTPUT_ROOT=/app/outputs \
  -e GEOVIS_REQUIRE_AUTH=false \
  -v "${RESTORE_OUTPUT_VOLUME}:/app/outputs:ro" \
  -v "${API_VERIFY_SCRIPT}:/restore-api-verify.py:ro" \
  geovis_lm_app:latest \
  uvicorn geovis_lm.dashboard.app:app --host 127.0.0.1 --port 8000 >/dev/null
for _ in $(seq 1 30); do
  if docker exec "${RESTORE_APP_CONTAINER}" python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)" \
      >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "${RESTORE_APP_CONTAINER}" python /restore-api-verify.py \
  > "${BACKUP_DIR}/restored-api-validation.json"

cmp "${BACKUP_DIR}/production-db-before.tsv" "${BACKUP_DIR}/restored-db.tsv"
cmp "${BACKUP_DIR}/production-outputs-before.tsv" "${BACKUP_DIR}/restored-outputs.tsv"
(
  cd "${BACKUP_DIR}"
  sha256sum -c checksums.sha256
)

record_production_state "${BACKUP_DIR}/production-state-after.txt"
cmp "${BACKUP_DIR}/production-state-before.txt" "${BACKUP_DIR}/production-state-after.txt"

duration_seconds() {
  local start_ns="$1"
  local finish_ns="$2"
  awk -v start="${start_ns}" -v finish="${finish_ns}" \
    'BEGIN { printf "%.3f", (finish - start) / 1000000000 }'
}

cat > "${BACKUP_DIR}/timings.env" <<EOF
backup_total_seconds=$(duration_seconds "${backup_started_ns}" "${backup_finished_ns}")
database_backup_seconds=$(duration_seconds "${database_backup_started_ns}" "${database_backup_finished_ns}")
outputs_backup_seconds=$(duration_seconds "${outputs_backup_started_ns}" "${outputs_backup_finished_ns}")
restore_total_seconds=$(duration_seconds "${restore_started_ns}" "${restore_finished_ns}")
EOF

cat > "${BACKUP_DIR}/result.txt" <<EOF
status=pass
drill_id=${DRILL_ID}
backup_dir=${BACKUP_DIR}
production_database_volume=${PRODUCTION_DB_VOLUME}
production_output_volume=${PRODUCTION_OUTPUT_VOLUME}
scratch_database_volume=${RESTORE_DB_VOLUME}
scratch_output_volume=${RESTORE_OUTPUT_VOLUME}
scratch_resources_removed_on_exit=true
production_state_unchanged=true
database_fingerprint_match=true
output_manifest_match=true
isolated_api_validation=true
backup_checksums_pass=true
EOF

chmod 600 "${BACKUP_DIR}"/*
echo "BACKUP_DIR=${BACKUP_DIR}"
cat "${BACKUP_DIR}/timings.env"
cat "${BACKUP_DIR}/restored-content-validation.json"
cat "${BACKUP_DIR}/result.txt"
