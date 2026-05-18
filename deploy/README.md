# Production Deployment — deploy/

Scripts for deploying the CTF Analytics Platform on a Parallels Ubuntu VM accessed via Tailscale. All scripts assume they are run from the **repository root**.

---

## Quick reference

| Script | Purpose | Run on |
|---|---|---|
| `deploy/setup-prod-vm.sh` | One-time VM provisioning | prod VM (as root) |
| `deploy/cut-release.sh` | Tag a frozen release | dev machine |
| `deploy/start-production.sh` | Full deploy (reset DB + launch) | prod VM |
| `deploy/preflight-check.sh` | 8-point pre-launch gate | prod VM |
| `deploy/monitor.sh` | Live resource monitor | prod VM |
| `deploy/stop-production.sh` | Graceful shutdown + backup | prod VM |
| `deploy/backup-db.sh` | On-demand DB backup | prod VM |
| `deploy/install-backup-cron.sh` | Hourly cron backup | prod VM |

---

## Deployment sequence

### First-time setup (do once)

```bash
# 1. On the prod VM (as root):
sudo bash deploy/setup-prod-vm.sh

# 2. Authenticate Tailscale:
sudo tailscale up
# open the URL shown, complete auth in browser
tailscale ip -4   # note the IP for .env.prod

# 3. Switch to deploy user and clone at a tag:
su - ctfadmin
git clone --recurse-submodules <repo-url>
cd ctf-analytics-platform
git checkout v1.0.0-data-collection

# 4. Fill in environment:
cp .env.prod.example .env.prod
nano .env.prod   # fill in every value (no placeholders!)

# 5. Install hourly backup cron:
bash deploy/install-backup-cron.sh
```

### Before each data collection round

```bash
# On dev machine — tag and push a frozen release:
bash deploy/cut-release.sh
git push origin v1.0.0-data-collection

# On prod VM — deploy (resets DB, rebuilds images, starts stack):
bash deploy/start-production.sh
# Type: DEPLOY

# Run pre-flight gate before opening to participants:
bash deploy/preflight-check.sh

# Start live monitor in a dedicated terminal:
bash deploy/monitor.sh
```

### After each round

```bash
# Stop and preserve data (takes final backup, does NOT delete volumes):
bash deploy/stop-production.sh
# Type: STOP
```

---

## Script details

### `deploy/setup-prod-vm.sh`

Idempotent. Installs Docker Engine (official script), Docker Compose plugin, Tailscale, and creates the `ctfadmin` deploy user. Writes `/etc/ctf-prod-vm` marker that `start-production.sh` uses to verify it is running on the right host.

### `deploy/start-production.sh`

Runs 10 sequential steps:
1. Verify `/etc/ctf-prod-vm` marker (abort if on dev machine)
2. Validate `.env.prod` (no placeholders)
3. Confirm git is on a release tag (not a branch)
4. Interactive `DEPLOY` confirmation
5. Pre-reset backup (if analytics_db is running)
6. Reset analytics DB via `database/scripts/reset_analytics_db.sql`
7. `docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d --build`
8. Poll healthchecks (120s timeout)
9. Run `verify_data_provenance.py` (expect 0 users at start)
10. Print Tailscale URL + participant checklist

### `deploy/preflight-check.sh`

Checks and prints ✓/✗ for:
1. Git is at a release tag
2. `.env.prod` has no placeholder values
3. All 7 containers are `healthy`
4. Analytics DB is empty (or operator confirms intentional data)
5. `verify_data_provenance.py` passes
6. Tailscale is up with a valid IP
7. Disk space > 20 GB free
8. `pytest tests/smoke` passes against the live system

Exits 1 if any check fails.

### `deploy/backup-db.sh`

Writes `deploy/backups/prod-YYYYMMDD-HHMM.sql.gz`. Prunes backups older than 72 hours. Exits non-zero if `pg_dump` fails or the dump is suspiciously small.

### `deploy/install-backup-cron.sh`

Adds an hourly cron job: `0 * * * * bash <repo>/deploy/backup-db.sh >> /var/log/ctf_backup.log 2>&1`. Idempotent (safe to re-run). Remove with `--uninstall`.

### `deploy/monitor.sh`

Refreshes every 10s: container CPU/RAM, disk free, total events, enrollments, events-per-60s, active users in last 5 min, per-container health. Press Ctrl+C to exit.

### `deploy/stop-production.sh`

Interactive `STOP` confirmation → final backup → `docker compose down` (no `-v`; volumes preserved).

### `deploy/cut-release.sh`

Run on dev machine. Runs `pytest tests/ -v` (must be 100% pass), then `git tag -a v1.0.0-data-collection`. Aborts on any test failure.

---

## Troubleshooting

### Container not healthy

```bash
# View logs for a specific service
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=100 orchestrator

# Check healthcheck output
docker inspect analytics_db_prod | python3 -c "import sys,json; h=json.load(sys.stdin)[0]['State']['Health']; [print(l['Output']) for l in h['Log'][-3:]]"

# Force restart a single service
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod restart orchestrator
```

### Tailscale not connected

```bash
sudo tailscale status          # check connection state
sudo tailscale up              # re-authenticate if needed
sudo systemctl restart tailscaled
tailscale ip -4                # get current IP
```

### Disk full

```bash
df -h /                                # check usage
docker system prune -f                 # remove unused images/containers
ls -lh deploy/backups/                 # check backup sizes
# Keep only the last 3 backups manually if cron pruning hasn't run yet
ls -t deploy/backups/prod-*.sql.gz | tail -n +4 | xargs rm -f
```

### Orchestrator OOM or slow

```bash
bash deploy/monitor.sh   # watch CPU/RAM in real time
# If RAM is consistently >90%, reduce MAX_CONCURRENT_SESSIONS in .env.prod
# then: docker compose ... up -d orchestrator  (restarts only orchestrator)
```

---

## Rollback procedure

If a deployment fails and data is at risk:

```bash
# 1. Stop the broken stack (no volume delete)
bash deploy/stop-production.sh
# type: STOP

# 2. Restore the most recent good backup
LATEST=$(ls -t deploy/backups/prod-*.sql.gz | head -1)
echo "Restoring from: ${LATEST}"

# Start only the DB
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d analytics_db

# Wait for DB to be ready, then restore
set -a; source .env.prod; set +a
gunzip -c "${LATEST}" | docker exec -i analytics_db_prod psql \
  -U "${ANALYTICS_DB_USER}" -d "${ANALYTICS_DB_NAME}"

# 3. Fix the underlying issue (check logs, fix code)
# 4. Re-tag if needed: bash deploy/cut-release.sh --tag v1.0.1-data-collection
# 5. Redeploy: bash deploy/start-production.sh
```

---

## Compose override pattern

The production stack uses Docker Compose [override files](https://docs.docker.com/compose/multiple-compose-files/):

```bash
docker compose \
  -f docker-compose.yml \          # base (never edited)
  -f docker-compose.prod.yml \     # prod overrides only
  --env-file .env.prod \           # prod credentials
  up -d --build
```

`docker-compose.prod.yml` overrides:
- Container names: `<service>_prod` suffix (prevents collision with dev)
- Volumes: `ctf_prod_*` named volumes (isolated from dev)
- Networks: `ctf_prod_edge`, `ctf_prod_backend`
- `analytics_db` port bound to `127.0.0.1` (not exposed on Tailscale)
- Healthchecks on every service (30s interval, 3 retries)
- `restart: unless-stopped` on every service (survives VM reboot)
