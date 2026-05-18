#!/usr/bin/env bash
# =============================================================================
# preflight-check.sh — Pre-launch gate (run before opening to participants)
# =============================================================================
# Checks 8 conditions and prints ✓/✗ for each.
# Exits 1 if ANY check fails.
#
# Usage:
#   bash deploy/preflight-check.sh
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

ENV_FILE=".env.prod"

PASS=0
FAIL=0
WARN=0

check_pass() { echo -e "  ${GREEN}✓${NC} $*"; PASS=$((PASS + 1)); }
check_fail() { echo -e "  ${RED}✗${NC} $*"; FAIL=$((FAIL + 1)); }
check_warn() { echo -e "  ${YELLOW}⚠${NC} $*"; WARN=$((WARN + 1)); }

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  CTF Analytics Platform — Pre-flight Check${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# Load env file quietly for variable access
if [[ -f "${ENV_FILE}" ]]; then
  set -a; source "${ENV_FILE}"; set +a
else
  echo -e "${RED}✗ .env.prod not found — cannot run preflight checks.${NC}"
  exit 1
fi

# ── Check 1: Git is at a release tag ─────────────────────────────────────────
echo -e "${CYAN}[1/8] Git release tag${NC}"
CURRENT_TAG=$(git describe --exact-match --tags HEAD 2>/dev/null || true)
if [[ -n "${CURRENT_TAG}" ]]; then
  check_pass "On release tag: ${CURRENT_TAG}"
else
  CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  check_fail "Not on a tag — currently on branch '${CURRENT_BRANCH}'. Tag a release first."
fi

# ── Check 2: .env.prod has no placeholders ────────────────────────────────────
echo -e "${CYAN}[2/8] .env.prod placeholder values${NC}"
PLACEHOLDER_PATTERNS=(
  "set-real-key-here"
  "generate-strong-password"
  "generate-random"
  "set-after-irb-approval"
  "set-tailscale-hostname-or-ip"
  "changeme"
)
FOUND=()
for pat in "${PLACEHOLDER_PATTERNS[@]}"; do
  if grep -q "${pat}" "${ENV_FILE}" 2>/dev/null; then
    FOUND+=("${pat}")
  fi
done
if [[ ${#FOUND[@]} -eq 0 ]]; then
  check_pass ".env.prod has no placeholder values."
else
  check_fail ".env.prod still contains placeholders: ${FOUND[*]}"
fi

# ── Check 3: All containers healthy ──────────────────────────────────────────
echo -e "${CYAN}[3/8] Container health${NC}"
PROD_SERVICES=(traefik_prod ctfd_prod ctfd_db_prod ctfd_cache_prod analytics_db_prod orchestrator_prod grafana_prod)
ALL_HEALTHY=true
for svc in "${PROD_SERVICES[@]}"; do
  STATUS=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' \
    "${svc}" 2>/dev/null || echo "not-found")
  case "${STATUS}" in
    healthy)          check_pass "${svc}: healthy" ;;
    no-healthcheck)   check_warn "${svc}: running (no healthcheck)" ;;
    not-found)        check_fail "${svc}: not running"; ALL_HEALTHY=false ;;
    *)                check_fail "${svc}: ${STATUS}"; ALL_HEALTHY=false ;;
  esac
done

# ── Check 4: Analytics DB is empty (or intentionally populated) ───────────────
echo -e "${CYAN}[4/8] Analytics DB state (should be empty before data collection)${NC}"
DB_STATUS="unknown"
if docker ps --format '{{.Names}}' | grep -q "^analytics_db_prod$"; then
  EVENT_COUNT=$(docker exec analytics_db_prod psql \
    -U "${ANALYTICS_DB_USER:-analytics}" \
    -d "${ANALYTICS_DB_NAME:-analytics_prod}" \
    -t -c "SELECT COUNT(*) FROM events;" 2>/dev/null | tr -d ' \n' || echo "error")
  ENROLL_COUNT=$(docker exec analytics_db_prod psql \
    -U "${ANALYTICS_DB_USER:-analytics}" \
    -d "${ANALYTICS_DB_NAME:-analytics_prod}" \
    -t -c "SELECT COUNT(*) FROM participant_enrollment;" 2>/dev/null | tr -d ' \n' || echo "error")

  if [[ "${EVENT_COUNT}" == "0" && "${ENROLL_COUNT}" == "0" ]]; then
    check_pass "DB is empty (${EVENT_COUNT} events, ${ENROLL_COUNT} enrollments) — clean state."
  else
    echo -e "  ${YELLOW}⚠${NC} DB has data: ${EVENT_COUNT} events, ${ENROLL_COUNT} enrollments."
    echo -n "    Is this intentional (mid-study)? [y/N]: "
    read -r ANSWER
    if [[ "${ANSWER}" =~ ^[Yy]$ ]]; then
      check_warn "DB non-empty — operator confirmed intentional."
      WARN=$((WARN + 1))
      PASS=$((PASS - 1))  # cancel the implicit pass from check_warn increment
    else
      check_fail "DB non-empty — run bash deploy/start-production.sh to reset."
    fi
  fi
else
  check_fail "analytics_db_prod is not running — cannot query DB state."
fi

# ── Check 5: Data provenance ─────────────────────────────────────────────────
echo -e "${CYAN}[5/8] Data provenance (verify_data_provenance.py)${NC}"
PROV_EXIT=0
PROV_OUT=$(ANALYTICS_DB_HOST=127.0.0.1 ANALYTICS_DB_PORT=5433 \
  python3 tools/research/verify_data_provenance.py --allow-unknown 2>&1) || PROV_EXIT=$?

if [[ ${PROV_EXIT} -eq 0 ]]; then
  check_pass "verify_data_provenance.py passed."
else
  # Exit code 1 = simulation/unknown users found; benign if DB is empty
  if echo "${PROV_OUT}" | grep -q "0 user"; then
    check_pass "verify_data_provenance.py: 0 users in DB (clean)."
  else
    check_fail "verify_data_provenance.py found simulation/unknown users."
    echo "${PROV_OUT}" | grep -E "(WARN|ERROR|simulation|unknown)" | head -5 | sed 's/^/    /'
  fi
fi

# ── Check 6: Tailscale is up and has an IP ────────────────────────────────────
echo -e "${CYAN}[6/8] Tailscale connectivity${NC}"
if command -v tailscale &>/dev/null; then
  TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || true)
  TS_STATUS=$(tailscale status 2>/dev/null | head -1 || echo "")
  if [[ -n "${TAILSCALE_IP}" ]]; then
    check_pass "Tailscale up — IP: ${TAILSCALE_IP}  (${TS_STATUS})"
  else
    check_fail "Tailscale has no IP. Run: sudo tailscale up"
  fi
else
  check_fail "Tailscale not installed. Run: sudo bash deploy/setup-prod-vm.sh"
fi

# ── Check 7: Disk space >20 GB ───────────────────────────────────────────────
echo -e "${CYAN}[7/8] Disk space (>20 GB free required)${NC}"
AVAIL_KB=$(df -k / | awk 'NR==2 {print $4}')
AVAIL_GB=$((AVAIL_KB / 1048576))
if [[ ${AVAIL_GB} -gt 20 ]]; then
  check_pass "Disk free: ${AVAIL_GB} GB  (threshold: 20 GB)"
else
  check_fail "Disk free: ${AVAIL_GB} GB — below 20 GB threshold. Free space before deploying."
fi

# ── Check 8: Smoke tests pass against live system ────────────────────────────
echo -e "${CYAN}[8/8] Smoke tests (pytest tests/smoke)${NC}"
PYTEST_EXIT=0
PYTEST_OUT=$(python3 -m pytest tests/smoke -v --tb=short -q 2>&1) || PYTEST_EXIT=$?
if [[ ${PYTEST_EXIT} -eq 0 ]]; then
  PASSED=$(echo "${PYTEST_OUT}" | grep -oE '[0-9]+ passed' | head -1 || echo "?")
  check_pass "Smoke tests passed: ${PASSED}"
else
  check_fail "Smoke tests FAILED."
  echo "${PYTEST_OUT}" | tail -20 | sed 's/^/    /'
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "  Results: ${GREEN}${PASS} passed${NC}  |  ${YELLOW}${WARN} warnings${NC}  |  ${RED}${FAIL} failed${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

if [[ ${FAIL} -gt 0 ]]; then
  echo -e "${RED}✗ Pre-flight FAILED. Fix the issues above before opening to participants.${NC}"
  echo ""
  exit 1
elif [[ ${WARN} -gt 0 ]]; then
  echo -e "${YELLOW}⚠ Pre-flight PASSED WITH WARNINGS. Review warnings before proceeding.${NC}"
  echo ""
  exit 0
else
  echo -e "${GREEN}✓ All checks passed. Platform is ready for participants.${NC}"
  echo ""
  echo "  Start monitoring: bash deploy/monitor.sh"
  echo ""
  exit 0
fi
