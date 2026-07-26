#!/usr/bin/env bash
# =============================================================================
# ANALYTICS DB RESET — for use BEFORE IRB-approved data collection only
# =============================================================================
# Destroys all data in the analytics database and rebuilds the schema. Use it
# once, immediately before the real cohort begins.
#
# DO NOT run this script:
#   - During or after data collection
#   - If the database contains any real participant data
#
# Two corrections over the previous version, both of which would have caused
# damage:
#
#   1. It addressed container "analytics_db" and database "analytics", neither of
#      which exists in this deployment (they are analytics_db_prod and
#      analytics_prod), so it could not run at all.
#
#   2. reset_analytics_db.sql rebuilds the ORIGINAL schema. Running it alone
#      silently reverts every migration: user_skill_reports loses overall_level
#      and summary_json, so reports stop saving; feedback_rating loses
#      feedback_source, so the RQ4 comparison becomes impossible; user_ai_reports
#      loses report_role, so shadow reports are served to learners in place of
#      the intervention; and survey_response disappears entirely. Nothing would
#      look wrong until data collection was already under way. The reset now
#      re-applies the migrations, so it produces the CURRENT schema.
#
# This script does NOT touch CTFd. Pilot accounts, their solves and any running
# challenge containers survive it -- see reset_ctfd_pilot_data.sh.
#
# Usage:
#   bash tools/setup/reset_for_data_collection.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
if [ ! -t 1 ]; then RED=''; YELLOW=''; GREEN=''; NC=''; fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESET_SQL="${REPO_ROOT}/database/scripts/reset_analytics_db.sql"
BACKUP_DIR="${REPO_ROOT}/database/backup"

DB_CONTAINER="${DB_CONTAINER:-analytics_db_prod}"
DB_USER="${DB_USER:-analytics}"
DB_NAME="${DB_NAME:-analytics_prod}"

echo ""
echo -e "${RED}============================================================${NC}"
echo -e "${RED}  ANALYTICS DATABASE RESET — DESTRUCTIVE OPERATION${NC}"
echo -e "${RED}============================================================${NC}"
echo ""
echo "  container : $DB_CONTAINER"
echo "  database  : $DB_NAME"
echo ""
echo -e "${YELLOW}This permanently deletes all data in that database:${NC}"
echo "  events · skill reports · AI reports · experiment assignments"
echo "  expert ratings · feedback ratings · survey responses · feedback"
echo ""

if ! docker inspect "$DB_CONTAINER" >/dev/null 2>&1; then
  echo -e "${RED}error: container $DB_CONTAINER not found.${NC}" >&2
  exit 1
fi

# ── Show what is about to be destroyed ────────────────────────────────────────
echo -e "${YELLOW}Current contents:${NC}"
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -F' ' -c "
  SELECT '  events=' || (SELECT count(*) FROM events)
      || '  skill_reports=' || (SELECT count(*) FROM user_skill_reports)
      || '  ai_reports=' || (SELECT count(*) FROM user_ai_reports)
      || '  assignments=' || (SELECT count(*) FROM experiment_assignment);" 2>/dev/null || true
echo ""

# ── Backup first ──────────────────────────────────────────────────────────────
echo -e "${YELLOW}Step 1/4: Creating backup...${NC}"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="${BACKUP_DIR}/pre_reset_$(date +%Y%m%d_%H%M%S).sql.gz"
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_FILE"
echo -e "${GREEN}  Backup: ${BACKUP_FILE} ($(du -h "$BACKUP_FILE" | cut -f1))${NC}"
echo ""

# ── Confirmation ──────────────────────────────────────────────────────────────
echo -e "${RED}Step 2/4: Confirmation required${NC}"
if [ "${RESET_CONFIRM:-}" = "RESET" ]; then
  echo "  RESET_CONFIRM=RESET supplied; proceeding without prompting."
else
  echo -n "  Type RESET (all caps) to proceed, or anything else to abort: "
  read -r CONFIRMATION
  if [[ "$CONFIRMATION" != "RESET" ]]; then
    echo ""
    echo "Aborted. Database unchanged."
    exit 0
  fi
fi

# ── Rebuild base schema ───────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}Step 3/4: Rebuilding base schema...${NC}"
docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
  -q -v ON_ERROR_STOP=1 < "$RESET_SQL"
echo -e "${GREEN}  Base schema rebuilt.${NC}"

# ── Re-apply migrations ───────────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}Step 4/4: Re-applying migrations...${NC}"
DB_CONTAINER="$DB_CONTAINER" DB_USER="$DB_USER" DB_NAME="$DB_NAME" \
  bash "${REPO_ROOT}/scripts/run_migrations.sh"

# ── Verify the schema is actually current ─────────────────────────────────────
echo ""
echo -e "${YELLOW}Verifying schema...${NC}"
MISSING=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -c "
  SELECT string_agg(x, ', ') FROM (
    SELECT 'user_skill_reports.overall_level' AS x WHERE NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_name='user_skill_reports' AND column_name='overall_level')
    UNION ALL SELECT 'user_skill_reports.round_no' WHERE NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_name='user_skill_reports' AND column_name='round_no')
    UNION ALL SELECT 'feedback_rating.feedback_source' WHERE NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_name='feedback_rating' AND column_name='feedback_source')
    UNION ALL SELECT 'user_ai_reports.report_role' WHERE NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_name='user_ai_reports' AND column_name='report_role')
    UNION ALL SELECT 'survey_response' WHERE NOT EXISTS (
      SELECT 1 FROM information_schema.tables WHERE table_name='survey_response')
  ) t;")

if [ -n "$MISSING" ]; then
  echo -e "${RED}  SCHEMA INCOMPLETE — missing: $MISSING${NC}" >&2
  echo -e "${RED}  Do NOT enrol participants. Investigate before proceeding.${NC}" >&2
  exit 1
fi
echo -e "${GREEN}  Schema is current (migrations 010-013 present).${NC}"

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Reset complete. Backup at: ${BACKUP_FILE}${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "Next steps:"
echo "  1. bash tools/setup/reset_ctfd_pilot_data.sh   (removes pilot accounts)"
echo "  2. python tools/research/verify_data_provenance.py  → expect 0 users"
echo "  3. bash scripts/pilot_verify.sh                → schema checks should pass"
echo "  4. Set STUDY_ROUND=1 in .env.prod and restart the orchestrator"
echo "  5. Enrol real participants"
