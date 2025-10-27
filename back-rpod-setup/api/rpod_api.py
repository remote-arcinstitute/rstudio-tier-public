#!/usr/bin/env python3
# File: back-rpod-setup/api/rpod_api.py
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import yaml
import logging
import json
import requests_unixsocket
import time
import threading
from typing import Dict, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("rpod_api")

# ── Podman socket resolution (rootless-first) ───────────────────────────────────
def resolve_podman_url() -> str:
    # Respect explicit override
    env_url = os.getenv("PODMAN_URL")
    if env_url:
        return env_url

    # Allow the host's rootless UID to be injected when container runs as root
    uid_str = os.getenv("PODMAN_ROOTLESS_UID")
    if uid_str and uid_str.isdigit():
        p = f"/run/user/{uid_str}/podman/podman.sock"
        if os.path.exists(p):
            return "http+unix://" + requests_unixsocket.quoting.quote(p, safe="")

    # XDG_RUNTIME_DIR is reliable on host sessions
    xdg = os.getenv("XDG_RUNTIME_DIR")
    if xdg:
        p = os.path.join(xdg, "podman/podman.sock")
        if os.path.exists(p):
            return "http+unix://" + requests_unixsocket.quoting.quote(p, safe="")

    # Try current process UID (works when API runs as the same user)
    uid = os.getuid()
    p = f"/run/user/{uid}/podman/podman.sock"
    if os.path.exists(p):
        return "http+unix://" + requests_unixsocket.quoting.quote(p, safe="")

    # Rootful fallback
    return "http+unix://" + requests_unixsocket.quoting.quote("/run/podman/podman.sock", safe="")

app = FastAPI(title="RPOD Backend API")
session = requests_unixsocket.Session()
PODMAN_URL = resolve_podman_url()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

ROOT = os.getenv("ROOT_PATH", "/app")
MOCK = os.getenv("MOCK_PATH", "/home/arcinstitute/mockdir")
CONFIG = os.getenv("USERS_FILE", "/app/config/users.yaml")
CONTAINER_ENGINE = os.getenv("CONTAINER_ENGINE", "podman")
HOST_IP = os.getenv("HOST_IP", "100.65.42.6")
IMAGE_NAME = os.getenv("IMAGE_NAME", "rstudio-tier")
TIER_PORTS = {"tier1": 8810, "tier2": 8820, "tier3": 8830}

logger.info("Backend starting with config:")
for k, v in {
    "ROOT": ROOT, "MOCK": MOCK, "CONFIG": CONFIG, "ENGINE": CONTAINER_ENGINE,
    "HOST_IP": HOST_IP, "IMAGE_NAME": IMAGE_NAME, "PODMAN_URL": PODMAN_URL
}.items():
    logger.info(f"  {k}: {v}")

@app.get("/")
def root():
    return {"service": "RPOD Backend API", "status": "running", "engine": CONTAINER_ENGINE, "config": CONFIG, "podman_url": PODMAN_URL}

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "engine": CONTAINER_ENGINE,
        "config_exists": os.path.exists(CONFIG),
        "mock_exists": os.path.exists(MOCK),
        "config_path": CONFIG,
        "mock_path": MOCK,
        "podman_url": PODMAN_URL,
    }

@app.get("/podman/version")
def podman_version():
    try:
        r = session.get(f"{PODMAN_URL}/v4.0.0/libpod/version")
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Podman version error: {e}")

def load_users() -> Dict[str, Dict]:
    try:
        with open(CONFIG) as f:
            data = yaml.safe_load(f) or {}
        users = data.get("users", data) or {}
        logger.info(f"Loaded {len(users)} users: {list(users.keys())}")
        return users
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"Config file not found: {CONFIG}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config error: {e}")

@app.get("/users")
def list_users():
    users = load_users()
    return {"users": list(users.keys()), "count": len(users)}

# ── Helpers ─────────────────────────────────────────────────────────────────────
def ensure_user_home(path: str):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create user home: {path} ({e})")

def validate_required_paths(paths: List[str]):
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing host path(s): {', '.join(missing)}")

def bind_mount(source: str, destination: str, read_only: bool) -> Dict:
    # Why: ensure read-only where intended; avoid accidental writes to shared dirs
    opts = ["rbind"]
    if read_only:
        opts.append("ro")
    return {"type": "bind", "source": source, "destination": destination, "options": opts}

def build_podman_spec(image: str, name: str, env: Dict[str, str], mounts: List[Dict], port: int) -> Dict:
    # IMPORTANT: omit netns completely; rootless defaults to slirp automatically
    return {
        "image": image,
        "name": name,
        "env": env,
        "remove": True,
        "mounts": mounts,
        "portmappings": [
            {
                "container_port": 8787,
                "host_port": port,
                "host_ip": "",   # default 0.0.0.0
                "protocol": "tcp",
                "range": 1
            }
        ],
    }

def podman_delete_if_exists(name: str, delay_seconds: int = 7200):
    try:
        inspect_url = f"{PODMAN_URL}/v4.0.0/libpod/containers/{name}/json"
        r = session.get(inspect_url)
        if r.status_code == 404:
            return
        info = r.json()
        state = info.get("State", {}).get("Status", "unknown")
        if state == "running":
            logger.info(f"Container {name} running; cleanup in {delay_seconds//60} min.")
            threading.Timer(delay_seconds, podman_delete_if_stopped, args=[name]).start()
            return
        logger.info(f"Removing stopped container: {name}")
        del_url = f"{PODMAN_URL}/v4.0.0/libpod/containers/{name}?force=true"
        session.delete(del_url)
    except Exception as e:
        logger.warning(f"Cleanup scheduling failed for {name}: {e}")

def podman_delete_if_stopped(name: str):
    try:
        inspect_url = f"{PODMAN_URL}/v4.0.0/libpod/containers/{name}/json"
        r = session.get(inspect_url)
        if r.status_code == 404:
            return
        state = r.json().get("State", {}).get("Status", "unknown")
        if state != "running":
            logger.info(f"Delayed cleanup: removing {name}")
            del_url = f"{PODMAN_URL}/v4.0.0/libpod/containers/{name}?force=true"
            session.delete(del_url)
    except Exception as e:
        logger.warning(f"Delayed cleanup failed for {name}: {e}")

def container_exists_and_running(name: str) -> bool:
    try:
        r = session.get(f"{PODMAN_URL}/v4.0.0/libpod/containers/{name}/json")
        if r.status_code == 404:
            return False
        return r.json().get("State", {}).get("Status", "unknown") == "running"
    except Exception:
        return False

def podman_create_and_start(spec: Dict) -> str:
    create_url = f"{PODMAN_URL}/v4.0.0/libpod/containers/create"
    r = session.post(create_url, json=spec)
    if r.status_code == 500 and "already in use" in r.text:
        name = spec.get("name", "<unnamed>")
        logger.warning(f"Name in use; scheduling delete: {name}")
        podman_delete_if_exists(name)
        time.sleep(2)
        r = session.post(create_url, json=spec)

    if r.status_code not in (200, 201):
        logger.error(f"Podman create error ({r.status_code}): {r.text}")
    r.raise_for_status()

    cid = r.json()["Id"]
    start_url = f"{PODMAN_URL}/v4.0.0/libpod/containers/{cid}/start"
    r = session.post(start_url)
    if r.status_code != 204:
        logger.error(f"Podman start error ({r.status_code}): {r.text}")
    r.raise_for_status()
    return cid

# ── Endpoints ───────────────────────────────────────────────────────────────────
@app.post("/launch")
def launch(username: str = Form(...), resource: str = Form("rstudio")):
    logger.info(f"Launch request for user={username}, resource={resource}")
    users = load_users()
    user = users.get(username)
    if not user:
        return JSONResponse({"ok": False, "error": f"User '{username}' not found"}, status_code=404)

    tier = user.get("tier", "tier1")
    port = TIER_PORTS.get(tier, 8810)
    user_home = user.get("home", f"/home/{username}")
    password = user.get("password", "arc_default_123")
    cname = f"rstudio-{username}"
    logger.info(f"User config: tier={tier}, port={port}, home={user_home}")

    src_project_center = os.path.join(MOCK, "Project Center")
    src_user_home = os.path.join(MOCK, "user_home", username)
    src_shared_rlib = os.path.join(MOCK, "shared-r-library")

    ensure_user_home(src_user_home)
    validate_required_paths([src_project_center, src_shared_rlib])

    mounts = [
        bind_mount(src_project_center, "/mockdir/Project Center", True),
        bind_mount(src_user_home, user_home, False),
        bind_mount(src_shared_rlib, "/usr/local/lib/R/site-library", True),
    ]

    env_vars = {"USER": username, "PASSWORD": password, "TIER": tier, "HOME": user_home}
    spec = build_podman_spec(image=f"localhost/{IMAGE_NAME}", name=cname, env=env_vars, mounts=mounts, port=port)

    try:
        logger.debug(f"Podman Spec:\n{json.dumps(spec, indent=2)}")
        cid = podman_create_and_start(spec)
        logger.info(f"Container started: {cid}")
        time.sleep(1)
        return JSONResponse({
            "ok": True,
            "redirect_url": f"http://{HOST_IP}:{port}",
            "tier": tier,
            "username": username,
            "container": cname,
            "port": port,
            "reuse": True
        })
    except HTTPException as he:
        return JSONResponse({"ok": False, "error": he.detail}, status_code=he.status_code)
    except Exception as e:
        logger.exception("Container launch failed via Podman API")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.post("/stop")
def stop_container(username: str = Form(...)):
    cname = f"rstudio-{username}"
    logger.info(f"Stopping container: {cname}")
    try:
        session.post(f"{PODMAN_URL}/v4.0.0/libpod/containers/{cname}/stop")
        podman_delete_if_exists(cname)
        return {"ok": True, "message": f"Container {cname} stopped and scheduled for removal"}
    except Exception as e:
        logger.error(f"Failed to stop container: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/status/{username}")
def check_status(username: str):
    cname = f"rstudio-{username}"
    try:
        ps_url = f'{PODMAN_URL}/v4.0.0/libpod/containers/json?filters={{"name":["{cname}"]}}'
        r = session.get(ps_url)
        data = r.json()
        running = len(data) > 0
        return {"username": username, "running": running, "container": cname}
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {"username": username, "running": False, "error": str(e)}
