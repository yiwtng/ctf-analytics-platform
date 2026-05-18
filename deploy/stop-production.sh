#!/usr/bin/env bash
# =============================================================================
# stop-production.sh — Graceful production stack shutdown
# =============================================================================
# Backs up the analytics DB then stops all containers.
# Volumes are NOT removed — data is preserved.
#
# Usage:
#   bash deploy/stop-production.sh
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

ENV_FILE=".env.prod"
COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ${ENV_FILE}"

step()  { echo -e "\n${CYAN}─── $* ───────────────────────────────────────────${NC}"; }
ok()    { echo -e "${GREEN}✓ $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠ $*${NC}"; }
abort() { echo -e "${RED}✗ ABORT: $*${NC}"; exit 1; }

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  CTF Analytics Platform — Production Shutdown${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

if [[ ! -f "${ENV_FILE}" ]]; then
  abort "${ENV_FILE} not found. Cannot determine DB config for backup."
fi

# ── Confirmation ──────────────────────────────────────────────────────────────
step "Confirmation"
echo ""
echo -e "${YELLOW}  This will stop all production containers.${NC}"
echo -e "${YELLOW}  A final backup will be taken first. Volumes are preserved.${NC}"
echo ""
echo -n "  Type STOP to confirm (anything else aborts): "
read -r CONFIRMATION
if [[ "${CONFIRMATION}" != "STOP" ]]; then
  echo ""
  echo "Aborted. Stack is still running."
  exit 0
fi
ok "Confirmed."

# ── Final backup ──────────────────────────────────────────────────────────────
step "Final database backup"
set -a; source "${ENV_FILE}"; set +a

if docker ps --format '{{.Names}}' | grep -q "^analytics_db_prod$"; then
  echo "  Running final backup before shutdown..."
  if bash deploy/backup-db.sh; then
    LATEST_BACKUP=$(ls -t deploy/backups/prod-*.sql.gz 2>/dev/null | head -1 || echo "none")
    ok "Backup complete: ${LATEST_BACKUP}"
  else
    warn "Backup failed — proceeding with shutdown anyway."
    warn "Data is still in Docker volumes (not deleted by 'down')."
  fi
else
  warn "analytics_db_prod is not running — no backup taken."
fi

# ── Stop containers ───────────────────────────────────────────────────────────
step "Stopping all production containers"
${COMPOSE_CMD} down
ok "All containers stopped."

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Production stack is DOWN. Data volumes are intact.${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
LATEST_BACKUP=$(ls -t deploy/backups/prod-*.sql.gz 2>/dev/null | head -1 || echo "no backup found")
echo -e "  Latest backup : ${LATEST_BACKUP}"
echo -e "  Backup dir    : ${REPO_ROOT}/deploy/backups/"
echo ""
echo "  To restart: bash deploy/start-production.sh"
echo ""
