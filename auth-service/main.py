import os
import uuid
import random
import httpx
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

app = FastAPI(title="Auth POC")

# ---------------------------------------------------------------------------
# JupyterHub integration config
# ---------------------------------------------------------------------------

# Internal URL uses the Docker container name, not localhost — both containers
# share jupyterhub-network, so DNS resolves "jupyter-hub" directly.
HUB_API_INTERNAL = os.getenv("HUB_API_INTERNAL", "http://jupyter-hub:8000/hub/api")

# Public URL is what the browser opens — must be reachable from the client machine.
HUB_PUBLIC_URL = os.getenv("HUB_PUBLIC_URL", "http://localhost:8000")

# Admin token defined in .env and registered in jupyterhub_config.py under
# c.JupyterHub.api_tokens. Without it every hub API call returns 403.
JUPYTERHUB_API_TOKEN = os.getenv("JUPYTERHUB_API_TOKEN", "")

# ---------------------------------------------------------------------------
# Users — POC only, no hashing, no database
# ---------------------------------------------------------------------------

USERS = {
    "sales@company.com":       {"password": "sales123",       "role": "sales"},
    "paul@company.com":       {"password": "paul123",       "role": "sales"},
    "marketing@company.com":   {"password": "marketing123",   "role": "marketing"},
    "collections@company.com": {"password": "collections123", "role": "collections"},
}

# Token → email map. Lives in memory — resets on container restart (POC only).
SESSIONS: dict[str, str] = {}


def _email_to_username(email: str) -> str:
    # JupyterHub usernames must not contain @ or dots.
    # sales@company.com → sales_company_com
    return email.replace("@", "_").replace(".", "_")

# ---------------------------------------------------------------------------
# Fake Big Data tables — 100 rows each, generated once at startup
# ---------------------------------------------------------------------------

def _name():
    first = random.choice(["James","Emily","Michael","Sarah","David","Jessica","Robert","Ashley","John","Amanda"])
    last  = random.choice(["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Wilson","Moore"])
    return f"{first} {last}"

# sales role — credit risk assessment data
RISK = [
    {
        "user_id": i + 1,
        "name": _name(),
        "risk_score": round(random.uniform(0, 100), 2),
        "risk_level": random.choice(["low", "medium", "high"]),
    }
    for i in range(100)
]

# marketing role — fraud incident data
FRAUD = [
    {
        "user_id": i + 1,
        "name": _name(),
        "fraud_type": random.choice(["cloned_card", "phishing", "identity_theft", "unauthorized_transaction"]),
        "amount": round(random.uniform(100, 50000), 2),
        "date": f"2024-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
    }
    for i in range(100)
]

# collections role — outstanding debt data
AVERAGE_DEBT = [
    {
        "user_id": i + 1,
        "name": _name(),
        "total_debt": round(random.uniform(500, 200000), 2),
        "overdue_months": random.randint(0, 36),
    }
    for i in range(100)
]

# Maps each role to the table(s) it can see — enforced in /dashboard
ROLE_TABLES = {
    "sales":       {"risk": RISK},
    "marketing":   {"fraud": FRAUD},
    "collections": {"average_debt": AVERAGE_DEBT},
}

# ---------------------------------------------------------------------------
# JupyterHub Admin API helpers
# ---------------------------------------------------------------------------

def _hub_headers() -> dict:
    return {"Authorization": f"token {JUPYTERHUB_API_TOKEN}"}

def _launch_notebook(username: str, auth_service_token: str) -> str:
    try:
        with httpx.Client(base_url=HUB_API_INTERNAL, headers=_hub_headers(), timeout=30) as hub:

            # 201 = created, 409 = user already exists — both are fine
            r = hub.post(f"/users/{username}")
            if r.status_code not in (201, 409):
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")

            # Pass the auth token as a spawn option — pre_spawn_hook reads spawner.user_options
            # and injects it as AUTH_SERVICE_TOKEN in the container environment.
            # 201 = started, 202 = starting (async), 400 = already running
            r = hub.post(f"/users/{username}/server", json={
                "AUTH_SERVICE_TOKEN": auth_service_token,
            })
            if r.status_code not in (201, 202, 400):
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")

            # /hub/token-login validates this token server-side and sets the session cookie.
            r = hub.post(f"/users/{username}/tokens")
            if r.status_code != 201:
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")
            user_token = r.json()["token"]

    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Cannot reach JupyterHub")

    next_path = quote(f"/user/{username}/", safe="")
    return f"{HUB_PUBLIC_URL}/hub/token-login?token={user_token}&next={next_path}"

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/auth/login")
def login(body: LoginRequest):
    user = USERS.get(body.email)
    if not user or user["password"] != body.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = str(uuid.uuid4())
    SESSIONS[token] = body.email
    return {"token": token, "role": user["role"]}

@app.get("/dashboard")
def dashboard(authorization: str = Header(...)):
    token = authorization.removeprefix("Bearer ").strip()
    email = SESSIONS.get(token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    role = USERS[email]["role"]
    return {"role": role, "tables": ROLE_TABLES[role]}

@app.post("/auth/jupyter-launch")
def jupyter_launch(authorization: str = Header(...)):
    token = authorization.removeprefix("Bearer ").strip()
    email = SESSIONS.get(token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    username = _email_to_username(email)
    url = _launch_notebook(username, auth_service_token=token)
    return {"url": url, "username": username}

@app.get("/health")
def health():
    return {"status": "ok"}
