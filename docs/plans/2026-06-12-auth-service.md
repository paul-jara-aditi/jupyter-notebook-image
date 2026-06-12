# Auth Service Implementation Plan (POC)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** POC container — email/password login, 3 roles (sales, marketing, collections), each role sees a different fake Big Data table (risk, fraud, average_debt with 100 invented rows). No validations, no database, no tests.

**Architecture:** Single `main.py` with FastAPI. Users hardcoded in a dict, sessions in memory (uuid token → role), fake data generated at startup with Python's `random` module. No ORM, no bcrypt, no JWT library.

**Tech Stack:** Python 3.11, FastAPI 0.115, uvicorn 0.32

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `auth-service/requirements.txt` | Two dependencies: fastapi + uvicorn |
| Create | `auth-service/Dockerfile` | Container image |
| Create | `auth-service/main.py` | Everything: users, sessions, fake data, routes |
| Modify | `docker-compose.yml` | Add auth-service on port 8001 |

---

### Task 1: Create auth-service files

**Files:**
- Create: `auth-service/requirements.txt`
- Create: `auth-service/Dockerfile`
- Create: `auth-service/main.py`

- [ ] **Step 1: Create `auth-service/requirements.txt`**

```
fastapi==0.115.0
uvicorn==0.32.0
```

- [ ] **Step 2: Create `auth-service/Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
```

- [ ] **Step 3: Create `auth-service/main.py`**

```python
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
```

- [ ] **Step 4: Commit**

```bash
git add auth-service/
git commit -m "feat(auth): add POC auth service with fake big data tables"
```

---

### Task 2: Add auth-service to docker-compose

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Update `docker-compose.yml`**

```yaml
networks:
  jupyterhub-network:
    name: jupyterhub-network

services:
  jupyter:
    container_name: jupyter-paypal
    env_file: .env
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./jupyterhub_config.py:/home/jupyter_user/jupyterhub_config.py
    networks:
      - jupyterhub-network
    restart: unless-stopped

  auth-service:
    container_name: auth-paypal
    build:
      context: ./auth-service
      dockerfile: Dockerfile
    ports:
      - "8001:8001"
    networks:
      - jupyterhub-network
    restart: unless-stopped
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(auth): add auth-service to docker-compose on port 8001"
```

---

### Task 3: Smoke test

- [ ] **Step 1: Build and start**

```bash
docker compose build auth-service
docker compose up auth-service -d
```

- [ ] **Step 2: Health check**

```bash
curl http://localhost:8001/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 3: Login as sales and call dashboard**

```bash
TOKEN=$(curl -s -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"sales@company.com","password":"sales123"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl http://localhost:8001/dashboard -H "Authorization: Bearer $TOKEN"
```

Expected: `{"role":"sales","tables":{"risk":[...100 rows...]}}`

- [ ] **Step 4: Wrong password returns 401**

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"sales@company.com","password":"wrong"}'
```

Expected: `401`

- [ ] **Step 5: Stop container**

```bash
docker compose down auth-service
```

---

### Task 4: Create Postman requests for auth endpoints

**Goal:** Add a collection in the existing Postman workspace with 3 requests covering login, dashboard, and health.

- [ ] **Step 1: Find the existing Postman workspace**

Use the Postman MCP to list workspaces and locate the one used for this project.

- [ ] **Step 2: Create an "Auth Service" collection with 3 requests**

Requests to create:

| Name | Method | URL | Notes |
|------|--------|-----|-------|
| Login | `POST` | `{{auth_url}}/auth/login` | Body: `{"email":"{{email}}","password":"{{password}}"}` |
| Dashboard | `GET` | `{{auth_url}}/dashboard` | Header: `Authorization: Bearer {{token}}` |
| Health | `GET` | `{{auth_url}}/health` | No auth required |

- [ ] **Step 3: Create an "Auth Service Local" environment**

| Variable | Value |
|----------|-------|
| `auth_url` | `http://localhost:8001` |
| `email` | `sales@company.com` |
| `password` | `sales123` |
| `token` | *(empty — filled after Login runs)* |

- [ ] **Step 4: Add a test script to Login that saves the token**

In the Login request's "Tests" tab, add:

```javascript
const res = pm.response.json();
pm.environment.set("token", res.token);
```

- [ ] **Step 5: Commit plan update**

```bash
git add docs/superpowers/plans/2026-06-12-auth-service.md
git commit -m "docs: add Postman task to auth service plan"
```

---

## Credential reference

| Email | Password | Role | Sees |
|-------|----------|------|------|
| sales@company.com | sales123 | sales | `risk` table |
| marketing@company.com | marketing123 | marketing | `fraud` table |
| collections@company.com | collections123 | collections | `average_debt` table |
