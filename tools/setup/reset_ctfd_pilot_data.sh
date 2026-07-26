#!/usr/bin/env bash
# =============================================================================
# CTFd PILOT CLEANUP — companion to reset_for_data_collection.sh
# =============================================================================
# Resetting the analytics database leaves the competition platform untouched:
# pilot accounts, their solves and submissions, and any running challenge
# containers all survive. If they are left in place the real cohort starts on a
# scoreboard that already has entries, and challenge sessions from the pilot keep
# consuming ports and memory.
#
# Removes, for the named accounts only:
#   - their submissions, solves, awards, hint unlocks and tracking rows
#   - the accounts themselves
#   - any running per-session challenge containers belonging to them
#
# Does NOT touch: challenges, flags, hints, admin accounts, or platform config.
#
# Usage:
#   bash tools/setup/reset_ctfd_pilot_data.sh                  # default prefixes
#   PILOT_PREFIXES="pilot,test" bash tools/setup/reset_ctfd_pilot_data.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
if [ ! -t 1 ]; then RED=''; YELLOW=''; GREEN=''; NC=''; fi

CTFD_DB="${CTFD_DB_CONTAINER:-ctfd_db_prod}"
CTFD_USER="${CTFD_DB_USER:-ctfd}"
CTFD_NAME="${CTFD_DB_NAME:-ctfd_prod}"
PILOT_PREFIXES="${PILOT_PREFIXES:-pilot,test}"

q() { docker exec "$CTFD_DB" psql -U "$CTFD_USER" -d "$CTFD_NAME" -t -A -c "$1"; }

# Build a SQL predicate from the prefix list. Admin accounts are protected
# regardless of name: losing the admin account would lock the platform.
PRED=""
IFS=',' read -ra PARTS <<< "$PILOT_PREFIXES"
for p in "${PARTS[@]}"; do
  p="$(echo "$p" | xargs)"
  [ -z "$p" ] && continue
  [ -n "$PRED" ] && PRED="$PRED OR "
  PRED="${PRED}name ILIKE '${p}%'"
done
[ -z "$PRED" ] && { echo "error: no prefixes given" >&2; exit 1; }
PRED="($PRED) AND type <> 'admin'"

echo ""
echo -e "${RED}============================================================${NC}"
echo -e "${RED}  CTFd PILOT CLEANUP — DESTRUCTIVE${NC}"
echo -e "${RED}============================================================${NC}"
echo ""
echo "  container : $CTFD_DB / $CTFD_NAME"
echo "  prefixes  : $PILOT_PREFIXES  (admin accounts are never removed)"
echo ""

TARGETS=$(q "SELECT id || '  ' || name FROM users WHERE $PRED ORDER BY id;")
if [ -z "$TARGETS" ]; then
  echo -e "${GREEN}No matching accounts. Nothing to do.${NC}"
  exit 0
fi

echo -e "${YELLOW}Accounts to be removed:${NC}"
echo "$TARGETS" | sed 's/^/  /'
echo ""
echo -e "${YELLOW}Their data:${NC}"
q "SELECT '  submissions=' || (SELECT count(*) FROM submissions WHERE user_id IN (SELECT id FROM users WHERE $PRED))
       || '  solves=' || (SELECT count(*) FROM solves WHERE user_id IN (SELECT id FROM users WHERE $PRED))
       || '  unlocks=' || (SELECT count(*) FROM unlocks WHERE user_id IN (SELECT id FROM users WHERE $PRED));"
echo ""

if [ "${RESET_CONFIRM:-}" = "RESET" ]; then
  echo "  RESET_CONFIRM=RESET supplied; proceeding without prompting."
else
  echo -n "  Type RESET (all caps) to proceed, or anything else to abort: "
  read -r CONFIRMATION
  [ "$CONFIRMATION" = "RESET" ] || { echo ""; echo "Aborted. Nothing changed."; exit 0; }
fi

echo ""
echo -e "${YELLOW}Removing challenge containers...${NC}"
REMOVED=0
for u in $(echo "$TARGETS" | awk '{print $1}'); do
  for c in $(docker ps -aq --filter "name=sess-${u}-" 2>/dev/null); do
    docker rm -f "$c" >/dev/null 2>&1 && REMOVED=$((REMOVED+1))
  done
done
# Sessions started with a non-numeric key (ad-hoc pilots) follow the same naming.
for p in "${PARTS[@]}"; do
  p="$(echo "$p" | xargs)"; [ -z "$p" ] && continue
  for c in $(docker ps -aq --filter "name=sess-${p}" 2>/dev/null); do
    docker rm -f "$c" >/dev/null 2>&1 && REMOVED=$((REMOVED+1))
  done
done
echo -e "${GREEN}  Removed $REMOVED container(s).${NC}"

echo ""
echo -e "${YELLOW}Deleting rows...${NC}"
# Order matters: dependants before the accounts they reference.
# -i is required: without it docker exec does not forward stdin, psql receives
# nothing, exits 0, and the script reports success having deleted nothing.
docker exec -i "$CTFD_DB" psql -U "$CTFD_USER" -d "$CTFD_NAME" -q -v ON_ERROR_STOP=1 <<SQL
BEGIN;
CREATE TEMP TABLE _pilot AS SELECT id FROM users WHERE $PRED;
DELETE FROM submissions WHERE user_id IN (SELECT id FROM _pilot);
-- CTFd stores solves in the submissions table (polymorphic type), so the
-- delete above already removed them; kept for clarity and for older schemas.
DELETE FROM solves      WHERE user_id IN (SELECT id FROM _pilot);
DELETE FROM awards      WHERE user_id IN (SELECT id FROM _pilot);
DELETE FROM unlocks     WHERE user_id IN (SELECT id FROM _pilot);
DELETE FROM tracking    WHERE user_id IN (SELECT id FROM _pilot);
DELETE FROM users       WHERE id IN (SELECT id FROM _pilot);
COMMIT;
SQL
echo -e "${GREEN}  Deleted.${NC}"

echo ""
echo -e "${YELLOW}Verifying...${NC}"
LEFT=$(q "SELECT count(*) FROM users WHERE $PRED;")
SUBS=$(q "SELECT count(*) FROM submissions;")
SOLV=$(q "SELECT count(*) FROM solves;")
echo "  matching accounts remaining : $LEFT"
echo "  submissions in platform     : $SUBS"
echo "  solves in platform          : $SOLV"

if [ "$LEFT" != "0" ]; then
  echo -e "${RED}  Some accounts were not removed. Investigate before enrolling.${NC}" >&2
  exit 1
fi

echo ""
echo -e "${GREEN}CTFd pilot cleanup complete.${NC}"
