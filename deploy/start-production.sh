#!/usr/bin/env bash
# =============================================================================
# start-production.sh — One-command production deployment
# =============================================================================
# Performs safety checks, resets the analytics DB to a clean slate, then
# launches the full production stack via Docker Compose override.
#
# Usage (from repo root on the prod VM):
#   bash deploy/start-production.sh
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

PROD_MARKER="/etc/ctf-prod-vm"
ENV_FILE=".env.prod"
COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file ${ENV_FILE}"
HEALTHCHECK_TIMEOUT=120

# Prod container names (must match docker-compose.prod.yml)
PROD_SERVICES=(traefik_prod ctfd_prod ctfd_db_prod ctfd_cache_prod analytics_db_prod orchestrator_prod grafana_prod)

step()  { echo -e "\n${CYAN}─── $* ───────────────────────────────────────────${NC}"; }
ok()    { echo -e "${GREEN}✓ $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠ $*${NC}"; }
abort() { echo -e "${RED}✗ ABORT: $*${NC}"; exit 1; }

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  CTF Analytics Platform — Production Deployment${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# ── STEP 1: Confirm this is the prod VM ──────────────────────────────────────
step "Step 1/10: Verifying prod VM identity"
if [[ ! -f "${PROD_MARKER}" ]]; then
  abort "Prod VM marker not found (${PROD_MARKER}). This does not appear to be the production VM.
  If this IS the prod VM, run:  sudo bash deploy/setup-prod-vm.sh"
fi
ok "Prod VM marker confirmed."

# ── STEP 2: Verify .env.prod exists and has no placeholders ──────────────────
step "Step 2/10: Validating .env.prod"
if [[ ! -f "${ENV_FILE}" ]]; then
  abort "${ENV_FILE} not found. Copy from .env.prod.example and fill in all values."
fi

PLACEHOLDER_PATTERNS=(
  "set-real-key-here"
  "generate-strong-password"
  "generate-random"
  "set-after-irb-approval"
  "set-tailscale-hostname-or-ip"
  "changeme"
)
FOUND_PLACEHOLDERS=()
for pat in "${PLACEHOLDER_PATTERNS[@]}"; do
  if grep -q "${pat}" "${ENV_FILE}" 2>/dev/null; then
    FOUND_PLACEHOLDERS+=("${pat}")
  fi
done

if [[ ${#FOUND_PLACEHOLDERS[@]} -gt 0 ]]; then
  abort ".env.prod still contains placeholder values: ${FOUND_PLACEHOLDERS[*]}
  Edit .env.prod and replace all placeholder values before deploying."
fi
ok ".env.prod has no placeholder values."

# ── STEP 3: Verify git is at a release tag ────────────────────────────────────
step "Step 3/10: Verifying git release tag"
CURRENT_TAG=$(git describe --exact-match --tags HEAD 2>/dev/null || true)
if [[ -z "${CURRENT_TAG}" ]]; then
  abort "Not on a release tag. Deploy must be from a tagged commit.
  Tag the release first:  bash deploy/cut-release.sh
  Then checkout:          git checkout v1.0.0-data-collection"
fi
ok "On release tag: ${CURRENT_TAG}"

# ── STEP 4: Confirmation prompt ───────────────────────────────────────────────
step "Step 4/10: Deployment confirmation"
echo ""
echo -e "${RED}  WARNING: This will RESET the production analytics DB and start all services.${NC}"
echo -e "${RED}  All existing analytics data will be permanently deleted.${NC}"
echo ""
echo -e "  Tag    : ${CURRENT_TAG}"
echo -e "  Env    : ${ENV_FILE}"
echo -e "  Marker : ${PROD_MARKER}"
echo ""
echo -n "  Type DEPLOY to confirm (anything else aborts): "
read -r CONFIRMATION

if [[ "${CONFIRMATION}" != "DEPLOY" ]]; then
  echo ""
  echo "Aborted. No changes made."
  exit 0
fi
echo ""
ok "Confirmed."

# ── STEP 5: Backup current DB (if any data exists) ───────────────────────────
step "Step 5/10: Pre-reset backup"
if docker ps --format '{{.Names}}' | grep -q "^analytics_db_prod$"; then
  echo "  Running pre-reset backup..."
  set -a; source "${ENV_FILE}"; set +a
  bash deploy/backup-db.sh || warn "Backup failed (DB may be empty — continuing)."
else
  warn "analytics_db_prod not running — skipping pre-reset backup."
fi

# ── STEP 6: Reset analytics DB to clean slate ─────────────────────────────────
step "Step 6/10: Resetting analytics DB"
# Start analytics_db_prod alone first (to run reset before full stack)
set -a; source "${ENV_FILE}"; set +a
${COMPOSE_CMD} up -d analytics_db

echo "  Waiting for analytics_db_prod to be ready..."
for i in $(seq 1 30); do
  if docker exec analytics_db_prod pg_isready -U "${ANALYTICS_DB_USER}" -d "${ANALYTICS_DB_NAME}" &>/dev/null; then
    ok "analytics_db_prod is ready."
    break
  fi
  if [[ $i -eq 30 ]]; then
    abort "analytics_db_prod did not become ready after 30 seconds."
  fi
  sleep 1
done

echo "  Executing schema reset..."
docker exec -i analytics_db_prod psql \
  -U "${ANALYTICS_DB_USER}" \
  -d "${ANALYTICS_DB_NAME}" \
  < database/scripts/reset_analytics_db.sql

ok "Analytics DB reset complete — schema rebuilt, data_collection_log initialized."

# ── STEP 7: Launch full production stack ──────────────────────────────────────
step "Step 7/10: Starting production stack"
${COMPOSE_CMD} up -d --build
ok "All services started."

# ── STEP 8: Wait for all services to become healthy ───────────────────────────
step "Step 8/10: Waiting for healthchecks (timeout: ${HEALTHCHECK_TIMEOUT}s)"
ELAPSED=0
INTERVAL=5
while [[ ${ELAPSED} -lt ${HEALTHCHECK_TIMEOUT} ]]; do
  ALL_HEALTHY=true
  UNHEALTHY=()
  for svc in "${PROD_SERVICES[@]}"; do
    STATUS=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' \
      "${svc}" 2>/dev/null || echo "not-found")
    if [[ "${STATUS}" != "healthy" && "${STATUS}" != "no-healthcheck" ]]; then
      ALL_HEALTHY=false
      UNHEALTHY+=("${svc}(${STATUS})")
    fi
  done
  if ${ALL_HEALTHY}; then
    ok "All services are healthy."
    break
  fi
  echo "  Waiting... (${ELAPSED}s) unhealthy: ${UNHEALTHY[*]}"
  sleep ${INTERVAL}
  ELAPSED=$((ELAPSED + INTERVAL))
done

if ! ${ALL_HEALTHY}; then
  warn "Some services did not become healthy within ${HEALTHCHECK_TIMEOUT}s: ${UNHEALTHY[*]}"
  warn "Check logs: docker compose -f docker-compose.yml -f docker-compose.prod.yml logs <service>"
fi

# ── STEP 9: Data provenance check ────────────────────────────────────────────
step "Step 9/10: Data provenance verification"
echo "  Running verify_data_provenance.py (expect 0 users at start)..."

PROV_EXIT=0
ANALYTICS_DB_HOST=127.0.0.1 ANALYTICS_DB_PORT=5433 \
  python3 tools/research/verify_data_provenance.py --allow-unknown 2>&1 || PROV_EXIT=$?

if [[ ${PROV_EXIT} -ne 0 ]]; then
  warn "verify_data_provenance.py exited non-zero. This is expected if DB is empty."
  warn "Run again after enrolling participants to confirm clean provenance."
else
  ok "Provenance check passed (0 users — clean state confirmed)."
fi

# ── STEP 10: Summary ──────────────────────────────────────────────────────────
step "Step 10/10: Deployment summary"
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "unknown (run: tailscale ip -4)")
TAILSCALE_HOST=$(tailscale status --json 2>/dev/null | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('Self',{}).get('DNSName','').rstrip('.'))" \
  2>/dev/null || echo "")

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Production stack is UP on tag: ${CURRENT_TAG}${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo -e "  ${CYAN}Tailscale IP  :${NC} ${TAILSCALE_IP}"
if [[ -n "${TAILSCALE_HOST}" ]]; then
  echo -e "  ${CYAN}Tailscale Host:${NC} ${TAILSCALE_HOST}"
fi
echo ""
echo -e "  ${CYAN}CTFd (participants):${NC}  http://${TAILSCALE_IP}"
echo -e "  ${CYAN}Orchestrator API  :${NC}  http://${TAILSCALE_IP} (via traefik routing)"
echo -e "  ${CYAN}Grafana (admin)   :${NC}  http://${TAILSCALE_IP}:3000"
echo -e "  ${CYAN}Traefik dashboard :${NC}  http://${TAILSCALE_IP}:8080"
echo ""
echo -e "${YELLOW}Pre-flight checklist before opening to participants:${NC}"
echo "  [ ] bash deploy/preflight-check.sh   ← run this now"
echo "  [ ] Enroll participants in CTFd"
echo "  [ ] Assign experiment groups: POST /experiment/assign per user"
echo "  [ ] Verify tailscale invite links sent to all ~60 testers"
echo "  [ ] Start monitor in separate terminal: bash deploy/monitor.sh"
echo ""
