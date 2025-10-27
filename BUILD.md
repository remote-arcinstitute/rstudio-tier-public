Unified Build Documentation — ARC RStudio Tier Setup

(front-arc-login + back-rpod-setup)

🔍 Overview

This document describes how to build, tag, and connect the ARC RStudio Tier Setup components.
Each service (front-end login and back-end pod controller) is isolated for modularity,
but both can be built locally, pushed to your internal registry, and orchestrated via Compose or K3s.

rstudio-tier-setup/
├── front-arc-login/   → FastAPI portal (port 6123)
└── back-rpod-setup/   → Pod management API (port 6124)

🧩 1. Build context and naming
Component	Path	Dockerfile	Image name	Default Port
Front Login	front-arc-login/	Dockerfile	arc/rstudio-login:latest	6123
Backend API	back-rpod-setup/api/	Dockerfile	arc/rstudio-backend:latest	6124

🧰 2. Building each container manually
    🧱 A. Build the front-end image
```bash
cd ~/rstudio-tier-setup/front-arc-login

podman build -t arc/rstudio-login:latest .
# or docker build -t arc/rstudio-login:latest .
```
Check result:
```bash
podman images | grep rstudio-login
```


    🧱 B. Build the backend image
```bash
cd ~/rstudio-tier-setup/back-rpod-setup/api

podman build -t arc/rstudio-backend:latest -f Dockerfile .
# or docker build -t arc/rstudio-backend:latest -f Dockerfile .
```
Check:
```bash
podman images | grep rstudio-backend
```

🧩 3. Unified testing (manual run)
Run backend first:
```bash
podman run -d --name arc-backend \
  -p 6124:6124 \
  -v ~/rstudio-tier-setup/shared:/shared \
  -v ~/rstudio-tier-setup/front-arc-login/config:/front-config \
  arc/rstudio-backend:latest
```
Then run frontend:
```bash
podman run -d --name arc-login \
  -p 6123:6123 \
  -e BACKEND_URL=http://arc-backend:6124 \
  --add-host arc-backend:127.0.0.1 \
  arc/rstudio-login:latest
```

Open:
➡️ http://localhost:6123

🧩 5. Versioning strategy

Each unified build produces tagged images:

Tag	Meaning
latest	rolling dev build
YYYY.MM	stable monthly snapshot
vX.Y.Z	semantic version release

Tag example:
```bash
podman tag arc/rstudio-login:latest arc/rstudio-login:v1.0.0
podman tag arc/rstudio-backend:latest arc/rstudio-backend:v1.0.0
```

Push to internal registry:
```bash
podman push arc/rstudio-login:v1.0.0 registry.arc.local/arc/rstudio-login:v1.0.0
podman push arc/rstudio-backend:v1.0.0 registry.arc.local/arc/rstudio-backend:v1.0.0
```
🧠 6. Directory permissions and shared mounts

When deploying under Ubuntu or RStudio Server hosts, ensure:
Directory	Ownership	Notes
/home/arcinstitute/rstudio-tier-setup/shared/	arcinstitute:main	shared configs
/home/arcinstitute/rstudio-tier-setup/shared/mockdir/	group researchers	symlink test area
/OneDrive/Riskesdas/	            mounted external data	read-only if synced

🛠 7. Maintenance
Task	Command
Rebuild front-end	podman build -t arc/rstudio-login .
Rebuild backend	podman build -t arc/rstudio-backend -f api/Dockerfile .
Clean all	podman system prune -a
Restart containers	podman restart arc-backend arc-login

🧩 8. Future expansion

Planned integrations:

- Support for per-user persistent storage (RStudio home volume)
- Integration with K3s pod auto-scaling
- Unified TLS proxy (Caddy or Nginx)
- Central logging via /shared/config/state/logs/
- OAuth / SSO (AzureAD) bridge