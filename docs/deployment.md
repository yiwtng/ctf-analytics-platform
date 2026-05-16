# Deployment Guide

## Prerequisites

- Docker & Docker Compose v2
- Python 3.12+ (for research tools)
- Gemini or OpenAI API key (for AI reports)

## Quick Start

### 1. Clone the repository

```bash
git clone --recurse-submodules https://github.com/thanagrit-wutthiamornthada/ctf-analytics-platform.git
cd ctf-analytics-platform
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your domain, credentials, and API keys
nano .env
```

### 3. Build challenge Docker images

```bash
docker build -t challenge-red_ghost_login    ./challenges/red/ghost_login
docker build -t challenge-red_pivot_notes    ./challenges/red/pivot_notes
docker build -t challenge-red_protocol_probe ./challenges/red/protocol_probe
docker build -t challenge-red_log_poisoning  ./challenges/red/log_poisoning
```

### 4. Start all services

```bash
docker compose up -d
docker compose ps   # verify all services are healthy
```

### 5. Create CTFd challenges and users

```bash
export CTFD_TOKEN="your-ctfd-admin-token"

# Create challenges
python tools/setup/create_all_challenges.py

# Create users (edit tools/setup/users.csv first)
python tools/setup/create_users.py
```

---

## Common Operations

| Action | Command |
|---|---|
| Start all services | `docker compose up -d` |
| Stop all services | `docker compose down` |
| Restart CTFd | `docker compose restart ctfd` |
| View CTFd logs | `docker compose logs --tail=200 ctfd` |
| View orchestrator logs | `docker compose logs --tail=200 orchestrator` |
| Check service status | `docker compose ps` |
| Full rebuild | `docker compose down -v && docker compose up -d --build` |
| Rebuild orchestrator only | `docker compose build --no-cache orchestrator && docker compose up -d orchestrator` |

---

## Research Tools

```bash
# Activate Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r platform/orchestrator/requirements.txt playwright
playwright install chromium

# Generate AI reports for all users
python tools/analysis/generate_all_ai_reports.py

# Simulate cohort study (3 participants × 3 rounds)
python tools/research/simulate_round_comparison_cohort.py

# Submit participant feedback
python tools/research/submit_feedback_natural.py

# Analyze Red Team behavior from analytics DB
python tools/analysis/analyze_red_behavior.py

# Delete users (before reset)
USERS_CSV=tools/setup/round_comparison_users.csv python tools/setup/delete_users.py
```

---

## Network Access

The platform supports two networking modes:

- **LAN** (`cp .env.lan .env`) — for local network deployment
- **Tailscale** (`cp .env.tailscale .env`) — for secure remote access overlay network

---

## Database Access

```bash
# Connect to analytics database directly
docker exec -it analytics_db psql -U analytics -d analytics
```

---

## Services & Ports

| Service | Port | URL |
|---|---|---|
| CTFd (platform) | 80 | `http://${CTF_DOMAIN}` |
| Orchestrator (API) | — | `http://${ORCH_DOMAIN}` |
| Grafana (dashboard) | 3000 | `http://localhost:3000` |
| Traefik (proxy UI) | 8080 | `http://localhost:8080` |
| Analytics DB | 5433 | `localhost:5433` |
| NC challenges | 31001–31999 | dynamic |
| SSH challenges | 32223–32999 | dynamic |
