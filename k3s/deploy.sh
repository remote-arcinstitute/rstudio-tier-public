#!/bin/bash
# ─────────────────────────────────────────────
# File: k3s/deploy.sh
# Purpose: Deploy rpod system to k3s
# ─────────────────────────────────────────────
set -euo pipefail

log() { printf "[*] %s\n" "$*"; }
error() { printf "[✘] ERROR: %s\n" "$*"; exit 1; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log "Deploying rpod system to k3s..."

# ── Check prerequisites ─────────────────────────────────────────────────────────
log "Checking prerequisites..."

command -v kubectl &>/dev/null || error "kubectl not found"
kubectl cluster-info &>/dev/null || error "Cannot connect to k3s cluster"

# Check if images exist
for img in localhost/rstudio-tier:latest localhost/rpod-api-k8s:latest; do
    if ! podman image exists "$img"; then
        error "Image not found: $img (run ./k3s/build-images.sh first)"
    fi
done
log "✓ Images available"

# Check if storage is prepared
for dir in /opt/project_center_mirror /opt/user_homes /opt/shared-r-library; do
    if [[ ! -d "$dir" ]]; then
        error "Directory missing: $dir (run ./k3s/prep/setup-storage.sh first)"
    fi
done
log "✓ Storage prepared"

# Check config exists
if [[ ! -f "$REPO_ROOT/config/users.yaml" ]]; then
    error "Config missing: $REPO_ROOT/config/users.yaml"
fi
log "✓ Config file exists"

# ── Apply manifests ─────────────────────────────────────────────────────────────
log ""
log "Applying k8s manifests..."

# RBAC (should already be applied)
kubectl apply -f k3s/manifests/rbac.yaml
log "✓ RBAC applied"

# API Deployment (no configmap needed - uses hostPath)
kubectl apply -f k3s/manifests/api-deployment.yaml
log "✓ API deployment applied"

# ── Wait for API to be ready ────────────────────────────────────────────────────
log ""
log "Waiting for API pod to be ready..."
kubectl wait --for=condition=ready pod -l app=rpod-api --timeout=120s || error "API pod failed to start"
log "✓ API pod ready"

# ── Display status ──────────────────────────────────────────────────────────────
log ""
log "✅ Deployment complete!"
log ""
log "Status:"
kubectl get pods -l app=rpod-api
kubectl get svc rpod-api

log ""
log "API endpoints:"
API_POD=$(kubectl get pod -l app=rpod-api -o jsonpath='{.items[0].metadata.name}')
log "  Health check: kubectl exec $API_POD -- curl -s http://localhost:6124/health"
log "  List users:   kubectl exec $API_POD -- curl -s http://localhost:6124/users"
log ""
log "View logs:"
log "  kubectl logs -f $API_POD"
log ""
log "Test launching RStudio:"
log "  kubectl exec $API_POD -- curl -X POST http://localhost:6124/launch -d 'username=julianbs'"
