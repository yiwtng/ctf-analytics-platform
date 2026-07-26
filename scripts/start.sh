#!/bin/bash
# Bring the stack up.
#
# The --env-file and the prod overlay are not optional. Running plain
# `docker compose up` makes compose look for .env, which this project does not
# use: every ${VAR} then expands to empty, and the orchestrator dies on
# int('') while parsing MAX_CONCURRENT_SESSIONS. That failure mode is confusing
# because the containers are created successfully and only then crash-loop.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

ENV_FILE="${ENV_FILE:-.env.prod}"
if [ ! -f "$ENV_FILE" ]; then
    echo "error: $ENV_FILE not found." >&2
    echo "       Copy .env.prod.example and fill it in, or set ENV_FILE." >&2
    exit 1
fi

COMPOSE=(-f docker-compose.yml)
[ -f docker-compose.prod.yml ] && COMPOSE+=(-f docker-compose.prod.yml)

docker compose --env-file "$ENV_FILE" "${COMPOSE[@]}" up -d --build
docker compose --env-file "$ENV_FILE" "${COMPOSE[@]}" ps
