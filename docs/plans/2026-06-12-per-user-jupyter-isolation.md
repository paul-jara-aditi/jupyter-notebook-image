# Per-User Jupyter Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each authenticated user gets their own JupyterHub container (not shared per role), the auth-service session token is injected as `AUTH_SERVICE_TOKEN` env var, and each container starts with a fresh copy of the template notebooks — ephemeral, lost when the container is destroyed.

**Architecture:** Notebooks are baked into the singleuser Docker image via `COPY`; no host volume mount for notebooks. A `pre_spawn_hook` in `jupyterhub_config.py` only injects `AUTH_SERVICE_TOKEN` from the server-start POST body. The auth-service derives a unique JupyterHub username per email address so each user gets their own container.

**Tech Stack:** JupyterHub 5.4.6, DockerSpawner 13, FastAPI, Docker Compose.

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `docker-compose.yml` | Add `singleuser` build service with project root as context |
| Modify | `singleuser/Dockerfile` | `COPY notebooks/` into the image |
| Modify | `auth-service/main.py` | Per-user username, SESSIONS type, token in server-start body |
| Modify | `jupyterhub_config.py` | `allow_all`, remove notebooks volume, simple `pre_spawn_hook` |

---

### Task 1: Bake notebooks into the singleuser image

**Files:**
- Modify: `singleuser/Dockerfile`
- Modify: `docker-compose.yml`

Notebooks are copied into the image at build time. Each spawned container starts with a
fresh `/home/jovyan/work/notebooks` from the image layer. Any user changes are lost when
the container is destroyed (`remove = True`) — intentionally ephemeral.

The singleuser build needs access to `notebooks/` which lives in the project root, not in
`singleuser/`. Changing the build context to `.` (project root) gives the Dockerfile access.

- [ ] **Step 1: Add `COPY notebooks/` to `singleuser/Dockerfile`**

Open `singleuser/Dockerfile`. After the `mamba install` block and before `USER root`, add:

```dockerfile
# Bake template notebooks into the image — each container starts with a fresh copy.
# Changes made during a session are lost when the container is destroyed (ephemeral).
COPY notebooks/ /home/jovyan/work/notebooks/
```

Full resulting Dockerfile:
```dockerfile
FROM quay.io/jupyter/base-notebook:latest

ENV PYTHONNOUSERSITE=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt /tmp/requirements.txt
RUN mamba install --yes --quiet --channel conda-forge --file /tmp/requirements.txt \
    && mamba clean --all -f -y

# Bake template notebooks into the image — each container starts with a fresh copy.
# Changes made during a session are lost when the container is destroyed (ephemeral).
COPY notebooks/ /home/jovyan/work/notebooks/

USER root

# Lock down the Python/conda environment so jovyan can read/execute but not write.
RUN chown -R root:root /opt/conda \
    && chmod -R 755 /opt/conda

# Disable the Jupyter terminal to block direct shell access.
RUN mkdir -p /etc/jupyter \
    && printf '%s\n' \
        'c.ServerApp.terminals_enabled = False' \
        'c.NotebookApp.terminals_enabled = False' \
       > /etc/jupyter/jupyter_server_config.py

# Block shell execution (!cmd) and package-manager magics (%pip, %conda, %mamba).
RUN mkdir -p /etc/ipython/profile_default/startup \
    && cat > /etc/ipython/profile_default/startup/00-block-system.py << 'EOF'
from IPython import get_ipython

ip = get_ipython()
if ip:
    def _blocked(cmd, *args, **kwargs):
        raise RuntimeError("System command execution is disabled in this environment.")

    ip.system = _blocked

    for magic in ("pip", "conda", "mamba"):
        ip.magics_manager.magics["line"].pop(magic, None)
EOF

USER ${NB_UID}
```

- [ ] **Step 2: Add `singleuser` build service to `docker-compose.yml`**

The service uses `profiles: ["build"]` so it is never started by `docker compose up`,
but `docker compose build singleuser` works and uses the project root as context —
giving the Dockerfile access to `notebooks/`.

Add this service to `docker-compose.yml` (after the `auth-service` block):

```yaml
  singleuser:
    build:
      context: .
      dockerfile: singleuser/Dockerfile
    image: jupyter-paypal-singleuser:latest
    profiles:
      - build
```

- [ ] **Step 3: Rebuild the singleuser image**

```bash
docker compose build singleuser
```

Expected output ends with:
```
=> => naming to docker.io/library/jupyter-paypal-singleuser:latest
```

- [ ] **Step 4: Verify notebooks are inside the image**

```bash
docker run --rm jupyter-paypal-singleuser:latest ls /home/jovyan/work/notebooks
```

Expected: `loan_risk_analysis.ipynb` (and any other notebooks in `notebooks/`).

- [ ] **Step 5: Commit**

```bash
git add singleuser/Dockerfile docker-compose.yml
git commit -m "feat: bake template notebooks into singleuser image (ephemeral per container)"
```

---

### Task 2: auth-service — per-user identity + token injection

**Files:**
- Modify: `auth-service/main.py`

Three changes:
1. `SESSIONS` stores only the email string (token → email). Role is never stored — it
   is derived on demand from `USERS[email]["role"]` in any endpoint that needs it.
2. Username is derived from email (`sales@company.com` → `sales_company_com`).
3. `_launch_notebook` passes `AUTH_SERVICE_TOKEN` in the server-start POST body so
   `pre_spawn_hook` can inject it as a container env var.

- [ ] **Step 1: Add the username helper and update SESSIONS type**

Replace:
```python
# Token → role map. Lives in memory, so sessions are lost on container restart.
# Acceptable for a POC; a real system would use Redis or a DB.
SESSIONS: dict[str, str] = {}
```

With:
```python
# Token → email map. Lives in memory — resets on container restart (POC only).
SESSIONS: dict[str, str] = {}


def _email_to_username(email: str) -> str:
    # JupyterHub usernames must not contain @ or dots.
    # sales@company.com → sales_company_com
    return email.replace("@", "_").replace(".", "_")
```

- [ ] **Step 2: Update `/auth/login` to store email in session**

Replace:
```python
    token = str(uuid.uuid4())
    SESSIONS[token] = user["role"]
    return {"token": token, "role": user["role"]}
```

With:
```python
    token = str(uuid.uuid4())
    SESSIONS[token] = body.email
    return {"token": token, "role": user["role"]}
```

- [ ] **Step 3: Update `/dashboard` to derive role from email**

Replace:
```python
    role = SESSIONS.get(token)
    if not role:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"role": role, "tables": ROLE_TABLES[role]}
```

With:
```python
    email = SESSIONS.get(token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    role = USERS[email]["role"]
    return {"role": role, "tables": ROLE_TABLES[role]}
```

- [ ] **Step 4: Update `_launch_notebook` to accept the auth token**

Replace the entire `_launch_notebook` function:
```python
def _launch_notebook(username: str) -> str:
    """Orchestrates three JupyterHub Admin API calls to produce a ready-to-open URL.

    Steps:
      1. Create the hub user (idempotent — 409 means it already exists).
      2. Start the user's notebook server (202 = starting, 400 = already running).
      3. Mint a short-lived user token for browser authentication.

    Returns a URL with ?token=... so the browser authenticates without a login form.
    Raises HTTPException(502) if the hub is unreachable or returns an unexpected status.
    """
    try:
        with httpx.Client(base_url=HUB_API_INTERNAL, headers=_hub_headers(), timeout=30) as hub:

            # 201 = created, 409 = user already exists — both are fine
            r = hub.post(f"/users/{username}")
            if r.status_code not in (201, 409):
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")

            # 201 = started, 202 = starting (DockerSpawner is async), 400 = already running
            r = hub.post(f"/users/{username}/server")
            if r.status_code not in (201, 202, 400):
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")

            # Mint a user-scoped token. Opening the URL with ?token=<value> bypasses
            # the JupyterHub login form entirely — the hub validates the token directly.
            r = hub.post(f"/users/{username}/tokens")
            if r.status_code != 201:
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")
            user_token = r.json()["token"]

    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Cannot reach JupyterHub")

    return f"{HUB_PUBLIC_URL}/hub/token-login?token={user_token}&next={quote(f'/user/{username}/', safe='')}"
```

With:
```python
def _launch_notebook(username: str, auth_service_token: str) -> str:
    """Orchestrates three JupyterHub Admin API calls to produce a ready-to-open URL.

    Steps:
      1. Create the hub user (idempotent — 409 means it already exists).
      2. Start the user's notebook server, passing the auth token as a spawn option
         so pre_spawn_hook injects it as a container environment variable.
      3. Mint a short-lived user token for the /hub/token-login browser redirect.

    Raises HTTPException(502) if the hub is unreachable or returns an unexpected status.
    """
    try:
        with httpx.Client(base_url=HUB_API_INTERNAL, headers=_hub_headers(), timeout=30) as hub:

            # 201 = created, 409 = user already exists — both are fine
            r = hub.post(f"/users/{username}")
            if r.status_code not in (201, 409):
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")

            # Pass the auth token as a spawn option — pre_spawn_hook reads spawner.user_options
            # and injects it as an environment variable in the container.
            # 201 = started, 202 = starting (async), 400 = already running
            r = hub.post(f"/users/{username}/server", json={
                "AUTH_SERVICE_TOKEN": auth_service_token,
            })
            if r.status_code not in (201, 202, 400):
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")

            r = hub.post(f"/users/{username}/tokens")
            if r.status_code != 201:
                raise HTTPException(status_code=502, detail=f"JupyterHub API error: {r.status_code} {r.text}")
            user_token = r.json()["token"]

    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Cannot reach JupyterHub")

    next_path = quote(f"/user/{username}/", safe="")
    return f"{HUB_PUBLIC_URL}/hub/token-login?token={user_token}&next={next_path}"
```

- [ ] **Step 5: Update `/auth/jupyter-launch` to derive username from email**

Replace:
```python
@app.post("/auth/jupyter-launch")
def jupyter_launch(authorization: str = Header(...)):
    token = authorization.removeprefix("Bearer ").strip()
    role = SESSIONS.get(token)
    if not role:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    # One JupyterHub user per role — all users of the same role share one notebook server
    username = role
    url = _launch_notebook(username)
    return {"url": url, "username": username, "role": role}
```

With:
```python
@app.post("/auth/jupyter-launch")
def jupyter_launch(authorization: str = Header(...)):
    token = authorization.removeprefix("Bearer ").strip()
    email = SESSIONS.get(token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    username = _email_to_username(email)
    url = _launch_notebook(username, auth_service_token=token)
    return {"url": url, "username": username}
```

- [ ] **Step 6: Rebuild and restart auth-service**

```bash
docker compose build auth-service && docker compose up -d auth-service
```

Expected: `auth-paypal Recreated` → `auth-paypal Started`.

- [ ] **Step 7: Smoke-test the three logins**

```bash
curl -s -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"sales@company.com","password":"sales123"}'
```

Expected: `{"token":"<uuid>","role":"sales"}`

```bash
curl -s -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"marketing@company.com","password":"marketing123"}'
```

Expected: `{"token":"<uuid>","role":"marketing"}`

- [ ] **Step 8: Commit**

```bash
git add auth-service/main.py
git commit -m "feat: per-user JupyterHub identity and auth token injection"
```

---

### Task 3: jupyterhub_config.py — allow_all + pre_spawn_hook

**Files:**
- Modify: `jupyterhub_config.py`

Three changes:
1. Replace the hardcoded `allowed_users` set with `allow_all = True` — usernames are now
   dynamic (e.g., `sales_company_com`) and can't be hardcoded.
2. Remove `notebooks` from the static volumes — notebooks are baked into the image.
3. Add a `pre_spawn_hook` that reads `spawner.user_options` (set from the POST body in
   `_launch_notebook`) and injects `AUTH_SERVICE_TOKEN` as a container env var.

- [ ] **Step 1: Replace `allowed_users` with `allow_all`**

Replace:
```python
c.Authenticator.allowed_users = {'jupyter_user', 'sales', 'marketing', 'collections'}
c.Authenticator.admin_users = {'jupyter_user'}
```

With:
```python
# allow_all lets any username authenticate — usernames are now derived from email
# addresses (e.g. sales_company_com) and cannot be hardcoded.
# Access is controlled by the auth-service: only authenticated users receive a Hub
# API token that can reach /hub/token-login.
c.Authenticator.allow_all = True
c.Authenticator.admin_users = {'jupyter_user'}
```

- [ ] **Step 2: Remove the `notebooks` entry from the static volumes**

Replace:
```python
c.DockerSpawner.volumes = {
    f'{host_path}/notebooks': '/home/jovyan/work/notebooks',
    f'{host_path}/data':      '/home/jovyan/work/data',
    f'{host_path}/src':       '/home/jovyan/work/src',
}
```

With:
```python
# notebooks is intentionally absent — it is baked into the image and is ephemeral.
c.DockerSpawner.volumes = {
    f'{host_path}/data': '/home/jovyan/work/data',
    f'{host_path}/src':  '/home/jovyan/work/src',
}
```

- [ ] **Step 3: Add the `pre_spawn_hook` before the `api_token` block**

Add after the volumes config:
```python
async def pre_spawn_hook(spawner):
    """Inject the auth-service token as a container environment variable.

    AUTH_SERVICE_TOKEN lets notebooks call /dashboard without asking the user
    to log in again. Its value comes from the JSON body of POST /users/{name}/server,
    which DockerSpawner exposes as spawner.user_options.
    """
    token = spawner.user_options.get('AUTH_SERVICE_TOKEN', '')
    if token:
        spawner.environment['AUTH_SERVICE_TOKEN'] = token


c.Spawner.pre_spawn_hook = pre_spawn_hook
```

- [ ] **Step 4: Restart the Hub**

```bash
docker compose restart jupyter
```

Check for startup errors:
```bash
docker logs jupyter-hub 2>&1 | grep -iE "^\\[E|^\\[C" | head -10
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add jupyterhub_config.py
git commit -m "feat: allow_all users, remove notebooks volume, add pre_spawn_hook for env vars"
```

---

### Task 4: End-to-end verification

Verify all three requirements: separate containers per user, env vars injected, and
notebooks are fresh and independent per container.

- [ ] **Step 1: Launch Jupyter for sales**

```bash
curl -s -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"sales@company.com","password":"sales123"}'
```

Save the token, then:
```bash
curl -s -X POST http://localhost:8001/auth/jupyter-launch \
  -H "Authorization: Bearer <token>"
```

Expected: `"username":"sales_company_com"` — note the underscore format, not `sales`.

- [ ] **Step 2: Launch Jupyter for marketing**

Repeat with `marketing@company.com` / `marketing123`.

Expected: `"username":"marketing_company_com"`.

- [ ] **Step 3: Verify two separate containers are running**

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep jupyter
```

Expected — three containers, Hub plus one per user:
```
jupyter-sales_company_com      Up X seconds (healthy)
jupyter-marketing_company_com  Up X seconds (healthy)
jupyter-hub                    Up X minutes
```

- [ ] **Step 4: Verify env vars are injected in the sales container**

```bash
docker exec jupyter-sales_company_com env | grep AUTH_SERVICE_TOKEN
```

Expected:
```
AUTH_SERVICE_TOKEN=<uuid-from-sales-login>
```

- [ ] **Step 5: Verify notebooks are present and ephemeral**

```bash
docker exec jupyter-sales_company_com ls /home/jovyan/work/notebooks
```

Expected: `loan_risk_analysis.ipynb`

Write a file inside the container to simulate a user change:
```bash
docker exec jupyter-sales_company_com sh -c "echo test > /home/jovyan/work/notebooks/test.txt"
```

Stop the container (simulates user closing Jupyter):
```bash
docker stop jupyter-sales_company_com
```

Relaunch Jupyter for sales (repeat Step 1) and verify the file is gone:
```bash
docker exec jupyter-sales_company_com ls /home/jovyan/work/notebooks
```

Expected: `loan_risk_analysis.ipynb` only — `test.txt` does not exist.

---

## Summary of runtime behavior after this plan

| Scenario | Before | After |
|----------|--------|-------|
| Two users with role `sales` | Share one container | Each gets their own container |
| `os.environ['AUTH_SERVICE_TOKEN']` in notebook | `KeyError` | UUID token for `/dashboard` calls |
| User modifies a notebook | Changes persist on host | Lost when container stops (ephemeral) |
| Next Jupyter launch | Same files as before | Fresh copy from image |
