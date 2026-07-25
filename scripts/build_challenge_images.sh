#!/usr/bin/env bash
# Build the Docker images for the interactive (red-team) challenges.
#
# The orchestrator starts a challenge by running the image named
# "challenge-<id>", where <id> comes from that challenge's challenge.json. Nothing
# in the repository built those images, so a fresh deployment has none and every
# start_session() call fails at the Docker layer even when the manifest is present.
#
# Run once after deploying, and again whenever a challenge's Dockerfile changes.
#
#   bash scripts/build_challenge_images.sh          # build all
#   bash scripts/build_challenge_images.sh red_ghost_login   # build one

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ONLY="${1:-}"
built=0; skipped=0; failed=0

for manifest in "$REPO_ROOT"/challenges/*/*/challenge.json; do
    dir="$(dirname "$manifest")"
    id="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['id'])" "$manifest")"

    if [ -n "$ONLY" ] && [ "$ONLY" != "$id" ]; then
        continue
    fi

    if [ ! -f "$dir/Dockerfile" ]; then
        echo "  skip  $id — no Dockerfile (static challenge)"
        skipped=$((skipped+1))
        continue
    fi

    image="challenge-$id"
    printf '  build %s ... ' "$image"
    if docker build -q -t "$image" "$dir" >/dev/null 2>&1; then
        echo "ok"
        built=$((built+1))
    else
        echo "FAILED"
        echo "        re-run to see the error:  docker build -t $image $dir"
        failed=$((failed+1))
    fi
done

echo
echo "built=$built skipped=$skipped failed=$failed"

echo
echo "Images now available:"
docker images --format '{{.Repository}}:{{.Tag}}' \
  | grep '^challenge-' | sort | sed 's/^/  /' || echo "  (none)"

[ "$failed" -eq 0 ]
