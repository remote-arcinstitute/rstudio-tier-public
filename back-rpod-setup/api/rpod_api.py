from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse
import subprocess, os, yaml

app = FastAPI()
ROOT = os.path.expanduser("~/rstudio-tier-setup/back-rpod-setup")
MOCK = os.path.expanduser("~/rstudio-tier-setup/shared/mockdir")
CONFIG = os.path.expanduser("~/rstudio-tier-setup/front-arc-login/config/users.yaml")

TIER_PORTS = {"tier1": 8810, "tier2": 8820, "tier3": 8830}

@app.post("/launch")
def launch(username: str = Form(...), resource: str = Form("rstudio")):
    with open(CONFIG) as f:
        users = yaml.safe_load(f)
    u = users.get(username)
    if not u:
        return JSONResponse({"ok": False, "error": f"user '{username}' not found"}, status_code=404)

    tier = u.get("tier", "tier1")
    port = TIER_PORTS.get(tier, 8810)
    cname = f"rstudio-{username}"
    image = "rstudio-tier"

    subprocess.run(["podman", "rm", "-f", cname], stdout=subprocess.DEVNULL)
    cmd = [
        "podman", "run", "-d", "--name", cname,
        "-p", f"{port}:8787",
        "-v", f"{ROOT}/01_build/mock_users.txt:/etc/rstudio/users.txt:ro",
        "-v", f"{ROOT}/01_build/tier_limits.conf:/etc/rstudio/tier_limits.conf:ro",
        "-v", f"{ROOT}/02_run:/var/lib/rstudio",
        "-v", f"{MOCK}/shared-r-library:/usr/local/lib/R/site-library:ro",
        "-v", f"{MOCK}/Project Center:/mockdir/Project Center:ro",
        "-v", f"{MOCK}/user_home:/home:rw",
        image
    ]
    subprocess.run(cmd, check=True)
    redirect_url = f"http://100.65.42.6:{port}"
    return JSONResponse({"ok": True, "redirect_url": redirect_url, "tier": tier, "username": username})
