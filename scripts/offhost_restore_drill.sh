#!/usr/bin/env bash
set -euo pipefail

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

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root to create isolated Docker volumes." >&2
  exit 1
fi
if [[ "${GEOVIS_RECOVERY_ENVIRONMENT:-}" != "independent" ]]; then
  echo "Set GEOVIS_RECOVERY_ENVIRONMENT=independent only on the separate recovery host." >&2
  exit 1
fi
if [[ -z "${OBJECT_KEY}" || -z "${IDENTITY_FILE}" ]]; then
  usage
  exit 2
fi
case "$(realpath -m "${RECOVERY_ROOT}")" in
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
mkdir -p "${WORK_DIR}"
chmod 700 "${WORK_DIR}"

cleanup_scratch() {
  docker rm -f "${RESTORE_APP_CONTAINER}" >/dev/null 2>&1 || true
  docker rm -f "${RESTORE_DB_CONTAINER}" >/dev/null 2>&1 || true
  docker volume rm "${RESTORE_DB_VOLUME}" >/dev/null 2>&1 || true
  docker volume rm "${RESTORE_OUTPUT_VOLUME}" >/dev/null 2>&1 || true
}
trap cleanup_scratch EXIT

cd "${DEPLOYMENT_ROOT}"
scripts/offhost_backup.py fetch \
  --object-key "${OBJECT_KEY}" \
  --identity-file "${IDENTITY_FILE}" \
  --destination "${EXTRACT_ROOT}" > "${WORK_DIR}/fetch-result.json"
BACKUP_DIR="$(jq -er '.extracted_backup' "${WORK_DIR}/fetch-result.json")"

(
  cd "${BACKUP_DIR}"
  sha256sum -c checksums.sha256
)

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
  if docker exec "${RESTORE_DB_CONTAINER}" pg_isready -U geovis -d bootstrap >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "${RESTORE_DB_CONTAINER}" pg_isready -U geovis -d bootstrap >/dev/null
docker exec "${RESTORE_DB_CONTAINER}" createdb -U geovis geovis_lm
docker exec -i "${RESTORE_DB_CONTAINER}" pg_restore -U geovis -d geovis_lm \
  --exit-on-error --no-owner < "${BACKUP_DIR}/postgis.dump"
tar -C "${RESTORE_OUTPUT_PATH}" -xzf "${BACKUP_DIR}/outputs.tar.gz"

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

database_fingerprint "${RESTORE_DB_CONTAINER}" "${WORK_DIR}/restored-db.tsv"
python3 scripts/backup_restore_verify.py manifest "${RESTORE_OUTPUT_PATH}" \
  > "${WORK_DIR}/restored-outputs.tsv"
python3 scripts/backup_restore_verify.py validate "${RESTORE_OUTPUT_PATH}" \
  > "${WORK_DIR}/restored-content-validation.json"
cmp "${BACKUP_DIR}/production-db-before.tsv" "${WORK_DIR}/restored-db.tsv"
cmp "${BACKUP_DIR}/production-outputs-before.tsv" "${WORK_DIR}/restored-outputs.tsv"

docker run -d --name "${RESTORE_APP_CONTAINER}" --network none --read-only \
  --tmpfs /tmp \
  -e GEOVIS_OUTPUT_ROOT=/app/outputs \
  -e GEOVIS_REQUIRE_AUTH=false \
  -v "${RESTORE_OUTPUT_VOLUME}:/app/outputs:ro" \
  -v "${DEPLOYMENT_ROOT}/scripts/backup_restore_api_verify.py:/restore-api-verify.py:ro" \
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
  > "${WORK_DIR}/restored-api-validation.json"

cat > "${WORK_DIR}/result.txt" <<EOF
status=pass
source=b2-only
object_key=${OBJECT_KEY}
ciphertext_checksum_verified=true
age_decryption_succeeded=true
database_fingerprint_match=true
output_manifest_match=true
isolated_api_validation=true
scratch_resources_removed_on_exit=true
EOF
find "${WORK_DIR}" -type d -exec chmod 700 {} +
find "${WORK_DIR}" -type f -exec chmod 600 {} +
echo "RECOVERY_EVIDENCE=${WORK_DIR}"
cat "${WORK_DIR}/result.txt"
