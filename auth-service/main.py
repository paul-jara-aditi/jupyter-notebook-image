import uuid
import random
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

app = FastAPI(title="Auth POC")

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
