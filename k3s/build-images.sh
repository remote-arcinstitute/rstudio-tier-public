#!/bin/bash
# ─────────────────────────────────────────────
# File: k3s/build-images.sh
# Purpose: Build all required images for k3s deployment
# ─────────────────────────────────────────────
set -euo pipefail

log() { printf "[*] %s\n" "$*"; }
error() { printf "[✘] ERROR: %s\n" "$*"; exit 1; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log "Building images from: $REPO_ROOT"

# ── Build RStudio tier image ────────────────────────────────────────────────────
log "Building rstudio-tier image..."
if ! podman build -t localhost/rstudio-tier:latest -f k3s/Dockerfile.rstudio .; then
    error "Failed to build rstudio-tier image"
fi
log "✓ Built: localhost/rstudio-tier:latest"

# ── Build API image ─────────────────────────────────────────────────────────────
log "Building rpod-api-k8s image..."
if ! podman build -t localhost/rpod-api-k8s:latest -f k3s/api/Dockerfile.api-k8s .; then
    error "Failed to build rpod-api-k8s image"
fi
log "✓ Built: localhost/rpod-api-k8s:latest"

# ── Verify images ───────────────────────────────────────────────────────────────
log ""
log "Verifying images..."
podman images | grep -E "rstudio-tier|rpod-api-k8s" || error "Images not found"

log ""
log "✅ All images built successfully!"
log ""
log "Images available:"
log "  - localhost/rstudio-tier:latest"
log "  - localhost/rpod-api-k8s:latest"
log ""
log "Next steps:"
log "  1. Run prep: ./k3s/prep/setup-storage.sh"
log "  2. Apply k3s manifests: kubectl apply -f k3s/manifests/"
