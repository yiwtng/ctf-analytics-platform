#!/usr/bin/env bash
# Apply every migration in order. Safe to re-run: each migration is written to be
# idempotent (IF NOT EXISTS, and DROP CONSTRAINT IF EXISTS before ADD).
#
# The previous defaults pointed at a container and database that do not exist in
# this deployment (analytics_db / analytics) and at a directory that was never
# used (./db/migrations), so the script could not have run as shipped.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DB_CONTAINER="${DB_CONTAINER:-analytics_db_prod}"
DB_USER="${DB_USER:-analytics}"
DB_NAME="${DB_NAME:-analytics_prod}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-$REPO_ROOT/database/migrations}"

if [ ! -d "$MIGRATIONS_DIR" ]; then
  echo "error: migrations directory not found: $MIGRATIONS_DIR" >&2
  exit 1
fi

shopt -s nullglob
files=("$MIGRATIONS_DIR"/*.sql)
if [ ${#files[@]} -eq 0 ]; then
  echo "error: no .sql files in $MIGRATIONS_DIR" >&2
  exit 1
fi

echo "Applying ${#files[@]} migrations to $DB_NAME in $DB_CONTAINER"
for f in $(printf '%s\n' "${files[@]}" | sort); do
  printf '  %-46s ' "$(basename "$f")"
  # ON_ERROR_STOP, so a failing migration halts the run instead of leaving the
  # schema half-applied while later migrations still report success.
  if docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" \
        -q -v ON_ERROR_STOP=1 < "$f" >/dev/null 2>&1; then
    echo "ok"
  else
    echo "FAILED"
    echo >&2
    echo "error: $(basename "$f") failed. Re-run it directly to see why:" >&2
    echo "  docker exec -i $DB_CONTAINER psql -U $DB_USER -d $DB_NAME < $f" >&2
    exit 1
  fi
done

echo "All migrations applied."
