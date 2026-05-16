#!/bin/bash
set -e
echo "Setting up CTF production environment..."
docker compose pull
docker compose build
