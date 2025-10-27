# RStudio Tier Setup (ARC Institute)

Unified environment for launching multi-tier RStudio Server pods within the ARC infrastructure.

This repository contains both the **front-end login portal** and the **back-end pod orchestration layer**, designed for Ubuntu-based systems (Ubuntu 24.04 LTS).  
Each user logs in through the FastAPI front end, and their workspace pod is launched dynamically via Podman or K3s according to the assigned tier.

---

## 🧭 Structure
rstudio-tier-setup/
├── front-arc-login/ # FastAPI web interface (port 6123)
│ ├── static/ # HTML login page + logo
│ ├── app.py # Handles login & forwards to backend API
│ ├── Dockerfile # Container definition for front-end portal
│ └── config/users.yaml # User tier mapping (temporary)
│
├── back-rpod-setup/ # Pod orchestration backend (port 6124)
│ ├── api/rpod_api.py # Launch/stop API
│ ├── 01_build/ # Build scripts and tier configs
│ └── 02_run/ # Runtime storage
│
└── shared/ # Shared volumes & mock data
├── config/ # Tier limits and state
└── mockdir/ # Test data directories

---

## 🚀 Usage

### Run locally (dev mode)
```bash
# Backend API
cd back-rpod-setup
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn pyyaml python-multipart
uvicorn api.rpod_api:app --host 0.0.0.0 --port 6124
```
```bash
# Frontend portal
cd front-arc-login
uvicorn app:app --host 0.0.0.0 --port 6123
```

Then open http://localhost:6123


🧩 Dockerized deployment

Each service has its own Dockerfile.
Later, these can be unified with docker-compose.yml for automatic startup.
```bash
# Front-end build
cd front-arc-login
podman build -t arc-login .

# Backend build
cd back-rpod-setup
podman build -t arc-backend -f api/Dockerfile .
```

🧠 Tier Concept
Tier	CPU/RAM target	Example users
tier1	2 vCPU / 4 GB	Hanif
tier2	4 vCPU / 8 GB	Julian BS
tier3	8 vCPU / 16 GB	Nilakshi

🛡️ License & Credits

© 2025 ARC Institute – Infrastructure & Data Engineering Team
Developed by Julian BS & collaborators.
Licensed for internal ARC deployment only.