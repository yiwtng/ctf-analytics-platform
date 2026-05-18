#!/usr/bin/env bash
# =============================================================================
# install-backup-cron.sh — Hourly backup cron job management
# =============================================================================
# Installs (or removes) a cron job that runs backup-db.sh every hour.
# Logs go to /var/log/ctf_backup.log.
#
# Usage:
#   bash deploy/install-backup-cron.sh            # install
#   bash deploy/install-backup-cron.sh --uninstall  # remove
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

CRON_MARKER="# ctf-analytics-backup"
CRON_JOB="0 * * * * bash ${REPO_ROOT}/deploy/backup-db.sh >> /var/log/ctf_backup.log 2>&1  ${CRON_MARKER}"
LOG_FILE="/var/log/ctf_backup.log"

MODE="install"
if [[ "${1:-}" == "--uninstall" ]]; then
  MODE="uninstall"
fi

if [[ "${MODE}" == "uninstall" ]]; then
  echo -e "${YELLOW}Removing CTF backup cron job...${NC}"
  CURRENT_CRONTAB=$(crontab -l 2>/dev/null || true)
  NEW_CRONTAB=$(echo "${CURRENT_CRONTAB}" | grep -v "${CRON_MARKER}" || true)
  echo "${NEW_CRONTAB}" | crontab -
  echo -e "${GREEN}✓ Cron job removed.${NC}"
  echo "  Logs remain at: ${LOG_FILE}"
  exit 0
fi

# ── Install ───────────────────────────────────────────────────────────────────
echo -e "${CYAN}Installing hourly backup cron job...${NC}"
echo ""
echo "  Script : ${REPO_ROOT}/deploy/backup-db.sh"
echo "  Schedule: every hour (0 * * * *)"
echo "  Log    : ${LOG_FILE}"
echo ""

# Create log file if missing
touch "${LOG_FILE}" 2>/dev/null || true

# Check if already installed (idempotent)
CURRENT_CRONTAB=$(crontab -l 2>/dev/null || true)
if echo "${CURRENT_CRONTAB}" | grep -q "${CRON_MARKER}"; then
  echo -e "${YELLOW}⚠ Cron job already installed (idempotent — no change).${NC}"
  echo ""
  echo "Current cron entry:"
  echo "${CURRENT_CRONTAB}" | grep "${CRON_MARKER}"
  echo ""
  echo "  To remove: bash deploy/install-backup-cron.sh --uninstall"
  exit 0
fi

# Append the new job
(echo "${CURRENT_CRONTAB}"; echo "${CRON_JOB}") | crontab -

echo -e "${GREEN}✓ Cron job installed.${NC}"
echo ""
echo "Current crontab:"
crontab -l
echo ""
echo "  To remove : bash deploy/install-backup-cron.sh --uninstall"
echo "  To monitor: tail -f ${LOG_FILE}"
