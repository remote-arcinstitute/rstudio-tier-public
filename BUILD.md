## Unified Build Documentation — ARC RStudio Tier Setup

**(front-arc-login + back-rpod-setup)**

---

### 🔍 Overview

This setup defines two modular FastAPI services:

| Component           | Description                                                                  | Default Port |
| ------------------- | ---------------------------------------------------------------------------- | ------------ |
| **front-arc-login** | Web login portal that validates users and forwards sessions to RStudio tiers | 6123         |
| **back-rpod-setup** | Pod controller API that launches tiered RStudio containers                   | 6124         |

```
rstudio-tier-setup/
├── front-arc-login/        → FastAPI portal
└── back-rpod-setup/        → Pod management API
```

---

### 🧩 1. Build Context and Naming

| Component   | Path                   | Dockerfile       | Image Name                   | Default Port |
| ----------- | ---------------------- | ---------------- | ---------------------------- | ------------ |
| Front Login | `front-arc-login/`     | `Dockerfile`     | `arc/rstudio-login:latest`   | 6123         |
| Backend API | `back-rpod-setup/api/` | `Dockerfile.api` | `arc/rstudio-backend:latest` | 6124         |

---

### 🧱 2. Build Each Container Manually

#### 🧱 A. Build the Front-End (Login Portal)

```bash
cd ~/rstudio-tier-setup/front-arc-login
podman build -t arc/rstudio-login:latest .
# or docker build -t arc/rstudio-login:latest .
```

Check:

```bash
podman images | grep rstudio-login
```

---

#### 🧱 B. Build the Back-End (Pod Management API)

```bash
cd ~/rstudio-tier-setup/back-rpod-setup/api
podman build -t arc/rstudio-backend:latest -f Dockerfile.api .
# or docker build -t arc/rstudio-backend:latest -f Dockerfile.api .
```

Check:

```bash
podman images | grep rstudio-backend
```

---

### 🧩 3. Unified Testing (Manual Run)

Run the **backend first**, then the **frontend**.

#### 🧩 A. Run Backend (Pod Controller)

```bash
podman run -d \
  --replace --name rpod-api \
  -p 6124:6124 \
  -v ./config:/app/config:ro \
  -v ~/mockdir:/home/arcinstitute/mockdir:rw \
  -v /run/user/$(id -u)/podman/podman.sock:/run/podman/podman.sock:rw \
  -e PODMAN_URL=http+unix://%2Frun%2Fuser%2F$(id -u)%2Fpodman%2Fpodman.sock \
  -e IMAGE_NAME=rstudio-tier \
  -e USERS_FILE=/app/config/users.yaml \
  localhost/rpod-api
```

Verify:

```bash
curl localhost:6124/health
```

Expected response:

```json
{"status": "healthy", "engine": "podman", ...}
```

---

#### 🧩 B. Run Frontend (Login Interface)

```bash
podman run -d \
  --replace --name arc-login \
  -p 6123:6123 \
  -e BACKEND_URL=http://host.containers.internal:6124 \
  -v ~/rstudio-tier-setup/front-arc-login/config:/app/config:ro \
  localhost/arc-login
```

Verify:

```bash
curl localhost:6123/health
```

Expected response:

```json
{"status": "healthy", "backend": "http://host.containers.internal:6124"}
```

Then open the login portal:
➡️ **[http://localhost:6123](http://localhost:6123)**

---

### 🧩 4. Versioning Strategy

| Tag       | Meaning                  |
| --------- | ------------------------ |
| `latest`  | Rolling dev build        |
| `YYYY.MM` | Stable monthly snapshot  |
| `vX.Y.Z`  | Semantic release version |

Example:

```bash
podman tag arc/rstudio-login:latest arc/rstudio-login:v1.0.0
podman tag arc/rstudio-backend:latest arc/rstudio-backend:v1.0.0
```

Push to internal registry:

```bash
podman push arc/rstudio-login:v1.0.0 registry.arc.local/arc/rstudio-login:v1.0.0
podman push arc/rstudio-backend:v1.0.0 registry.arc.local/arc/rstudio-backend:v1.0.0
```

---

### 🤠 5. Directory Permissions and Shared Mounts

When deploying on Ubuntu hosts (e.g., ThinkPad X270, ResearchPC, IkaPC):

| Directory                                               | Ownership               | Purpose               |
| ------------------------------------------------------- | ----------------------- | --------------------- |
| `/home/arcinstitute/rstudio-tier-setup/shared/`         | `arcinstitute:main`     | Shared configs        |
| `/home/arcinstitute/rstudio-tier-setup/shared/mockdir/` | `researchers` group     | Symlink testing       |
| `/OneDrive/Riskesdas/`                                  | External OneDrive mount | Read-only synced data |

---

### 🛠 6. Maintenance Commands

| Task             | Command                                                       |
| ---------------- | ------------------------------------------------------------- |
| Rebuild frontend | `podman build -t arc/rstudio-login .`                         |
| Rebuild backend  | `podman build -t arc/rstudio-backend -f api/Dockerfile.api .` |
| Clean all images | `podman system prune -a`                                      |
| Restart services | `podman restart rpod-api arc-login`                           |

---

### 🧩 7. Future Expansion

Planned integrations:

* Persistent per-user RStudio home volumes
* Auto-scaling via K3s deployment
* Unified TLS proxy (Caddy / Nginx)
* Centralized logging at `/shared/config/state/logs/`
* OAuth / SSO integration (Azure AD bridge)
