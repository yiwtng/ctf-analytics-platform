#!/usr/bin/env bash
# =============================================================================
# cut-release.sh — Create a signed release tag for IRB data collection
# =============================================================================
# Runs the full test suite, then creates an annotated git tag.
# Must be run on the DEV machine (not the prod VM).
#
# Usage:
#   bash deploy/cut-release.sh
#   bash deploy/cut-release.sh --tag v1.0.1-data-collection  # custom tag
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

DEFAULT_TAG="v1.0.0-data-collection"
TAG="${1:-}"
if [[ "${TAG}" == "--tag" ]]; then
  TAG="${2:-${DEFAULT_TAG}}"
elif [[ -z "${TAG}" ]]; then
  TAG="${DEFAULT_TAG}"
fi

step()  { echo -e "\n${CYAN}─── $* ───────────────────────────────────────────${NC}"; }
ok()    { echo -e "${GREEN}✓ $*${NC}"; }
abort() { echo -e "${RED}✗ ABORT: $*${NC}"; exit 1; }

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  CTF Analytics Platform — Cut Release${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "  Proposed tag : ${TAG}"
echo "  Commit       : $(git rev-parse --short HEAD)"
echo "  Branch       : $(git rev-parse --abbrev-ref HEAD)"
echo ""

# ── Check for uncommitted changes ─────────────────────────────────────────────
step "Checking working tree state"
if ! git diff --quiet || ! git diff --cached --quiet; then
  abort "Uncommitted changes detected. Commit or stash them before tagging."
fi
ok "Working tree is clean."

# ── Check tag doesn't already exist ──────────────────────────────────────────
step "Checking tag uniqueness"
if git tag --list | grep -q "^${TAG}$"; then
  abort "Tag '${TAG}' already exists. Use a different tag name or delete the existing one."
fi
ok "Tag '${TAG}' is available."

# ── Run full test suite ───────────────────────────────────────────────────────
step "Running full pytest suite (must pass 100%)"
echo ""
PYTEST_EXIT=0
python3 -m pytest tests/ -v --tb=short 2>&1 | tee /tmp/ctf_release_tests.log || PYTEST_EXIT=$?

if [[ ${PYTEST_EXIT} -ne 0 ]]; then
  abort "Tests FAILED. Fix all failures before tagging a release.
  Full log: /tmp/ctf_release_tests.log"
fi

TOTAL=$(grep -oE '[0-9]+ passed' /tmp/ctf_release_tests.log | tail -1 || echo "? passed")
ok "All tests passed: ${TOTAL}"

# ── Create annotated tag ──────────────────────────────────────────────────────
step "Creating annotated release tag"
git tag -a "${TAG}" \
  -m "Frozen release for IRB-approved data collection

Tests  : ${TOTAL}
Commit : $(git rev-parse HEAD)
Date   : $(date -Iseconds)
"

ok "Tag created: ${TAG}"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Release tag '${TAG}' created successfully.${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo -e "${CYAN}Next steps:${NC}"
echo ""
echo "  1. Push the tag to remote:"
echo "       git push origin ${TAG}"
echo ""
echo "  2. On the prod VM, fetch and checkout the tag:"
echo "       git fetch --tags"
echo "       git checkout ${TAG}"
echo "       git submodule update --init --recursive"
echo ""
echo "  3. Deploy:"
echo "       bash deploy/start-production.sh"
echo ""
