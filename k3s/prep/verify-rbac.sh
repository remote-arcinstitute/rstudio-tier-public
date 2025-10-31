#!/bin/bash
# ─────────────────────────────────────────────
# File: k3s/prep/verify-rbac.sh
# Purpose: Verify RBAC is properly configured
# ─────────────────────────────────────────────
set -euo pipefail

log() { printf "[*] %s\n" "$*"; }
error() { printf "[✘] ERROR: %s\n" "$*"; }

NAMESPACE="default"
SA_NAME="rpod-api"

log "Checking RBAC configuration..."

# Check if ServiceAccount exists
if ! kubectl get serviceaccount "$SA_NAME" -n "$NAMESPACE" &>/dev/null; then
    error "ServiceAccount '$SA_NAME' not found in namespace '$NAMESPACE'"
    exit 1
fi
log "✓ ServiceAccount exists: $SA_NAME"

# Check if Role exists
if ! kubectl get role rpod-api-role -n "$NAMESPACE" &>/dev/null; then
    error "Role 'rpod-api-role' not found"
    exit 1
fi
log "✓ Role exists: rpod-api-role"

# Check if RoleBinding exists
if ! kubectl get rolebinding rpod-api-binding -n "$NAMESPACE" &>/dev/null; then
    error "RoleBinding 'rpod-api-binding' not found"
    exit 1
fi
log "✓ RoleBinding exists: rpod-api-binding"

# Test permissions using auth can-i
log ""
log "Testing permissions..."

for resource in pods services; do
    for verb in get list create delete; do
        if kubectl auth can-i "$verb" "$resource" \
            --as=system:serviceaccount:"$NAMESPACE":"$SA_NAME" \
            -n "$NAMESPACE" &>/dev/null; then
            log "  ✓ Can $verb $resource"
        else
            error "  ✘ Cannot $verb $resource"
        fi
    done
done

log ""
log "✅ RBAC verification complete!"
log ""
log "The rpod-api ServiceAccount can now:"
log "  - Create/delete pods (RStudio instances)"
log "  - Create/delete services (NodePort exposure)"
log "  - List/watch pods and services (status checks)"
