from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests
import os
import yaml
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:6124")
USERS_FILE = os.getenv("USERS_FILE", "/app/config/users.yaml")

app = FastAPI(title="ARC Login Frontend")

# Mount static files
app.mount("/static", StaticFiles(directory="/app/static"), name="static")

def load_users():
    """Load users from YAML file"""
    try:
        with open(USERS_FILE) as f:
            data = yaml.safe_load(f)
            return data.get("users", data)
    except Exception as e:
        logger.error(f"Error loading users: {e}")
        return {}

# Health check
@app.get("/health")
def health():
    return {"status": "healthy", "backend": BACKEND_URL}

# Serve homepage
@app.get("/")
def root():
    return FileResponse("/app/static/index.html")

# Route form submission
@app.post("/route")
async def route_user(username: str = Form(...), resource: str = Form("rstudio")):
    logger.info(f"Login attempt: user={username}, resource={resource}")
    
    try:
        # Validate username locally first
        users = load_users()
        if not users:
            return HTMLResponse(
                "<h2>Configuration Error: Cannot load users.yaml</h2>",
                status_code=500
            )
        
        if username not in users:
            logger.warning(f"User not found: {username}")
            return HTMLResponse(
                f"<h2>User '{username}' not found</h2>",
                status_code=400
            )
        
        # Forward to backend /launch
        logger.info(f"Forwarding to backend: {BACKEND_URL}/launch")
        
        try:
            r = requests.post(
                f"{BACKEND_URL}/launch",
                data={"username": username, "resource": resource},
                timeout=30
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Backend connection error: {e}")
            return HTMLResponse(
                f"<h2>Backend not available</h2><p>Could not connect to {BACKEND_URL}</p>",
                status_code=503
            )
        except requests.exceptions.Timeout:
            logger.error("Backend timeout")
            return HTMLResponse(
                "<h2>Backend timeout</h2><p>Request took too long</p>",
                status_code=504
            )
        
        # Handle backend response
        if r.status_code != 200:
            logger.error(f"Backend error: {r.status_code} - {r.text}")
            return HTMLResponse(
                f"<h2>Backend error ({r.status_code})</h2><pre>{r.text}</pre>",
                status_code=500
            )
        
        data = r.json()
        if data.get("ok"):
            logger.info(f"Success! Redirecting to: {data['redirect_url']}")
            return RedirectResponse(url=data["redirect_url"], status_code=303)
        
        error_msg = data.get("error", "Unknown error")
        logger.error(f"Backend returned error: {error_msg}")
        return HTMLResponse(
            f"<h2>Launch failed</h2><p>{error_msg}</p>",
            status_code=400
        )
        
    except Exception as e:
        logger.exception("Unexpected error in route_user")
        return HTMLResponse(
            f"<h2>Unexpected error</h2><pre>{str(e)}</pre>",
            status_code=500
        )

# List available users (for debugging)
@app.get("/users")
def list_users():
    users = load_users()
    return {"users": list(users.keys())}