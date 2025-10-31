#!/bin/bash
# ─────────────────────────────────────────────
# File: k3s/prep/sync-config-to-nodes.sh
# Purpose: Sync config and storage to worker nodes
# ─────────────────────────────────────────────
set -euo pipefail

log() { printf "[*] %s\n" "$*"; }

NODES=("pc-ika" "researchpc")
CONFIG_SRC="$HOME/rstudio-tier-setup/config/users.yaml"

log "Syncing config to worker nodes..."

for node in "${NODES[@]}"; do
    log "Syncing to $node..."
    
    # Create directory on remote node
    ssh "$node" "sudo mkdir -p /opt/rpod-config"
    
    # Copy config
    scp "$CONFIG_SRC" "$node:/tmp/users.yaml"
    ssh "$node" "sudo mv /tmp/users.yaml /opt/rpod-config/ && sudo chmod 644 /opt/rpod-config/users.yaml"
    
    log "  ✓ Synced to $node"
done

log "✅ Config synced to all nodes!"
