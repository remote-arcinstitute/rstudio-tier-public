#!/bin/bash
set -e

echo "🚀 Building RPOD System"
echo "======================="

# Export current user UID/GID for docker-compose
export UID=$(id -u)
export GID=$(id -g)

echo "Running as UID=$UID, GID=$GID"

# Check podman socket
PODMAN_SOCK="/run/user/$UID/podman/podman.sock"
if [ ! -S "$PODMAN_SOCK" ]; then
    echo "⚠️  Podman socket not found at $PODMAN_SOCK"
    echo "Starting podman socket..."
    systemctl --user start podman.socket
    sleep 2
fi

# Build RStudio tier image
echo ""
echo "📦 Building RStudio Tier Image..."
cd back-rpod-setup/01_build
if [ ! -f "Dockerfile.tier" ]; then
    echo "❌ Dockerfile.tier not found"
    exit 1
fi

podman build -t rstudio-tier -f Dockerfile.tier .
echo "✅ RStudio tier image built"
cd ../..

# Build frontend and backend
echo ""
echo "📦 Building Frontend and Backend..."
podman-compose build

# Start services
echo ""
echo "🚀 Starting Services..."
podman-compose up -d

# Wait for services
echo ""
echo "⏳ Waiting for services to start..."
sleep 5

# Health checks
echo ""
echo "🔍 Health Checks:"
echo "  Frontend: http://localhost:6123"
curl -s http://localhost:6123/health | python3 -m json.tool || echo "  ❌ Frontend not responding"

echo "  Backend: http://localhost:6124"
curl -s http://localhost:6124/health | python3 -m json.tool || echo "  ❌ Backend not responding"

echo ""
echo "✅ Done! Access frontend at: http://localhost:6123"
echo ""
echo "📝 Check logs with: podman-compose logs -f"