#!/usr/bin/env bash
set -e

FLAG="flag{3a94ecb064f591a63c5a0644e4844f26}"

# ซ่อน flag ไว้ไม่ตรง home
mkdir -p /srv/backups/.staging
echo "$FLAG" > /srv/backups/.staging/.ops-archive.flag
chmod 644 /srv/backups/.staging/.ops-archive.flag

# สร้างเบาะแสหลายชั้น
cat > /home/player/.cache/sessions/last_sync.log <<'EOF'
[session-sync]
status=warning
target=/srv/backups/.staging
note=old archive path still readable by ops during migration
EOF

cat > /opt/internal/recovery-note.txt <<'EOF'
Ops migration checklist
- remove old staged backups
- validate archive permissions
- rotate credentials after cutover
EOF

# สิทธิ์
chown -R player:player /home/player
chmod 700 /home/player/.cache
chmod 700 /home/player/.cache/sessions
chmod 644 /home/player/.cache/sessions/last_sync.log
chmod 644 /opt/internal/recovery-note.txt

# กัน default motd เยอะเกิน
rm -f /etc/update-motd.d/*
touch /var/run/utmp

# sshd does not pass this container's environment to user sessions, so the
# telemetry helper reads the orchestrator address from here instead. Written at
# startup because SESSION_ID/USER_ID differ per session.
umask 022
cat > /etc/ctf-telemetry.env <<ENVEOF
ORCH_URL="${ORCH_URL:-}"
SESSION_ID="${SESSION_ID:-}"
USER_ID="${USER_ID:-}"
CHALLENGE_ID="${CHALLENGE_ID:-}"
ENVEOF
chmod 644 /etc/ctf-telemetry.env

exec /usr/sbin/sshd -D
