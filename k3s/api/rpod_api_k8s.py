#!/usr/bin/env python3
# ─────────────────────────────────────────────
# File: k3s/api/rpod_api_k8s.py
# Purpose: K8s-native API for launching RStudio pods (one pod per user)
# ─────────────────────────────────────────────
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import os
import yaml
import logging
from typing import Dict, Optional, List
from datetime import datetime, timezone
import threading
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("rpod_api_k8s")

# ── K8s Configuration ───────────────────────────────────────────────────────────
try:
    config.load_incluster_config()  # Running inside k8s
    logger.info("Loaded in-cluster k8s config")
except:
    config.load_kube_config()  # Running locally
    logger.info("Loaded local kubeconfig")

v1 = client.CoreV1Api()

# ── Environment Configuration ───────────────────────────────────────────────────
NAMESPACE = os.getenv("K8S_NAMESPACE", "default")
CONFIG_FILE = os.getenv("USERS_FILE", "/app/config/users.yaml")
IMAGE_NAME = os.getenv("IMAGE_NAME", "localhost/rstudio-tier:latest")
NODE_IP = os.getenv("NODE_IP", "100.64.0.7")

# NodePort range for RStudio instances
NODEPORT_START = 30810
NODEPORT_END = 30900

# Session limits (in seconds)
MAX_SESSION_DURATION = 12 * 60 * 60  # 12 hours
SESSION_CHECK_INTERVAL = 60 * 60  # Check every 1 hour

# Tier resource limits
TIER_LIMITS = {
    "tier1": {"cpu_request": "1000m", "cpu_limit": "2000m", "mem_request": "2Gi", "mem_limit": "4Gi"},
    "tier2": {"cpu_request": "2000m", "cpu_limit": "4000m", "mem_request": "4Gi", "mem_limit": "8Gi"},
    "tier3": {"cpu_request": "4000m", "cpu_limit": "8000m", "mem_request": "8Gi", "mem_limit": "16Gi"},
}

# Storage paths on host
PROJECT_CENTER_PATH = "/opt/project_center_mirror"
USER_HOMES_PATH = "/opt/user_homes"
SHARED_RLIB_PATH = "/opt/shared-r-library"

logger.info("K8s API starting with config:")
for k, v in {
    "NAMESPACE": NAMESPACE,
    "CONFIG_FILE": CONFIG_FILE,
    "IMAGE_NAME": IMAGE_NAME,
    "NODE_IP": NODE_IP,
    "NODEPORT_RANGE": f"{NODEPORT_START}-{NODEPORT_END}",
    "MAX_SESSION_HOURS": MAX_SESSION_DURATION / 3600,
}.items():
    logger.info(f"  {k}: {v}")

# ── FastAPI Setup ───────────────────────────────────────────────────────────────
app = FastAPI(title="RPOD K8s Backend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Session Management ──────────────────────────────────────────────────────────
def get_pod_age_seconds(pod) -> float:
    """Calculate pod age in seconds"""
    if not pod.status.start_time:
        return 0
    now = datetime.now(timezone.utc)
    start_time = pod.status.start_time
    age = (now - start_time).total_seconds()
    return age

def cleanup_old_sessions():
    """Background task to cleanup sessions older than MAX_SESSION_DURATION"""
    while True:
        try:
            logger.info("Checking for old sessions...")
            pods = v1.list_namespaced_pod(
                namespace=NAMESPACE,
                label_selector="app=rstudio"
            )
            
            for pod in pods.items:
                age = get_pod_age_seconds(pod)
                username = pod.metadata.labels.get("user", "unknown")
                
                if age > MAX_SESSION_DURATION:
                    logger.warning(f"Session timeout: {pod.metadata.name} (user={username}, age={age/3600:.1f}h)")
                    try:
                        # Delete pod
                        v1.delete_namespaced_pod(
                            name=pod.metadata.name,
                            namespace=NAMESPACE,
                            body=client.V1DeleteOptions()
                        )
                        # Delete service
                        svc_name = f"rstudio-svc-{username}"
                        v1.delete_namespaced_service(name=svc_name, namespace=NAMESPACE)
                        logger.info(f"Cleaned up session for {username} (exceeded {MAX_SESSION_DURATION/3600}h limit)")
                    except Exception as e:
                        logger.error(f"Failed to cleanup {pod.metadata.name}: {e}")
                elif age > MAX_SESSION_DURATION - 1800:  # 30 min warning
                    remaining = (MAX_SESSION_DURATION - age) / 60
                    logger.info(f"Session warning: {username} has {remaining:.0f} minutes remaining")
                    
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")
        
        time.sleep(SESSION_CHECK_INTERVAL)

# Start background cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_sessions, daemon=True)
cleanup_thread.start()
logger.info(f"Started session cleanup thread (checking every {SESSION_CHECK_INTERVAL/3600:.1f}h)")

# ── Helper Functions ────────────────────────────────────────────────────────────
def load_users() -> Dict[str, Dict]:
    try:
        with open(CONFIG_FILE) as f:
            data = yaml.safe_load(f) or {}
        users = data.get("users", data) or {}
        logger.info(f"Loaded {len(users)} users: {list(users.keys())}")
        return users
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"Config file not found: {CONFIG_FILE}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config error: {e}")

def get_pod_name(username: str) -> str:
    return f"rstudio-{username}"

def get_service_name(username: str) -> str:
    return f"rstudio-svc-{username}"

def get_used_nodeports() -> List[int]:
    """Get list of all NodePorts currently in use"""
    try:
        services = v1.list_namespaced_service(namespace=NAMESPACE)
        ports = []
        for svc in services.items:
            if svc.spec.type == "NodePort":
                for port in svc.spec.ports:
                    if port.node_port:
                        ports.append(port.node_port)
        return ports
    except ApiException as e:
        logger.error(f"Failed to list services: {e}")
        return []

def allocate_nodeport() -> int:
    """Find next available NodePort"""
    used_ports = set(get_used_nodeports())
    for port in range(NODEPORT_START, NODEPORT_END + 1):
        if port not in used_ports:
            return port
    raise HTTPException(status_code=507, detail="No available NodePorts")

def get_user_nodeport(username: str) -> Optional[int]:
    """Get existing NodePort for user's service"""
    svc_name = get_service_name(username)
    try:
        svc = v1.read_namespaced_service(name=svc_name, namespace=NAMESPACE)
        if svc.spec.type == "NodePort" and svc.spec.ports:
            return svc.spec.ports[0].node_port
    except ApiException as e:
        if e.status == 404:
            return None
        raise
    return None

def pod_exists(username: str) -> Optional[Dict]:
    """Check if pod exists and return its status"""
    pod_name = get_pod_name(username)
    try:
        pod = v1.read_namespaced_pod(name=pod_name, namespace=NAMESPACE)
        age = get_pod_age_seconds(pod)
        return {
            "exists": True,
            "phase": pod.status.phase,
            "pod_ip": pod.status.pod_ip,
            "age_seconds": age,
            "age_hours": age / 3600,
        }
    except ApiException as e:
        if e.status == 404:
            return {"exists": False}
        raise

def build_project_volumes_and_mounts(projects: List[Dict]) -> tuple:
    """
    Build volume and volumeMount lists for user's project folders.
    Returns: (volumes, volume_mounts)
    """
    volumes = []
    volume_mounts = []
    
    for idx, project in enumerate(projects):
        base = project.get("base", "")
        folders = project.get("folders", [])
        
        if not base or not folders:
            continue
            
        # Sanitize base name for k8s resource naming (lowercase, no spaces)
        base_safe = base.lower().replace(" ", "-").replace(".", "")
        
        for folder in folders:
            # Host path: /opt/project_center_mirror/{base}/{folder}
            host_path = os.path.join(PROJECT_CENTER_PATH, base, folder)
            
            # Volume name must be DNS-1123 compliant
            volume_name = f"proj-{base_safe}-{idx}-{folder.replace(' ', '-').replace('.', '-').lower()}"
            
            # Mount path: /project-center/{base}/{folder}
            mount_path = os.path.join("/project-center", base, folder)
            
            volumes.append(
                client.V1Volume(
                    name=volume_name,
                    host_path=client.V1HostPathVolumeSource(
                        path=host_path,
                        type="Directory",
                    ),
                )
            )
            
            volume_mounts.append(
                client.V1VolumeMount(
                    name=volume_name,
                    mount_path=mount_path,
                    read_only=False,  # Read-write access
                )
            )
            
            logger.debug(f"  Volume: {volume_name} -> {host_path} mounted at {mount_path} (RW)")
    
    return volumes, volume_mounts

def create_pod(username: str, password: str, tier: str, user_home: str, projects: List[Dict]) -> str:
    """Create RStudio pod for user with tier-based resource limits and project mounts"""
    pod_name = get_pod_name(username)
    
    # Get tier limits
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["tier1"])
    logger.info(f"Creating pod with limits: {limits}")
    
    # Build project-specific volumes and mounts
    project_volumes, project_mounts = build_project_volumes_and_mounts(projects)
    logger.info(f"Created {len(project_volumes)} project volume mounts for {username}")
    
    # Base volumes (user home + shared R lib)
    base_volumes = [
        client.V1Volume(
            name="user-home",
            host_path=client.V1HostPathVolumeSource(
                path=f"{USER_HOMES_PATH}/{username}",
                type="DirectoryOrCreate",
            ),
        ),
        client.V1Volume(
            name="shared-rlib",
            host_path=client.V1HostPathVolumeSource(
                path=SHARED_RLIB_PATH,
                type="Directory",
            ),
        ),
    ]
    
    # Base mounts
    base_mounts = [
        client.V1VolumeMount(
            name="user-home",
            mount_path=user_home,
            read_only=False,
        ),
        client.V1VolumeMount(
            name="shared-rlib",
            mount_path="/usr/local/lib/R/site-library",
            read_only=True,
        ),
    ]
    
    # Combine base + project volumes/mounts
    all_volumes = base_volumes + project_volumes
    all_mounts = base_mounts + project_mounts
    
    # Pod specification
    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=pod_name,
            labels={
                "app": "rstudio",
                "user": username,
                "tier": tier,
            }
        ),
        spec=client.V1PodSpec(
            node_selector={"kubernetes.io/hostname": "researchpc"},  # Force to this node for testing
            containers=[
                client.V1Container(
                    name="rstudio",
                    image=IMAGE_NAME,
                    image_pull_policy="IfNotPresent",
                    ports=[client.V1ContainerPort(container_port=8787)],
                    env=[
                        client.V1EnvVar(name="USERNAME", value=username),
                        client.V1EnvVar(name="PASSWORD", value=password),
                        client.V1EnvVar(name="USER_HOME", value=user_home),
                        client.V1EnvVar(name="TIER", value=tier),
                    ],
                    volume_mounts=all_mounts,
                    resources=client.V1ResourceRequirements(
                        requests={
                            "memory": limits["mem_request"],
                            "cpu": limits["cpu_request"]
                        },
                        limits={
                            "memory": limits["mem_limit"],
                            "cpu": limits["cpu_limit"]
                        },
                    ),
                )
            ],
            volumes=all_volumes,
        ),
    )
    
    try:
        api_response = v1.create_namespaced_pod(namespace=NAMESPACE, body=pod)
        logger.info(f"Created pod: {pod_name} with tier={tier}, {len(project_volumes)} project mounts (RW)")
        return api_response.metadata.name
    except ApiException as e:
        logger.error(f"Failed to create pod: {e}")
        raise HTTPException(status_code=500, detail=f"K8s API error: {e}")

def create_service(username: str, port: int):
    """Create NodePort service for user's RStudio pod"""
    svc_name = get_service_name(username)
    
    service = client.V1Service(
        metadata=client.V1ObjectMeta(
            name=svc_name,
            labels={"app": "rstudio", "user": username},
        ),
        spec=client.V1ServiceSpec(
            type="NodePort",
            selector={"app": "rstudio", "user": username},
            ports=[
                client.V1ServicePort(
                    port=8787,
                    target_port=8787,
                    node_port=port,
                    protocol="TCP",
                )
            ],
        ),
    )
    
    try:
        api_response = v1.create_namespaced_service(namespace=NAMESPACE, body=service)
        logger.info(f"Created service: {svc_name} on NodePort {port}")
        return api_response.metadata.name
    except ApiException as e:
        if e.status == 409:  # Already exists
            logger.info(f"Service {svc_name} already exists")
            return svc_name
        logger.error(f"Failed to create service: {e}")
        raise HTTPException(status_code=500, detail=f"K8s API error: {e}")

def delete_pod(username: str):
    """Delete user's RStudio pod"""
    pod_name = get_pod_name(username)
    try:
        v1.delete_namespaced_pod(
            name=pod_name,
            namespace=NAMESPACE,
            body=client.V1DeleteOptions(),
        )
        logger.info(f"Deleted pod: {pod_name}")
    except ApiException as e:
        if e.status != 404:
            logger.error(f"Failed to delete pod: {e}")
            raise

def delete_service(username: str):
    """Delete user's NodePort service"""
    svc_name = get_service_name(username)
    try:
        v1.delete_namespaced_service(name=svc_name, namespace=NAMESPACE)
        logger.info(f"Deleted service: {svc_name}")
    except ApiException as e:
        if e.status != 404:
            logger.error(f"Failed to delete service: {e}")

# ── API Endpoints ───────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "service": "RPOD K8s Backend API",
        "status": "running",
        "namespace": NAMESPACE,
        "config": CONFIG_FILE,
        "nodeport_range": f"{NODEPORT_START}-{NODEPORT_END}",
        "max_session_hours": MAX_SESSION_DURATION / 3600,
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "namespace": NAMESPACE,
        "config_exists": os.path.exists(CONFIG_FILE),
        "k8s_connected": True,
        "max_session_hours": MAX_SESSION_DURATION / 3600,
    }

@app.get("/users")
def list_users():
    users = load_users()
    return {"users": list(users.keys()), "count": len(users)}

@app.get("/nodeports")
def list_nodeports():
    """List all allocated NodePorts"""
    used = get_used_nodeports()
    return {
        "used_ports": sorted(used),
        "available_range": f"{NODEPORT_START}-{NODEPORT_END}",
        "used_count": len(used),
    }

@app.post("/launch")
def launch(username: str = Form(...), resource: str = Form("rstudio")):
    logger.info(f"Launch request: user={username}, resource={resource}")
    
    users = load_users()
    user = users.get(username)
    if not user:
        return JSONResponse(
            {"ok": False, "error": f"User '{username}' not found"},
            status_code=404,
        )
    
    tier = user.get("tier", "tier1")
    user_home = user.get("home", f"/home/{username}")
    password = user.get("password", "default123")
    projects = user.get("projects", [])
    
    logger.info(f"User config: tier={tier}, home={user_home}, projects={len(projects)}")
    
    # Check if pod already exists
    status = pod_exists(username)
    existing_port = get_user_nodeport(username)
    
    if status["exists"]:
        if status["phase"] == "Running" and existing_port:
            age_hours = status.get("age_hours", 0)
            logger.info(f"Pod already running for {username} on port {existing_port} (age: {age_hours:.1f}h)")
            return JSONResponse({
                "ok": True,
                "redirect_url": f"http://{NODE_IP}:{existing_port}",
                "tier": tier,
                "username": username,
                "pod": get_pod_name(username),
                "port": existing_port,
                "age_hours": round(age_hours, 2),
                "reuse": True,
            })
        else:
            logger.info(f"Pod exists but not running (phase={status['phase']}), recreating...")
            delete_pod(username)
            if existing_port:
                delete_service(username)
    
    try:
        # Allocate or reuse NodePort
        port = existing_port if existing_port else allocate_nodeport()
        logger.info(f"Using NodePort: {port}")
        
        # Create pod and service
        create_pod(username, password, tier, user_home, projects)
        create_service(username, port)
        
        return JSONResponse({
            "ok": True,
            "redirect_url": f"http://{NODE_IP}:{port}",
            "tier": tier,
            "username": username,
            "pod": get_pod_name(username),
            "port": port,
            "age_hours": 0,
            "reuse": False,
        })
    except Exception as e:
        logger.exception("Failed to launch RStudio pod")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.post("/stop")
def stop_container(username: str = Form(...)):
    logger.info(f"Stop request for user: {username}")
    try:
        delete_pod(username)
        delete_service(username)
        return {"ok": True, "message": f"RStudio pod for {username} stopped"}
    except Exception as e:
        logger.error(f"Failed to stop: {e}")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.get("/status/{username}")
def check_status(username: str):
    try:
        status = pod_exists(username)
        port = get_user_nodeport(username)
        return {
            "username": username,
            "running": status["exists"] and status.get("phase") == "Running",
            "pod": get_pod_name(username),
            "phase": status.get("phase", "NotFound"),
            "port": port,
            "age_hours": round(status.get("age_hours", 0), 2) if status["exists"] else None,
        }
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {"username": username, "running": False, "error": str(e)}

@app.get("/sessions")
def list_sessions():
    """List all active RStudio sessions with age info"""
    try:
        pods = v1.list_namespaced_pod(
            namespace=NAMESPACE,
            label_selector="app=rstudio"
        )
        sessions = []
        for pod in pods.items:
            username = pod.metadata.labels.get("user", "unknown")
            age = get_pod_age_seconds(pod)
            remaining = MAX_SESSION_DURATION - age
            sessions.append({
                "username": username,
                "pod": pod.metadata.name,
                "status": pod.status.phase,
                "age_hours": round(age / 3600, 2),
                "remaining_hours": round(remaining / 3600, 2) if remaining > 0 else 0,
            })
        return {"sessions": sessions, "count": len(sessions)}
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        return {"sessions": [], "error": str(e)}
