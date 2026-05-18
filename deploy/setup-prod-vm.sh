#!/usr/bin/env bash
# =============================================================================
# setup-prod-vm.sh — One-time VM provisioning for CTF Analytics Platform
# =============================================================================
# Run ONCE on a fresh Parallels Ubuntu VM before any deployment.
# Safe to re-run (idempotent).
#
# Usage:
#   sudo bash deploy/setup-prod-vm.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

DEPLOY_USER="${DEPLOY_USER:-ctfadmin}"
MARKER_FILE="/etc/ctf-prod-vm"

step() { echo -e "\n${CYAN}>>> $*${NC}"; }
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
fail() { echo -e "${RED}✗ $*${NC}"; exit 1; }

# ── Must run as root ──────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  fail "Run as root: sudo bash deploy/setup-prod-vm.sh"
fi

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  CTF Analytics Platform — Production VM Setup${NC}"
echo -e "${CYAN}============================================================${NC}"

# ── Check Ubuntu version ──────────────────────────────────────────────────────
step "Checking Ubuntu version..."
if ! command -v lsb_release &>/dev/null; then
  fail "lsb_release not found — this script requires Ubuntu."
fi
UBUNTU_VER=$(lsb_release -rs)
UBUNTU_CODENAME=$(lsb_release -cs)
echo "  Detected: Ubuntu ${UBUNTU_VER} (${UBUNTU_CODENAME})"
# Require Ubuntu 22.04 or 24.04
case "$UBUNTU_VER" in
  22.04|24.04) ok "Ubuntu ${UBUNTU_VER} supported." ;;
  *) warn "Untested Ubuntu version ${UBUNTU_VER}. Proceeding anyway." ;;
esac

# ── Update apt ────────────────────────────────────────────────────────────────
step "Updating apt package index..."
apt-get update -qq
ok "apt updated."

# ── Install prerequisites ─────────────────────────────────────────────────────
step "Installing prerequisites (ca-certificates, curl, gnupg)..."
apt-get install -y -q ca-certificates curl gnupg lsb-release jq python3 python3-pip
ok "Prerequisites installed."

# ── Install Docker (official script, idempotent) ─────────────────────────────
step "Installing Docker Engine + Compose plugin..."
if command -v docker &>/dev/null && docker compose version &>/dev/null; then
  DOCKER_VER=$(docker --version)
  COMPOSE_VER=$(docker compose version)
  ok "Docker already installed: ${DOCKER_VER}"
  ok "Docker Compose: ${COMPOSE_VER}"
else
  echo "  Downloading Docker install script..."
  curl -fsSL https://get.docker.com | sh
  ok "Docker installed: $(docker --version)"
  ok "Compose: $(docker compose version)"
fi

# ── Enable Docker service ─────────────────────────────────────────────────────
step "Enabling Docker daemon..."
systemctl enable docker --quiet
systemctl start docker
ok "Docker daemon running."

# ── Create deploy user ────────────────────────────────────────────────────────
step "Setting up deploy user '${DEPLOY_USER}'..."
if id "${DEPLOY_USER}" &>/dev/null; then
  ok "User '${DEPLOY_USER}' already exists."
else
  useradd -m -s /bin/bash "${DEPLOY_USER}"
  ok "User '${DEPLOY_USER}' created."
fi

# Add to docker group (idempotent)
if groups "${DEPLOY_USER}" | grep -q '\bdocker\b'; then
  ok "User '${DEPLOY_USER}' already in docker group."
else
  usermod -aG docker "${DEPLOY_USER}"
  ok "User '${DEPLOY_USER}' added to docker group."
fi

# ── Install Tailscale ─────────────────────────────────────────────────────────
step "Installing Tailscale..."
if command -v tailscale &>/dev/null; then
  ok "Tailscale already installed: $(tailscale version | head -1)"
else
  curl -fsSL https://tailscale.com/install.sh | sh
  ok "Tailscale installed: $(tailscale version | head -1)"
fi

# Enable Tailscale service
systemctl enable tailscaled --quiet 2>/dev/null || true
systemctl start tailscaled 2>/dev/null || true
ok "Tailscale daemon running."

# ── Write prod VM marker ──────────────────────────────────────────────────────
step "Writing prod VM marker (${MARKER_FILE})..."
if [[ -f "${MARKER_FILE}" ]]; then
  ok "Marker already present."
else
  echo "CTF_ANALYTICS_PROD_VM=1" > "${MARKER_FILE}"
  echo "SETUP_DATE=$(date -Iseconds)" >> "${MARKER_FILE}"
  chmod 644 "${MARKER_FILE}"
  ok "Marker written."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  VM setup complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo -e "  ${CYAN}1. Connect to Tailscale network:${NC}"
echo "       sudo tailscale up"
echo "       # Open the login URL in your browser"
echo ""
echo -e "  ${CYAN}2. Note your Tailscale IP:${NC}"
echo "       tailscale ip -4"
echo ""
echo -e "  ${CYAN}3. Switch to deploy user:${NC}"
echo "       su - ${DEPLOY_USER}"
echo ""
echo -e "  ${CYAN}4. Clone repo at a specific release tag:${NC}"
echo "       git clone --recurse-submodules <repo-url>"
echo "       cd ctf-analytics-platform"
echo "       git checkout v1.0.0-data-collection"
echo ""
echo -e "  ${CYAN}5. Configure environment:${NC}"
echo "       cp .env.prod.example .env.prod"
echo "       nano .env.prod   # fill in all values"
echo ""
echo -e "  ${CYAN}6. Deploy:${NC}"
echo "       bash deploy/start-production.sh"
echo ""
