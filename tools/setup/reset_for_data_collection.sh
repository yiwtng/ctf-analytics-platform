#!/usr/bin/env bash
# =============================================================================
# ANALYTICS DB RESET — for use BEFORE IRB-approved data collection only
# =============================================================================
# This script DESTROYS all data in the analytics database and rebuilds the
# schema from scratch. Use it once, immediately before the real cohort begins.
#
# DO NOT run this script:
#   - During or after data collection
#   - If the DB contains any real participant data
#   - Without a confirmed backup
#
# Usage:
#   ./tools/setup/reset_for_data_collection.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RESET_SQL="${REPO_ROOT}/database/scripts/reset_analytics_db.sql"
BACKUP_DIR="${REPO_ROOT}/database/backup"

echo ""
echo -e "${RED}============================================================${NC}"
echo -e "${RED}  ANALYTICS DATABASE RESET — DESTRUCTIVE OPERATION${NC}"
echo -e "${RED}============================================================${NC}"
echo ""
echo -e "${YELLOW}This will permanently DELETE all data in the analytics database:${NC}"
echo "  - All events"
echo "  - All skill score snapshots"
echo "  - All participant feedback and survey responses"
echo "  - All AI reports"
echo "  - All experiment assignments"
echo "  - All expert ratings"
echo ""
echo "Use this ONLY immediately before starting IRB-approved data collection."
echo ""

# ── Backup first ──────────────────────────────────────────────────────────────
echo -e "${YELLOW}Step 1/3: Creating backup before reset...${NC}"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="${BACKUP_DIR}/pre_reset_$(date +%Y%m%d_%H%M%S).sql.gz"
docker exec analytics_db pg_dump -U analytics analytics | gzip > "$BACKUP_FILE"
BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo -e "${GREEN}Backup written: ${BACKUP_FILE} (${BACKUP_SIZE})${NC}"
echo ""

# ── Confirmation ──────────────────────────────────────────────────────────────
echo -e "${RED}Step 2/3: Confirmation required${NC}"
echo ""
echo -n "Type RESET (all caps) to proceed, or anything else to abort: "
read -r CONFIRMATION

if [[ "$CONFIRMATION" != "RESET" ]]; then
    echo ""
    echo "Aborted. Database unchanged."
    exit 0
fi

# ── Execute reset ─────────────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}Step 3/3: Executing reset...${NC}"
docker exec -i analytics_db psql -U analytics -d analytics < "$RESET_SQL"
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Database reset complete.${NC}"
echo -e "${GREEN}  Schema rebuilt from scratch. data_collection_log initialized.${NC}"
echo -e "${GREEN}  Backup preserved at: ${BACKUP_FILE}${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Run tools/research/verify_data_provenance.py → should report 0 users"
echo "  2. Enroll real participants via CTFd"
echo "  3. Call POST /experiment/assign for each enrolled user"
echo "  4. Begin data collection (Round 1)"
