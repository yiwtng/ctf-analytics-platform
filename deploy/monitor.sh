#!/usr/bin/env bash
# =============================================================================
# monitor.sh — Live resource monitor during data collection rounds
# =============================================================================
# Prints every 10 seconds: container CPU/RAM, disk free, active sessions,
# and recent event count. Run in a dedicated terminal during data collection.
#
# Usage:
#   bash deploy/monitor.sh
# Press Ctrl+C to exit.
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

ENV_FILE=".env.prod"
INTERVAL=10

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [[ -f "${ENV_FILE}" ]]; then
  set -a; source "${ENV_FILE}"; set +a
fi

DB_CONTAINER="${DB_CONTAINER:-analytics_db_prod}"
DB_USER="${ANALYTICS_DB_USER:-analytics}"
DB_NAME="${ANALYTICS_DB_NAME:-analytics_prod}"

ORCH_CONTAINER="orchestrator_prod"

clear_screen() { printf '\033[H\033[2J'; }

query_db() {
  docker exec "${DB_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" \
    -t -c "$1" 2>/dev/null | tr -d ' \n' || echo "N/A"
}

trap 'echo -e "\n${YELLOW}Monitor stopped.${NC}"; exit 0' INT TERM

echo -e "${CYAN}Starting monitor (Ctrl+C to stop)...${NC}"
sleep 1

while true; do
  clear_screen

  NOW=$(date '+%Y-%m-%d %H:%M:%S')
  TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "no-tailscale")

  echo -e "${CYAN}══════════════════════════════════════════════════════════════════${NC}"
  echo -e "${CYAN}  CTF Analytics — Live Monitor   ${NOW}${NC}"
  echo -e "${CYAN}  Tailscale IP: ${TAILSCALE_IP}   (refresh: ${INTERVAL}s)${NC}"
  echo -e "${CYAN}══════════════════════════════════════════════════════════════════${NC}"
  echo ""

  # ── Container stats ────────────────────────────────────────────────────────
  echo -e "${GREEN}── Container Resources ────────────────────────────────────────────${NC}"
  docker stats --no-stream --format \
    "  {{printf \"%-25s\" .Name}}  CPU: {{printf \"%6s\" .CPUPerc}}  RAM: {{printf \"%10s\" .MemUsage}}" \
    traefik_prod ctfd_prod ctfd_db_prod ctfd_cache_prod \
    analytics_db_prod orchestrator_prod grafana_prod \
    2>/dev/null || echo "  (some containers not running)"
  echo ""

  # ── Disk space ────────────────────────────────────────────────────────────
  echo -e "${GREEN}── Disk Space ─────────────────────────────────────────────────────${NC}"
  df -h / | awk 'NR==1{printf "  %-15s %-8s %-8s %-8s %s\n",$1,$2,$3,$4,$5} NR==2{printf "  %-15s %-8s %-8s %-8s %s\n",$1,$2,$3,$4,$5}'
  echo ""

  # ── Analytics DB metrics ──────────────────────────────────────────────────
  echo -e "${GREEN}── Analytics DB ───────────────────────────────────────────────────${NC}"
  if docker ps --format '{{.Names}}' | grep -q "^${DB_CONTAINER}$"; then
    EVENT_COUNT=$(query_db "SELECT COUNT(*) FROM events;")
    ENROLL_COUNT=$(query_db "SELECT COUNT(*) FROM participant_enrollment;")
    ASSIGN_COUNT=$(query_db "SELECT COUNT(*) FROM experiment_assignment;")

    # Recent events (last 60s)
    RECENT_EVENTS=$(query_db \
      "SELECT COUNT(*) FROM events WHERE ts > NOW() - INTERVAL '60 seconds';")

    # Active sessions (events in last 5 min from distinct users)
    ACTIVE_SESSIONS=$(query_db \
      "SELECT COUNT(DISTINCT user_key) FROM events WHERE ts > NOW() - INTERVAL '5 minutes';")

    printf "  %-25s %s\n" "Total events:"      "${EVENT_COUNT}"
    printf "  %-25s %s\n" "Enrollments:"       "${ENROLL_COUNT}"
    printf "  %-25s %s\n" "Experiment assigns:" "${ASSIGN_COUNT}"
    printf "  %-25s %s\n" "Events (last 60s):" "${RECENT_EVENTS}"
    printf "  %-25s %s\n" "Active users (5m):" "${ACTIVE_SESSIONS}"
  else
    echo "  ${DB_CONTAINER} is not running"
  fi
  echo ""

  # ── Container health summary ──────────────────────────────────────────────
  echo -e "${GREEN}── Service Health ─────────────────────────────────────────────────${NC}"
  for svc in traefik_prod ctfd_prod ctfd_db_prod ctfd_cache_prod analytics_db_prod orchestrator_prod grafana_prod; do
    STATUS=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}' \
      "${svc}" 2>/dev/null || echo "stopped")
    case "${STATUS}" in
      healthy|running) INDICATOR="${GREEN}●${NC}" ;;
      starting)        INDICATOR="${YELLOW}●${NC}" ;;
      *)               INDICATOR="\033[0;31m●${NC}" ;;
    esac
    printf "  %b  %-25s %s\n" "${INDICATOR}" "${svc}" "${STATUS}"
  done
  echo ""

  echo -e "${CYAN}  Next refresh in ${INTERVAL}s — Ctrl+C to stop${NC}"

  sleep ${INTERVAL}
done
