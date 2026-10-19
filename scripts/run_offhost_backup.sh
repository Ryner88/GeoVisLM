#!/usr/bin/env bash
set -euo pipefail

DEPLOYMENT_ROOT="${DEPLOYMENT_ROOT:-/opt/geovis_lm}"
BACKUP_ROOT="${BACKUP_ROOT:-/root/geovis-backups}"
DRILL_ID="${DRILL_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
BACKUP_DIR="${BACKUP_ROOT}/production-drill-${DRILL_ID}"
LOCK_FILE="${GEOVIS_BACKUP_LOCK_FILE:-/run/geovis-offhost/backup.lock}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root so the production volumes and protected configuration are accessible." >&2
  exit 1
fi

cd "${DEPLOYMENT_ROOT}"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "Another GeoVisLM backup/replication operation is already running." >&2
  exit 1
fi

alert_failure() {
  scripts/offhost_backup.py alert-test \
    --message "scheduled production backup or off-host replication failed" >/dev/null 2>&1 || true
}
trap alert_failure ERR

VERIFY_SCRIPT="${DEPLOYMENT_ROOT}/scripts/backup_restore_verify.py" \
API_VERIFY_SCRIPT="${DEPLOYMENT_ROOT}/scripts/backup_restore_api_verify.py" \
BACKUP_ROOT="${BACKUP_ROOT}" \
DEPLOYMENT_ROOT="${DEPLOYMENT_ROOT}" \
DRILL_ID="${DRILL_ID}" \
scripts/production_backup_restore_drill.sh

scripts/offhost_backup.py replicate --backup-dir "${BACKUP_DIR}"
trap - ERR
