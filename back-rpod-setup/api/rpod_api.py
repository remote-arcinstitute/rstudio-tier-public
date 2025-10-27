# ─────────────────────────────────────────────
# File: back-rpod-setup/api/rpod_api.py
# ─────────────────────────────────────────────
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import yaml
import logging
import json
import requests_unixsocket
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="RPOD Backend API")

# ─────────────────────────────────────────────
# [CHANGED] Use Podman REST API via socket
# ─────────────────────────────────────────────
session = requests_unixsocket.Session()
PODMAN_URL = os.getenv("PODMAN_URL", "http+unix://%2Frun%2Fpodman%2Fpodman.sock")

# CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration defaults
ROOT = os.getenv("ROOT_PATH", "/app")
MOCK = os.getenv("MOCK_PATH", "/home/arcinstitute/mockdir")
CONFIG = os.getenv("USERS_FILE", "/app/config/users.yaml")
CONTAINER_ENGINE = os.getenv("CONTAINER_ENGINE", "podman")
HOST_IP = os.getenv("HOST_IP", "100.65.42.6")
IMAGE_NAME = os.getenv("IMAGE_NAME", "rstudio-tier")

# Tier-port mapping
TIER_PORTS = {
    "tier1": 8810,
    "tier2": 8820,
    "tier3": 8830
}

logger.info("Backend starting with config:")
logger.info(f"  ROOT: {ROOT}")
logger.info(f"  MOCK: {MOCK}")
logger.info(f"  CONFIG: {CONFIG}")
logger.info(f"  ENGINE: {CONTAINER_ENGINE}")
logger.info(f"  HOST_IP: {HOST_IP}")
logger.info(f"  IMAGE_NAME: {IMAGE_NAME}")

@app.get("/")
def root():
    return {
        "service": "RPOD Backend API",
        "status": "running",
        "engine": CONTAINER_ENGINE,
        "config": CONFIG
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    config_exists = os.path.exists(CONFIG)
    mock_exists = os.path.exists(MOCK)
    return {
        "status": "healthy",
        "engine": CONTAINER_ENGINE,
        "config_exists": config_exists,
        "mock_exists": mock_exists,
        "config_path": CONFIG,
        "mock_path": MOCK
    }

def load_users():
    """Load users from config file"""
    try:
        logger.info(f"Loading users from: {CONFIG}")
        with open(CONFIG) as f:
            data = yaml.safe_load(f)
            users = data.get("users", data)
            logger.info(f"Loaded {len(users)} users: {list(users.keys())}")
            return users
    except FileNotFoundError:
        logger.error(f"Config file not found: {CONFIG}")
        raise HTTPException(status_code=500, detail=f"Config file not found: {CONFIG}")
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        raise HTTPException(status_code=500, detail=f"Config error: {e}")

@app.get("/users")
def list_users():
    """List all configured users"""
    users = load_users()
    return {"users": list(users.keys()), "count": len(users)}

# ─────────────────────────────────────────────
# [CHANGED] New Podman helper using REST API
# ─────────────────────────────────────────────
def podman_create_and_start(payload):
    """Create and start container via Podman REST API"""
    create_url = f"{PODMAN_URL}/v4.0.0/libpod/containers/create"
    r = session.post(create_url, json=payload)
    r.raise_for_status()
    container_id = r.json()["Id"]

    start_url = f"{PODMAN_URL}/v4.0.0/libpod/containers/{container_id}/start"
    r = session.post(start_url)
    r.raise_for_status()
    return container_id

@app.post("/launch")
def launch(username: str = Form(...), resource: str = Form("rstudio")):
    """Launch RStudio container for user"""
    logger.info(f"Launch request for user: {username}, resource: {resource}")

    users = load_users()
    user = users.get(username)

    if not user:
        logger.warning(f"User not found: {username}")
        return JSONResponse({"ok": False, "error": f"User '{username}' not found"}, status_code=404)

    tier = user.get("tier", "tier1")
    port = TIER_PORTS.get(tier, 8810)
    user_home = user.get("home", f"/home/{username}")
    cname = f"rstudio-{username}"

    logger.info(f"User config: tier={tier}, port={port}, home={user_home}")

    # ─────────────────────────────────────────────
    # [CHANGED] Replace subprocess with REST payload
    # ─────────────────────────────────────────────
    try:
        payload = {
            "image": IMAGE_NAME,
            "name": cname,
            "env": [
                f"USER={username}",
                f"USERID={os.getuid()}",
                f"TIER={tier}"
            ],
            "portmappings": [{"host_port": port, "container_port": 8787}],
            "mounts": [
                {
                    "source": f"{MOCK}/Project Center",
                    "destination": "/mockdir/Project Center",
                    "options": ["ro"]
                },
                {
                    "source": f"{MOCK}/user_home/{username}",
                    "destination": f"{user_home}",
                    "options": ["rw"]
                },
                {
                    "source": f"{MOCK}/shared-r-library",
                    "destination": "/usr/local/lib/R/site-library",
                    "options": ["ro"]
                }
            ]
        }

        container_id = podman_create_and_start(payload)
        logger.info(f"Container created and started: {container_id}")

        time.sleep(2)  # wait briefly for RStudio to start
        redirect_url = f"http://{HOST_IP}:{port}"

        return JSONResponse({
            "ok": True,
            "redirect_url": redirect_url,
            "tier": tier,
            "username": username,
            "container": cname,
            "port": port
        })

    except Exception as e:
        logger.exception("Container launch failed via Podman API")
        return JSONResponse({"ok": False, "error": f"Podman API error: {str(e)}"}, status_code=500)

@app.post("/stop")
def stop_container(username: str = Form(...)):
    """Stop user's RStudio container"""
    cname = f"rstudio-{username}"
    logger.info(f"Stopping container: {cname}")
    try:
        stop_url = f"{PODMAN_URL}/v4.0.0/libpod/containers/{cname}/stop"
        session.post(stop_url)
        return {"ok": True, "message": f"Container {cname} stopped"}
    except Exception as e:
        logger.error(f"Failed to stop container: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/status/{username}")
def check_status(username: str):
    """Check if user's container is running"""
    cname = f"rstudio-{username}"
    try:
        ps_url = f"{PODMAN_URL}/v4.0.0/libpod/containers/json?filters={{\"name\":[\"{cname}\"]}}"
        r = session.get(ps_url)
        data = r.json()
        is_running = len(data) > 0
        return {"username": username, "running": is_running, "container": cname}
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {"username": username, "running": False, "error": str(e)}
