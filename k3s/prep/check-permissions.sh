#!/bin/bash
# ─────────────────────────────────────────────
# File: k3s/prep/check-permissions.sh
# Purpose: Verify host permissions for k3s mounts
# ─────────────────────────────────────────────
set -euo pipefail

log() { printf "[*] %s\n" "$*"; }
warn() { printf "[!] WARNING: %s\n" "$*"; }
error() { printf "[✘] ERROR: %s\n" "$*"; }

PROJECT_CENTER="/opt/project_center_mirror"
USER_HOMES="/opt/user_homes"
SHARED_RLIB="/opt/shared-r-library"

log "Checking host permissions..."

# Check if directories exist
for dir in "$PROJECT_CENTER" "$USER_HOMES" "$SHARED_RLIB"; do
    if [[ ! -d "$dir" ]]; then
        error "Directory missing: $dir"
        exit 1
    fi
    log "✓ Directory exists: $dir"
done

# Check read permissions on project center
if [[ ! -r "$PROJECT_CENTER" ]]; then
    error "Cannot read $PROJECT_CENTER"
    exit 1
fi
log "✓ Readable: $PROJECT_CENTER"

# Check specific test folder
TEST_FOLDER="$PROJECT_CENTER/ARC8. Global Surgery Institute/8.1 Workforce"
if [[ -d "$TEST_FOLDER" ]]; then
    if [[ ! -r "$TEST_FOLDER" ]]; then
        error "Cannot read test folder: $TEST_FOLDER"
        exit 1
    fi
    log "✓ Readable: $TEST_FOLDER"
else
    warn "Test folder not found: $TEST_FOLDER"
fi

# Check write permission on user homes
if [[ ! -w "$USER_HOMES" ]]; then
    error "Cannot write to $USER_HOMES"
    exit 1
fi
log "✓ Writable: $USER_HOMES"

# Check shared R library
if [[ ! -r "$SHARED_RLIB" ]]; then
    error "Cannot read $SHARED_RLIB"
    exit 1
fi
log "✓ Readable: $SHARED_RLIB"

# Display permissions
log ""
log "Permission summary:"
ls -ld "$PROJECT_CENTER" "$USER_HOMES" "$SHARED_RLIB"

log ""
log "✅ All permission checks passed!"
log ""
log "Note: K3s pods run as root inside the container by default,"
log "so hostPath mounts should be accessible as long as the host"
log "directories are readable/writable by root or world-readable."


