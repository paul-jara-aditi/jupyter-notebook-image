import os
import uuid
import random
import httpx
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

app = FastAPI(title="Auth POC")

# JupyterHub integration config
HUB_API_INTERNAL = os.getenv("HUB_API_INTERNAL", "http://jupyter-paypal:8000/hub/api")
HUB_PUBLIC_URL = os.getenv("HUB_PUBLIC_URL", "http://localhost:8000")
JUPYTERHUB_API_TOKEN = os.getenv("JUPYTERHUB_API_TOKEN", "")

# Hardcoded users — POC only, no validation
USERS = {
    "sales@company.com":       {"password": "sales123",       "role": "sales"},
    "marketing@company.com":   {"password": "marketing123",   "role": "marketing"},
    "collections@company.com": {"password": "collections123", "role": "collections"},
}

# In-memory sessions: token → role (reset on container restart)
SESSIONS: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Fake Big Data tables — 100 rows each, generated once at startup
# ---------------------------------------------------------------------------

def _name():
    first = random.choice(["James","Emily","Michael","Sarah","David","Jessica","Robert","Ashley","John","Amanda"])
    last  = random.choice(["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Wilson","Moore"])
    return f"{first} {last}"

RISK = [
    {
        "user_id": i + 1,
        "name": _name(),
        "risk_score": round(random.uniform(0, 100), 2),
        "risk_level": random.choice(["low", "medium", "high"]),
    }
    for i in range(100)
]

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

AVERAGE_DEBT = [
    {
        "user_id": i + 1,
        "name": _name(),
        "total_debt": round(random.uniform(500, 200000), 2),
        "overdue_months": random.randint(0, 36),
    }
    for i in range(100)
]

# Which tables each role can access
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

def _launch_notebook(username: str) -> str:
    try:
        with httpx.Client(base_url=HUB_API_INTERNAL, headers=_hub_headers(), timeout=30) as hub:
            r = hub.post(f"/users/{username}")
            if r.status_code not in (201, 409):
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")

            r = hub.post(f"/users/{username}/server")
            if r.status_code not in (201, 202, 400):
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")

            r = hub.post(f"/users/{username}/tokens")
            if r.status_code != 201:
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")
            user_token = r.json()["token"]
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Cannot reach JupyterHub")

    return f"{HUB_PUBLIC_URL}/user/{username}/?token={user_token}"

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
    SESSIONS[token] = user["role"]
    return {"token": token, "role": user["role"]}

@app.get("/dashboard")
def dashboard(authorization: str = Header(...)):
    token = authorization.removeprefix("Bearer ").strip()
    role = SESSIONS.get(token)
    if not role:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"role": role, "tables": ROLE_TABLES[role]}

@app.get("/health")
def health():
    return {"status": "ok"}
