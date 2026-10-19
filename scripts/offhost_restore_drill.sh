#!/usr/bin/env bash
set -euo pipefail
umask 077

DEPLOYMENT_ROOT="${DEPLOYMENT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RECOVERY_ROOT="${RECOVERY_ROOT:-/var/tmp/geovis-offhost-recovery}"
OBJECT_KEY=""
IDENTITY_FILE=""

usage() {
  echo "Usage: $0 --object-key PREFIX/production-drill-TIMESTAMP.tar.age --identity-file PATH" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --object-key) OBJECT_KEY="${2:-}"; shift 2 ;;
    --identity-file) IDENTITY_FILE="${2:-}"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done

if [[ "${GEOVIS_RECOVERY_ENVIRONMENT:-}" != "independent" ]]; then
  echo "Set GEOVIS_RECOVERY_ENVIRONMENT=independent only on the separate recovery host." >&2
  exit 1
fi
if [[ -z "${OBJECT_KEY}" || -z "${IDENTITY_FILE}" ]]; then
  usage
  exit 2
fi
case "$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "${RECOVERY_ROOT}")" in
  /root/geovis-backups|/root/geovis-backups/*)
    echo "RECOVERY_ROOT must not be Prime's on-host backup directory." >&2
    exit 1
    ;;
esac

DRILL_ID="offhost-$(date -u +%Y%m%dT%H%M%SZ)-$$"
RESTORE_DB_CONTAINER="geovis-${DRILL_ID}-db"
RESTORE_APP_CONTAINER="geovis-${DRILL_ID}-app"
RESTORE_DB_VOLUME="geovis_${DRILL_ID}_postgis"
RESTORE_OUTPUT_VOLUME="geovis_${DRILL_ID}_outputs"
RESTORE_PASSWORD="restore-only-${DRILL_ID}"
WORK_DIR="${RECOVERY_ROOT}/${DRILL_ID}"
EXTRACT_ROOT="${WORK_DIR}/downloaded"
CURRENT_STAGE="initialization"
mkdir -p "${WORK_DIR}"
chmod 700 "${WORK_DIR}"

cleanup_scratch() {
  docker rm -f "${RESTORE_APP_CONTAINER}" >/dev/null 2>&1 || true
  docker rm -f "${RESTORE_DB_CONTAINER}" >/dev/null 2>&1 || true
  docker volume rm "${RESTORE_DB_VOLUME}" >/dev/null 2>&1 || true
  docker volume rm "${RESTORE_OUTPUT_VOLUME}" >/dev/null 2>&1 || true
}
on_exit() {
  local status=$?
  trap - EXIT
  if [[ "${status}" -ne 0 ]]; then
    python3 "${DEPLOYMENT_ROOT}/scripts/recovery_diagnostics.py" capture \
      "${WORK_DIR}" "${RESTORE_DB_CONTAINER}" "${RESTORE_APP_CONTAINER}" \
      "${status}" "${CURRENT_STAGE}" || true
  fi
  cleanup_scratch
  python3 "${DEPLOYMENT_ROOT}/scripts/recovery_diagnostics.py" verify-cleanup \
    "${WORK_DIR}" "${RESTORE_DB_CONTAINER}" "${RESTORE_APP_CONTAINER}" \
    "${RESTORE_DB_VOLUME}" "${RESTORE_OUTPUT_VOLUME}" || status=1
  find "${WORK_DIR}" -type d -exec chmod 700 {} +
  find "${WORK_DIR}" -type f -exec chmod 600 {} +
  exit "${status}"
}
trap on_exit EXIT

cd "${DEPLOYMENT_ROOT}"
CURRENT_STAGE="B2 fetch and decrypt"
scripts/offhost_backup.py fetch \
  --object-key "${OBJECT_KEY}" \
  --identity-file "${IDENTITY_FILE}" \
  --destination "${EXTRACT_ROOT}" > "${WORK_DIR}/fetch-result.json"
BACKUP_DIR="$(jq -er '.extracted_backup' "${WORK_DIR}/fetch-result.json")"

(
  cd "${BACKUP_DIR}"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c checksums.sha256
  else
    shasum -a 256 -c checksums.sha256
  fi
)

RECOVERY_APP_IMAGE="${RECOVERY_APP_IMAGE:-geovis_lm_app:latest}"
CURRENT_STAGE="application image verification"
python3 scripts/verify_recovery_image.py "${BACKUP_DIR}" "${RECOVERY_APP_IMAGE}" \
  > "${WORK_DIR}/image-verification.json"
APP_IMAGE_ID="$(jq -er '.image_id' "${WORK_DIR}/image-verification.json")"

CURRENT_STAGE="scratch volume creation"
docker volume create "${RESTORE_DB_VOLUME}" >/dev/null
docker volume create "${RESTORE_OUTPUT_VOLUME}" >/dev/null

output_helper() {
  docker run --rm --network none --read-only --tmpfs /tmp \
    --mount "type=volume,source=${RESTORE_OUTPUT_VOLUME},target=/restore/outputs,$1" \
    --mount "type=bind,source=${DEPLOYMENT_ROOT}/scripts/backup_restore_verify.py,target=/restore-verify.py,readonly" \
    "${APP_IMAGE_ID}" "${@:2}"
}

CURRENT_STAGE="PostgreSQL startup"
docker run -d --name "${RESTORE_DB_CONTAINER}" --network none \
  -e POSTGRES_DB=bootstrap \
  -e POSTGRES_USER=geovis \
  -e POSTGRES_PASSWORD="${RESTORE_PASSWORD}" \
  -v "${RESTORE_DB_VOLUME}:/var/lib/postgresql/data" \
  postgis/postgis:16-3.4 >/dev/null

CURRENT_STAGE="PostgreSQL final startup"
for _ in $(seq 1 120); do
  if docker logs --tail 200 "${RESTORE_DB_CONTAINER}" > "${WORK_DIR}/postgresql-startup.log" 2>&1 \
      && grep -Fq 'PostgreSQL init process complete; ready for start up.' "${WORK_DIR}/postgresql-startup.log" \
      && docker exec "${RESTORE_DB_CONTAINER}" pg_isready -U geovis -d bootstrap >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
grep -Fq 'PostgreSQL init process complete; ready for start up.' "${WORK_DIR}/postgresql-startup.log"
docker exec "${RESTORE_DB_CONTAINER}" pg_isready -U geovis -d bootstrap >/dev/null
docker exec "${RESTORE_DB_CONTAINER}" createdb -U geovis geovis_lm
CURRENT_STAGE="PostGIS restore"
docker exec -i "${RESTORE_DB_CONTAINER}" pg_restore -U geovis -d geovis_lm \
  --exit-on-error --no-owner < "${BACKUP_DIR}/postgis.dump"
docker run --rm --network none --read-only --tmpfs /tmp \
  --mount "type=volume,source=${RESTORE_OUTPUT_VOLUME},target=/restore/outputs" \
  --mount "type=bind,source=${BACKUP_DIR}/outputs.tar.gz,target=/restore/outputs.tar.gz,readonly" \
  "${APP_IMAGE_ID}" \
  tar -C /restore/outputs -xzf /restore/outputs.tar.gz

database_fingerprint() {
  local container="$1"
  local destination="$2"
  local table_list="${WORK_DIR}/fingerprint-table-list.txt"
  local query_stdout query_stderr query_status table_name
  : > "${destination}"
  CURRENT_STAGE="database fingerprint: extensions"
  query_stdout="${WORK_DIR}/fingerprint-extensions.stdout"
  query_stderr="${WORK_DIR}/fingerprint-extensions.stderr"
  printf '%s\tstart\textensions\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${WORK_DIR}/fingerprint-queries.tsv"
  if docker exec "${container}" psql -X -v ON_ERROR_STOP=1 -U geovis -d geovis_lm -Atc \
      "select extname || '|' || extversion from pg_extension order by extname" \
      > "${query_stdout}" 2> "${query_stderr}"; then
    sed 's/^/extension|/' "${query_stdout}" >> "${destination}"
    printf '%s\tpass\textensions\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${WORK_DIR}/fingerprint-queries.tsv"
    rm -f "${query_stdout}" "${query_stderr}"
  else
    query_status=$?
    printf '%s\tfail\textensions\texit=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${query_status}" >> "${WORK_DIR}/fingerprint-queries.tsv"
    return "${query_status}"
  fi
  CURRENT_STAGE="database fingerprint: table list"
  if docker exec "${container}" psql -X -v ON_ERROR_STOP=1 -U geovis -d geovis_lm -Atc \
      "select schemaname || '.' || tablename from pg_tables where schemaname not in ('pg_catalog', 'information_schema') order by 1" \
      > "${table_list}" 2> "${WORK_DIR}/fingerprint-table-list.stderr"; then
    rm -f "${WORK_DIR}/fingerprint-table-list.stderr"
  else
    query_status=$?
    printf '%s\tfail\ttable list\texit=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${query_status}" >> "${WORK_DIR}/fingerprint-queries.tsv"
    return "${query_status}"
  fi
  while IFS= read -r table_name; do
    [[ "${table_name}" =~ ^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$ ]] || exit 1
    CURRENT_STAGE="database fingerprint: ${table_name}"
    query_stdout="${WORK_DIR}/fingerprint-${table_name}.stdout"
    query_stderr="${WORK_DIR}/fingerprint-${table_name}.stderr"
    printf '%s\tstart\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${table_name}" >> "${WORK_DIR}/fingerprint-queries.tsv"
    if docker exec "${container}" psql -X -v ON_ERROR_STOP=1 -U geovis -d geovis_lm -Atc \
      "select '${table_name}|' || count(*) || '|' || coalesce(md5(string_agg(md5(row_to_json(t)::text), '' order by md5(row_to_json(t)::text))), md5('')) from ${table_name} t" \
        > "${query_stdout}" 2> "${query_stderr}"; then
      cat "${query_stdout}" >> "${destination}"
      printf '%s\tpass\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${table_name}" >> "${WORK_DIR}/fingerprint-queries.tsv"
      rm -f "${query_stdout}" "${query_stderr}"
    else
      query_status=$?
      printf '%s\tfail\t%s\texit=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${table_name}" "${query_status}" >> "${WORK_DIR}/fingerprint-queries.tsv"
      return "${query_status}"
    fi
  done < "${table_list}"
}

CURRENT_STAGE="database fingerprint"
database_fingerprint "${RESTORE_DB_CONTAINER}" "${WORK_DIR}/restored-db.tsv"
CURRENT_STAGE="output validation"
output_helper readonly python /restore-verify.py manifest /restore/outputs \
  > "${WORK_DIR}/restored-outputs.tsv"
output_helper readonly python /restore-verify.py validate /restore/outputs \
  > "${WORK_DIR}/restored-content-validation.json"
cmp "${BACKUP_DIR}/production-db-before.tsv" "${WORK_DIR}/restored-db.tsv"
cmp "${BACKUP_DIR}/production-outputs-before.tsv" "${WORK_DIR}/restored-outputs.tsv"

CURRENT_STAGE="isolated API verification"
docker run -d --name "${RESTORE_APP_CONTAINER}" --network none --read-only \
  --tmpfs /tmp \
  -e GEOVIS_OUTPUT_ROOT=/app/outputs \
  -e GEOVIS_REQUIRE_AUTH=false \
  -v "${RESTORE_OUTPUT_VOLUME}:/app/outputs:ro" \
  -v "${DEPLOYMENT_ROOT}/scripts/backup_restore_api_verify.py:/restore-api-verify.py:ro" \
  "${APP_IMAGE_ID}" \
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
  > "${WORK_DIR}/restored-api-validation.json"

CURRENT_STAGE="scratch cleanup verification"
cleanup_scratch
python3 scripts/recovery_diagnostics.py verify-cleanup \
  "${WORK_DIR}" "${RESTORE_DB_CONTAINER}" "${RESTORE_APP_CONTAINER}" \
  "${RESTORE_DB_VOLUME}" "${RESTORE_OUTPUT_VOLUME}"
trap - EXIT

cat > "${WORK_DIR}/result.txt" <<EOF
status=pass
source=b2-only
object_key=${OBJECT_KEY}
ciphertext_checksum_verified=true
age_decryption_succeeded=true
database_fingerprint_match=true
output_manifest_match=true
isolated_api_validation=true
application_image_verified=true
scratch_resources_removed=true
EOF
find "${WORK_DIR}" -type d -exec chmod 700 {} +
find "${WORK_DIR}" -type f -exec chmod 600 {} +
echo "RECOVERY_EVIDENCE=${WORK_DIR}"
cat "${WORK_DIR}/result.txt"
