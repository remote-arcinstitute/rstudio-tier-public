#!/bin/bash
# ─────────────────────────────────────────────
# File: k3s/init-rstudio.sh
# Purpose: Initialize RStudio pod for specific user
# ─────────────────────────────────────────────
set -euo pipefail

: "${USERNAME:?USERNAME required}"
: "${PASSWORD:?PASSWORD required}"
: "${USER_HOME:?USER_HOME required}"
: "${TIER:=tier1}"

log() { printf "[*] %s\n" "$*"; }

log "Initializing RStudio for user: $USERNAME (tier: $TIER)"

# ── Create or use main group (GID 1002 to match host)
MAIN_GID=1002
if ! getent group main >/dev/null 2>&1; then
    if getent group $MAIN_GID >/dev/null 2>&1; then
        EXISTING_GROUP=$(getent group $MAIN_GID | cut -d: -f1)
        log "GID $MAIN_GID exists as group '$EXISTING_GROUP', will use it"
        MAIN_GROUP="$EXISTING_GROUP"
    else
        groupadd -g $MAIN_GID main
        log "Created main group (GID $MAIN_GID)"
        MAIN_GROUP="main"
    fi
else
    MAIN_GROUP="main"
fi

# ── Create user if doesn't exist
if ! id "$USERNAME" >/dev/null 2>&1; then
    log "Creating user: $USERNAME"
    useradd -m -d "$USER_HOME" -G "$MAIN_GROUP" -s /bin/bash "$USERNAME"
else
    # Add to main group if already exists
    usermod -aG "$MAIN_GROUP" "$USERNAME"
    log "Added $USERNAME to $MAIN_GROUP group"
fi

# ── Set password
echo "$USERNAME:$PASSWORD" | chpasswd

# ── Set ownership
chown -R "$USERNAME:$USERNAME" "$USER_HOME"

# ── Link R library (if not already linked)
if [[ ! -e "$USER_HOME/R" ]]; then
    ln -sfn /usr/local/lib/R/site-library "$USER_HOME/R"
    log "Linked R library to $USER_HOME/R"
fi

# ── Symlink project folders to user home
PROJECT_ROOT="/project-center"
if [[ -d "$PROJECT_ROOT" ]]; then
    log "Creating project shortcuts in user home..."
    
    # Create a Projects directory in user home
    PROJECTS_DIR="$USER_HOME/Projects"
    mkdir -p "$PROJECTS_DIR"
    
    # Link all mounted institute folders
    for institute_dir in "$PROJECT_ROOT"/*; do
        if [[ -d "$institute_dir" ]]; then
            institute_name=$(basename "$institute_dir")
            target_link="$PROJECTS_DIR/$institute_name"
            
            if [[ ! -e "$target_link" ]]; then
                ln -sfn "$institute_dir" "$target_link"
                log "  Linked: $institute_name → $target_link"
            fi
        fi
    done
    
    chown -R "$USERNAME:$USERNAME" "$PROJECTS_DIR"
else
    log "Warning: No project center found at $PROJECT_ROOT"
fi

log "✅ User setup complete. Starting RStudio Server..."

# Start RStudio Server
exec /init
