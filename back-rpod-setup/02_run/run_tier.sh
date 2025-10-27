#!/bin/bash
# ─────────────────────────────────────────────
# File: 02_run/run_tier.sh
# ─────────────────────────────────────────────
set -euo pipefail

ROOT="${ROOT:-$HOME/rstudio-tier-setup}"
IMAGE="${IMAGE:-rstudio-tier}"
CONTAINER="${CONTAINER:-rstudio-tier}"
PORT="${PORT:-8787}"
MOCK_ROOT="$HOME/mockdir"

# Sanity checks
[[ -d "$MOCK_ROOT" ]] || { echo "❌ Missing $MOCK_ROOT — run mockdir setup first."; exit 1; }

podman rm -f "$CONTAINER" 2>/dev/null || true

podman run -d \
  --name "$CONTAINER" \
  -p 8787:8787 \
  -v "$ROOT/01_build/mock_users.txt:/etc/rstudio/users.txt:ro" \
  -v "$ROOT/01_build/tier_limits.conf:/etc/rstudio/tier_limits.conf:ro" \
  -v "$ROOT/02_run:/var/lib/rstudio" \
  -v "$MOCK_ROOT/shared-r-library:/usr/local/lib/R/site-library:ro" \
  -v "$MOCK_ROOT/Project Center:/mockdir/Project Center:ro" \
  -v "$MOCK_ROOT/user_home:/home:rw" \
  "$IMAGE"

echo "[✔] Container started"
echo "Visit: http://localhost:${PORT}"
echo "Logs:  podman logs -f $CONTAINER"
