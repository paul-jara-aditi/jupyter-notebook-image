# Auth ↔ JupyterHub Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `POST /auth/jupyter-launch` endpoint to the auth service that turns an auth-service session token into a ready-to-open JupyterHub notebook URL (no login form), and reject unauthenticated callers with 401.

**Architecture:** The auth service orchestrates JupyterHub via its Admin API over the shared Docker network. It creates/starts the role's ephemeral notebook, mints a JupyterHub user token, and returns `http://localhost:8000/user/{username}/?token=...`. Opening that URL authenticates the browser through the `?token=` query parameter.

**Tech Stack:** Python 3.11, FastAPI, httpx, JupyterHub REST Admin API, Docker Compose

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `auth-service/requirements.txt` | Add `httpx` |
| Modify | `auth-service/main.py` | Add hub config, `_hub_*` helpers, `POST /auth/jupyter-launch` |
| Modify | `jupyterhub_config.py` | Allow `sales`, `marketing`, `collections` users |
| Modify | `docker-compose.yml` | Give auth-service the `JUPYTERHUB_API_TOKEN` via `.env` |
| Add (MCP) | Postman "Auth Service" collection | New "Jupyter Launch" request |

This is a POC: no automated test suite exists. Each task ends with a **manual smoke test** plus a commit, matching the existing auth-service workflow.

---

### Task 1: Add httpx dependency

**Files:**
- Modify: `auth-service/requirements.txt`

- [ ] **Step 1: Add httpx to `auth-service/requirements.txt`**

The full file becomes:

```
fastapi==0.115.0
uvicorn==0.32.0
httpx==0.27.2
```

- [ ] **Step 2: Commit**

```bash
git add auth-service/requirements.txt
git commit -m "chore(auth): add httpx for JupyterHub API calls"
```

---

### Task 2: Allow role usernames in JupyterHub

**Files:**
- Modify: `jupyterhub_config.py:17`

- [ ] **Step 1: Update `allowed_users` in `jupyterhub_config.py`**

Find this line (line 17):

```python
c.Authenticator.allowed_users = {'jupyter_user'}
```

Replace it with:

```python
c.Authenticator.allowed_users = {'jupyter_user', 'sales', 'marketing', 'collections'}
```

Leave line 18 (`admin_users = {'jupyter_user'}`) unchanged.

- [ ] **Step 2: Commit**

```bash
git add jupyterhub_config.py
git commit -m "feat(hub): allow sales, marketing, collections users"
```

---

### Task 3: Pass the API token to the auth-service container

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add `env_file` to the `auth-service` block in `docker-compose.yml`**

The `auth-service` service block becomes:

```yaml
  auth-service:
    container_name: auth-paypal
    env_file: .env
    build:
      context: ./auth-service
      dockerfile: Dockerfile
    ports:
      - "8001:8001"
    networks:
      - jupyterhub-network
    restart: unless-stopped
```

(The only added line is `env_file: .env`, mirroring the `jupyter` service. This makes `JUPYTERHUB_API_TOKEN` available inside the auth container.)

- [ ] **Step 2: Verify `.env` already defines the token**

```bash
grep JUPYTERHUB_API_TOKEN .env
```

Expected: a line like `JUPYTERHUB_API_TOKEN=super-secret-paypal-token-2026`. If it is missing, add it (use the same value the hub uses).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(auth): pass JUPYTERHUB_API_TOKEN to auth-service"
```

---

### Task 4: Add hub configuration and helpers to main.py

**Files:**
- Modify: `auth-service/main.py`

- [ ] **Step 1: Add imports and hub config near the top of `auth-service/main.py`**

Change the import block at the top from:

```python
import uuid
import random
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
```

to:

```python
import os
import uuid
import random
import httpx
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
```

- [ ] **Step 2: Add hub configuration constants immediately after `app = FastAPI(title="Auth POC")`**

```python
# JupyterHub integration config
HUB_API_INTERNAL = os.getenv("HUB_API_INTERNAL", "http://jupyter-paypal:8000/hub/api")
HUB_PUBLIC_URL = os.getenv("HUB_PUBLIC_URL", "http://localhost:8000")
JUPYTERHUB_API_TOKEN = os.getenv("JUPYTERHUB_API_TOKEN", "")
```

- [ ] **Step 3: Add the hub helper function above the `# Routes` section**

Insert this just before the `# ---- Routes ----` divider comment:

```python
# ---------------------------------------------------------------------------
# JupyterHub Admin API helpers
# ---------------------------------------------------------------------------

def _hub_headers() -> dict:
    return {"Authorization": f"token {JUPYTERHUB_API_TOKEN}"}

def _launch_notebook(username: str) -> str:
    """Create+start the user's server, mint a token, return the open URL.

    Raises HTTPException(502) if the hub cannot be reached or returns an
    unexpected status.
    """
    try:
        with httpx.Client(base_url=HUB_API_INTERNAL, headers=_hub_headers(), timeout=30) as hub:
            # Create user — 201 created, 409 already exists are both fine
            r = hub.post(f"/users/{username}")
            if r.status_code not in (201, 409):
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")

            # Start server — 201 started, 202 pending, 400 already running are fine
            r = hub.post(f"/users/{username}/server")
            if r.status_code not in (201, 202, 400):
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")

            # Mint a user token for direct browser access
            r = hub.post(f"/users/{username}/tokens")
            if r.status_code != 201:
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")
            user_token = r.json()["token"]
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Cannot reach JupyterHub")

    return f"{HUB_PUBLIC_URL}/user/{username}/?token={user_token}"
```

- [ ] **Step 4: Verify the file imports cleanly**

```bash
cd auth-service
python -c "import ast; ast.parse(open('main.py').read()); print('syntax ok')"
```

Expected: `syntax ok`

- [ ] **Step 5: Commit**

```bash
git add auth-service/main.py
git commit -m "feat(auth): add JupyterHub admin API helpers"
```

---

### Task 5: Add the /auth/jupyter-launch endpoint

**Files:**
- Modify: `auth-service/main.py`

- [ ] **Step 1: Add the endpoint after the existing `/dashboard` route**

Insert this between the `dashboard` function and the `health` function:

```python
@app.post("/auth/jupyter-launch")
def jupyter_launch(authorization: str = Header(...)):
    token = authorization.removeprefix("Bearer ").strip()
    role = SESSIONS.get(token)
    if not role:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    username = role  # one hub user per role
    url = _launch_notebook(username)
    return {"url": url, "username": username, "role": role}
```

- [ ] **Step 2: Verify the file imports cleanly**

```bash
cd auth-service
python -c "import ast; ast.parse(open('main.py').read()); print('syntax ok')"
```

Expected: `syntax ok`

- [ ] **Step 3: Commit**

```bash
git add auth-service/main.py
git commit -m "feat(auth): add /auth/jupyter-launch endpoint"
```

---

### Task 6: Build, run, and smoke test the full flow

**Files:** none (verification only)

- [ ] **Step 1: Build the singleuser image (required by DockerSpawner)**

```bash
docker build -t jupyter-paypal-singleuser:latest -f Dockerfile.singleuser .
```

Expected: image builds with no errors. (Skip if already built.)

- [ ] **Step 2: Build and start both services**

```bash
docker compose up --build -d
```

Expected: `jupyter-paypal` and `auth-paypal` both start.

- [ ] **Step 3: Wait for the hub to be ready**

```bash
sleep 5
curl -s http://localhost:8000/hub/api/ | python -c "import sys,json; print(json.load(sys.stdin))"
```

Expected: a JSON object with a `version` field.

- [ ] **Step 4: Log in and capture the token**

```bash
TOKEN=$(curl -s -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"sales@company.com","password":"sales123"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")
echo "auth token: $TOKEN"
```

Expected: a non-empty UUID.

- [ ] **Step 5: Launch the notebook**

```bash
curl -s -X POST http://localhost:8001/auth/jupyter-launch \
  -H "Authorization: Bearer $TOKEN" | python -c "import sys,json; d=json.load(sys.stdin); print('username:', d['username']); print('role:', d['role']); print('url:', d['url'])"
```

Expected output, e.g.:

```
username: sales
role: sales
url: http://localhost:8000/user/sales/?token=<long-token>
```

- [ ] **Step 6: Open the URL in a browser**

Copy the `url` from Step 5 into a browser.

Expected: the Jupyter notebook interface loads directly, with **no JupyterHub login form**.

- [ ] **Step 7: Verify an invalid token is rejected**

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8001/auth/jupyter-launch \
  -H "Authorization: Bearer not-a-real-token"
```

Expected: `401`

- [ ] **Step 8: Stop the stack**

```bash
docker compose down
```

---

### Task 7: Add the Jupyter Launch request to Postman

**Files:** none (Postman workspace, done via MCP)

- [ ] **Step 1: Add a "Jupyter Launch" request to the existing "Auth Service" collection**

Request:
- Method `POST`
- URL `{{auth_url}}/auth/jupyter-launch`
- Header `Authorization: Bearer {{token}}`
- Test script (saves the URL to the environment):

```javascript
const res = pm.response.json();
pm.environment.set("jupyter_url", res.url);
```

- [ ] **Step 2: Add a `jupyter_url` variable to the "JupyterHub Local" environment**

Add `jupyter_url` with an empty initial value (it is filled when Jupyter Launch runs).

---

## Self-Review

### Spec coverage

| Spec requirement | Task |
|------------------|------|
| `POST /auth/jupyter-launch` validates session token, 401 if missing | Task 5 |
| Map role → hub username | Task 5 (`username = role`) |
| Create user (ignore 409) | Task 4 (`_launch_notebook`) |
| Start server (ignore 400 already-running) | Task 4 |
| Mint user token | Task 4 |
| Return `{url, username, role}` with `?token=` | Tasks 4 + 5 |
| 502 on hub failure | Task 4 |
| `httpx` dependency | Task 1 |
| Allow role usernames in hub | Task 2 |
| Pass `JUPYTERHUB_API_TOKEN` to auth container | Task 3 |
| Postman "Jupyter Launch" request | Task 7 |
| Browser opens with no login form | Task 6 Step 6 |

### Placeholder scan

- No "TBD"/"TODO". Every code step shows full code.
- The only intentionally-empty value is the Postman `jupyter_url` initial value (Task 7), which is correct.

### Type / name consistency

- `HUB_API_INTERNAL`, `HUB_PUBLIC_URL`, `JUPYTERHUB_API_TOKEN` defined in Task 4 Step 2, used in Task 4 Step 3.
- `_launch_notebook(username)` defined in Task 4, called in Task 5.
- `_hub_headers()` defined and used within Task 4.
- `SESSIONS` already exists in `main.py` (token → role); reused in Task 5.
- Endpoint returns `username` = `role` string, consistent with the `allowed_users` set added in Task 2.
