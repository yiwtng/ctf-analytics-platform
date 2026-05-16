#!/usr/bin/env bash
# Daily backup of the analytics database.
# Usage: ./scripts/backup_db.sh
# Recommended: run via cron during data collection phase
#   0 3 * * * /home/parallels/ctf-prod/scripts/backup_db.sh >> /var/log/ctf_backup.log 2>&1

set -euo pipefail

BACKUP_DIR="$(dirname "$0")/../database/backup"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/analytics_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date -Iseconds)] Starting backup → ${BACKUP_FILE}"

docker exec analytics_db pg_dump -U analytics analytics | gzip > "$BACKUP_FILE"

SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "[$(date -Iseconds)] Backup complete — ${SIZE} — ${BACKUP_FILE}"

# Keep only last 14 daily backups
find "$BACKUP_DIR" -name "analytics_*.sql.gz" -mtime +14 -delete
echo "[$(date -Iseconds)] Old backups pruned (>14 days)"
