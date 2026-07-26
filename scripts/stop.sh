#!/bin/bash
# Take the stack down. Same --env-file requirement as start.sh: without it
# compose cannot resolve the service definitions it is being asked to stop.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

ENV_FILE="${ENV_FILE:-.env.prod}"
COMPOSE=(-f docker-compose.yml)
[ -f docker-compose.prod.yml ] && COMPOSE+=(-f docker-compose.prod.yml)

docker compose --env-file "$ENV_FILE" "${COMPOSE[@]}" down
