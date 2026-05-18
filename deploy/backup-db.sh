#!/usr/bin/env bash
# =============================================================================
# backup-db.sh — Analytics DB backup for production stack
# =============================================================================
# Dumps analytics_prod DB → deploy/backups/prod-YYYYMMDD-HHMM.sql.gz
# Keeps backups from the last 72 hours; older ones are deleted.
# Exits non-zero on dump failure (safe to use in pipelines).
#
# Usage:
#   bash deploy/backup-db.sh
#   bash deploy/backup-db.sh --db-name analytics_test  # override DB name
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${REPO_ROOT}/deploy/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M)
BACKUP_FILE="${BACKUP_DIR}/prod-${TIMESTAMP}.sql.gz"

# DB config — override via env or .env.prod
DB_CONTAINER="${DB_CONTAINER:-analytics_db_prod}"
DB_USER="${ANALYTICS_DB_USER:-analytics}"
DB_NAME="${ANALYTICS_DB_NAME:-analytics_prod}"

# ---------------------------------------------------------------------------
echo "[$(date -Iseconds)] Starting backup"
echo "  Container : ${DB_CONTAINER}"
echo "  Database  : ${DB_NAME}"
echo "  Output    : ${BACKUP_FILE}"

mkdir -p "${BACKUP_DIR}"

# ── Dump ─────────────────────────────────────────────────────────────────────
# Fail loudly if the container is not running or pg_dump fails
if ! docker ps --format '{{.Names}}' | grep -q "^${DB_CONTAINER}$"; then
  echo "[ERROR] Container '${DB_CONTAINER}' is not running." >&2
  exit 1
fi

if ! docker exec "${DB_CONTAINER}" pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${BACKUP_FILE}"; then
  echo "[ERROR] pg_dump failed — removing incomplete file." >&2
  rm -f "${BACKUP_FILE}"
  exit 1
fi

# ── Verify the dump is non-empty ──────────────────────────────────────────────
BACKUP_BYTES=$(stat -c%s "${BACKUP_FILE}" 2>/dev/null || echo 0)
if [[ "${BACKUP_BYTES}" -lt 100 ]]; then
  echo "[ERROR] Backup file is suspiciously small (${BACKUP_BYTES} bytes). Aborting." >&2
  rm -f "${BACKUP_FILE}"
  exit 1
fi

BACKUP_SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
echo "[$(date -Iseconds)] Backup complete — ${BACKUP_SIZE} — ${BACKUP_FILE}"

# ── Prune backups older than 72 hours ─────────────────────────────────────────
PRUNED=$(find "${BACKUP_DIR}" -name "prod-*.sql.gz" -mmin +4320 -print -delete | wc -l)
if [[ "${PRUNED}" -gt 0 ]]; then
  echo "[$(date -Iseconds)] Pruned ${PRUNED} backup(s) older than 72 hours."
fi

echo "[$(date -Iseconds)] Backup dir: ${BACKUP_DIR}"
ls -lh "${BACKUP_DIR}"/prod-*.sql.gz 2>/dev/null | tail -5 || true
