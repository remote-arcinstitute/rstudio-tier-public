#!/bin/bash
# ─────────────────────────────────────────────
# File: k3s/test-deployment.sh
# Purpose: Test rpod deployment end-to-end
# ─────────────────────────────────────────────
set -euo pipefail

log() { printf "[*] %s\n" "$*"; }
error() { printf "[✘] ERROR: %s\n" "$*"; exit 1; }
success() { printf "[✓] %s\n" "$*"; }

API_POD=$(kubectl get pod -l app=rpod-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
[[ -z "$API_POD" ]] && error "API pod not found. Run ./k3s/deploy.sh first"

log "Testing rpod deployment..."
log "API Pod: $API_POD"
log ""

# ── Test 1: Health check ────────────────────────────────────────────────────────
log "Test 1: Health check"
HEALTH=$(kubectl exec "$API_POD" -- curl -s http://localhost:6124/health)
if echo "$HEALTH" | grep -q '"status":"healthy"'; then
    success "API is healthy"
else
    error "Health check failed: $HEALTH"
fi

# ── Test 2: List users ──────────────────────────────────────────────────────────
log ""
log "Test 2: List users"
USERS=$(kubectl exec "$API_POD" -- curl -s http://localhost:6124/users)
if echo "$USERS" | grep -q 'julianbs'; then
    success "Users loaded: $(echo "$USERS" | grep -o '"count":[0-9]*')"
else
    error "Failed to load users: $USERS"
fi

# ── Test 3: Launch RStudio for julianbs ────────────────────────────────────────
log ""
log "Test 3: Launch RStudio pod for julianbs"
LAUNCH=$(kubectl exec "$API_POD" -- curl -s -X POST http://localhost:6124/launch -d 'username=julianbs')
echo "$LAUNCH" | jq '.' 2>/dev/null || echo "$LAUNCH"

if echo "$LAUNCH" | grep -q '"ok":true'; then
    success "Launch request successful"
    PORT=$(echo "$LAUNCH" | grep -o '"port":[0-9]*' | cut -d: -f2)
    URL=$(echo "$LAUNCH" | grep -o '"redirect_url":"[^"]*"' | cut -d'"' -f4)
    log "  Port: $PORT"
    log "  URL: $URL"
else
    error "Launch failed: $LAUNCH"
fi

# ── Test 4: Check pod status ────────────────────────────────────────────────────
log ""
log "Test 4: Waiting for RStudio pod to start..."
sleep 5

kubectl get pods -l app=rstudio
RSTUDIO_POD=$(kubectl get pod -l user=julianbs -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -n "$RSTUDIO_POD" ]]; then
    success "RStudio pod created: $RSTUDIO_POD"
    
    log "  Waiting for pod to be ready..."
    kubectl wait --for=condition=ready pod "$RSTUDIO_POD" --timeout=60s || log "  (Pod still starting...)"
    
    log ""
    log "  Pod details:"
    kubectl get pod "$RSTUDIO_POD" -o wide
    
    log ""
    log "  Pod logs (last 10 lines):"
    kubectl logs "$RSTUDIO_POD" --tail=10 || log "  (Logs not available yet)"
else
    error "RStudio pod not found"
fi

# ── Test 5: Check service ───────────────────────────────────────────────────────
log ""
log "Test 5: Check NodePort service"
SVC=$(kubectl get svc -l user=julianbs -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -n "$SVC" ]]; then
    success "Service created: $SVC"
    kubectl get svc "$SVC"
else
    error "Service not found"
fi

# ── Summary ─────────────────────────────────────────────────────────────────────
log ""
log "======================================================================"
log "✅ All tests passed!"
log "======================================================================"
log ""
log "Access RStudio at: $URL"
log "Username: julianbs"
log "Password: julianpw"
log ""
log "Cleanup:"
log "  kubectl exec $API_POD -- curl -s -X POST http://localhost:6124/stop -d 'username=julianbs'"
log "  Or: kubectl delete pod $RSTUDIO_POD"
