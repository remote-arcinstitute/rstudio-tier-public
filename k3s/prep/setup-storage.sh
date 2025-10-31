#!/bin/bash
# ─────────────────────────────────────────────
# File: k3s/prep/setup-storage.sh
# Purpose: Prepare host storage for k3s RStudio deployment
# ─────────────────────────────────────────────
set -euo pipefail

log() { printf "[*] %s\n" "$*"; }
error() { printf "[!] ERROR: %s\n" "$*" >&2; exit 1; }

# ── Configuration ────────────────────────────
PROJECT_CENTER="/opt/project_center_mirror"
USER_HOMES="/opt/user_homes"
SHARED_RLIB="/opt/shared-r-library"
CONTAINER_IMAGE="localhost/rstudio-tier:latest"
# FIX: Use absolute path instead of relative cd
REPO_ROOT="/home/julianbs/rstudio-tier-setup"

# ── Checks ───────────────────────────────────
log "Checking prerequisites..."
[[ -d "$PROJECT_CENTER" ]] || error "Project center not found: $PROJECT_CENTER"
command -v podman >/dev/null || error "Podman not installed"
[[ -d "$REPO_ROOT" ]] || error "Repo not found: $REPO_ROOT"

# ── Create directories ───────────────────────
log "Creating directory structure..."
mkdir -p "$USER_HOMES" "$SHARED_RLIB"
chown arcinstitute:main "$USER_HOMES"
chmod 775 "$USER_HOMES"  # FIX: Make writable by group

# ── Extract R library from container ─────────
log "Extracting shared R library from container..."
if ! podman image exists "$CONTAINER_IMAGE"; then
    log "Building rstudio-tier image first..."
    cd "$REPO_ROOT"
    podman build -t "$CONTAINER_IMAGE" -f k3s/Dockerfile.rstudio .
fi

# Run temporary container to extract R libs
TEMP_CONTAINER="rstudio-temp-extract-$$"
podman run -d --name "$TEMP_CONTAINER" "$CONTAINER_IMAGE" sleep 300
podman cp "$TEMP_CONTAINER:/usr/local/lib/R/site-library/." "$SHARED_RLIB/"
podman rm -f "$TEMP_CONTAINER"

chown -R root:root "$SHARED_RLIB"
chmod -R 755 "$SHARED_RLIB"

# ── Summary ──────────────────────────────────
log "✅ Storage preparation complete!"
log ""
log "Directories created:"
log "  Project Center: $PROJECT_CENTER ($(du -sh $PROJECT_CENTER 2>/dev/null | cut -f1 || echo 'N/A'))"
log "  User Homes:     $USER_HOMES"
log "  Shared R Lib:   $SHARED_RLIB ($(du -sh $SHARED_RLIB 2>/dev/null | cut -f1 || echo 'N/A'))"
log ""
log "Next steps:"
log "  1. Review k3s/manifests/ YAML files"
log "  2. Apply: kubectl apply -f k3s/manifests/"
