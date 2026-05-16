#!/bin/bash
set -e

DB_CONTAINER="${DB_CONTAINER:-analytics_db}"
DB_USER="${DB_USER:-analytics}"
DB_NAME="${DB_NAME:-analytics}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-./db/migrations}"

if [ ! -d "$MIGRATIONS_DIR" ]; then
  echo "[!] migrations directory not found: $MIGRATIONS_DIR"
  exit 1
fi

for f in $(ls "$MIGRATIONS_DIR"/*.sql | sort); do
  echo "[*] Applying migration: $f"
  docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" < "$f"
done

echo "[+] All migrations applied successfully."