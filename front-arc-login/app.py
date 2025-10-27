from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import requests, os

# URL of backend API
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:6124")

app = FastAPI()
app.mount("/static", StaticFiles(directory="/app/static"), name="static")

@app.get("/")
def root():
    return FileResponse("/app/static/index.html")

@app.post("/route")
def route_user(username: str = Form(...), resource: str = Form("rstudio")):
    try:
        r = requests.post(f"{BACKEND_URL}/launch", data={"username": username, "resource": resource})
        if r.status_code != 200:
            return HTMLResponse(f"<h2>Backend error: {r.text}</h2>", status_code=500)
        data = r.json()
        if data.get("ok"):
            return RedirectResponse(url=data["redirect_url"])
        return HTMLResponse(f"<h2>{data.get('error')}</h2>", status_code=400)
    except Exception as e:
        return HTMLResponse(f"<h2>Backend connection failed: {e}</h2>", status_code=500)
