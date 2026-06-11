# Plan: Jupyter Sandboxing — Decision Doc + Level 3 (JupyterHub Multi-User)

## Context

The project today is a **single-user** Dockerized Jupyter (custom `Dockerfile` on `python:3.11-slim`, unprivileged `jupyter_user`, token auth via `start.sh`). The goal is to move toward proper sandboxing based on a 4-level reference (1: rootless containers, 2: gVisor/microVMs, 3: serverless/JupyterHub multi-tenant, 4: JupyterLite in-browser).

Decisions taken:
- **Deliverable: Both** — a decision/comparison document *and* an implementation.
- **Threat model: Multi-user / team** → target **Level 3: JupyterHub + DockerSpawner**.

**Platform constraint:** host is Windows 11 + Docker Desktop. gVisor's `runsc` runtime (Level 2) only runs on a Linux host, so it is documented as a future/cloud option, not implemented here. JupyterHub + DockerSpawner works on Docker Desktop via the mounted Docker socket. JupyterLite (Level 4) is fully cross-platform and documented as complementary.

---

## Part A — Decision Document

**New file:** `docs/sandboxing-strategy.md`

A concise comparison of the 4 levels applied to this project.

- **Where we are today:** partial Level 1 (custom image, unprivileged user, read-only packages, token auth).

| Level | Tooling | Windows/Docker Desktop | Best for |
|-------|---------|------------------------|----------|
| 1 Light | Docker/Podman rootless, jupyter docker-stacks (uid 1000), network bridges | ✅ Native | Single user, trusted code |
| 2 Deep | gVisor `runsc`, Kata/Firecracker, KubeArmor | ⚠️ Linux host only (not Docker Desktop) | Untrusted code execution |
| 3 Cloud/Multi-tenant | **JupyterHub + DockerSpawner**, idle-culler | ✅ Via Docker socket | **Teams (chosen)** |
| 4 Browser-only | JupyterLite + Pyodide (WASM) | ✅ Static site, zero backend | Sharing/demos, fully untrusted code |

- **Recommendation:** Implement **Level 3** now for the team. Escalate to **Level 2 (gVisor)** only if untrusted code must run, on a Linux host or cloud VM (`--runtime=runsc`). Offer **Level 4 (JupyterLite)** as a complementary zero-infra channel for read-only/demo notebooks.
- **Network isolation note:** user containers on an `internal` Docker network are cut off from the host LAN/intranet and internet; the Hub bridges to the host so the browser can still reach it.

---

## Part B — Level 3 Implementation (JupyterHub + DockerSpawner)

### Architecture
- **Hub container** (port 8000): authentication + spawning. Mounts the Docker socket to spawn per-user containers.
- **Single-user containers**: one per logged-in user, spawned on demand, auto-removed on logout, with CPU/memory caps.
- **Two networks**:
  - `hub-public` (bridge): host ↔ Hub on `:8000`, and Hub egress.
  - `hub-internal` (`internal: true`): Hub ↔ single-user containers. User containers join **only** this → no LAN/internet access. Hub joins both.

### Files to create

**1. `Dockerfile.hub`** — the Hub image
```dockerfile
FROM quay.io/jupyterhub/jupyterhub:5
RUN pip install --no-cache-dir \
    dockerspawner \
    jupyterhub-nativeauthenticator \
    jupyterhub-idle-culler
COPY jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py
```

**2. `Dockerfile.notebook`** — single-user image (replaces the role of the current `Dockerfile`)
```dockerfile
# Official stack already runs as unprivileged jovyan (uid 1000) = Level 1 baseline
FROM quay.io/jupyter/scipy-notebook:latest
COPY --chown=1000:1000 requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
```

**3. `jupyterhub_config.py`** — core config
- `c.JupyterHub.spawner_class = 'dockerspawner.DockerSpawner'`
- `c.DockerSpawner.image = os.environ['DOCKER_NOTEBOOK_IMAGE']`
- `c.DockerSpawner.network_name = 'hub-internal'`
- `c.JupyterHub.hub_connect_ip = 'jupyterhub'` ; `c.JupyterHub.hub_ip = '0.0.0.0'`
- Per-user volume: `c.DockerSpawner.volumes = {'jupyterhub-user-{username}': '/home/jovyan/work'}`
- Shared read-only data + starter notebook mounted at `/home/jovyan/shared` (`mode: 'ro'`)
- `c.DockerSpawner.remove = True`
- Resource caps: `mem_limit='2G'`, `cpu_limit=1.0` (tunable)
- Auth: `c.JupyterHub.authenticator_class = 'nativeauthenticator.NativeAuthenticator'`, `c.NativeAuthenticator.open_signup = False`, `c.Authenticator.admin_users = set(os.environ.get('JUPYTERHUB_ADMIN','admin').split(','))`
- DB: `c.JupyterHub.db_url = 'sqlite:////srv/jupyterhub/data/jupyterhub.sqlite'`
- Idle culling via `jupyterhub-idle-culler` hub service (e.g. 1h idle)

**4. Rewrite `docker-compose.yml`**

```yaml
services:
  jupyterhub:
    build: { context: docs, dockerfile: Dockerfile.hub }
    container_name: jupyterhub
    ports: [ "8000:8000" ]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:rw
      - jupyterhub-data:/srv/jupyterhub/data
      - ./data:/srv/shared-data:ro
      - ./notebooks:/srv/shared-notebooks:ro
    environment:
      DOCKER_NOTEBOOK_IMAGE: paypal-notebook:latest
      JUPYTERHUB_ADMIN: ${JUPYTERHUB_ADMIN}
    networks: [ hub-public, hub-internal ]
    restart: unless-stopped

networks:
  hub-public:
  hub-internal:
    internal: true

volumes:
  jupyterhub-data:
```
> Build the single-user image separately so it exists on the host daemon:
> `docker build -f Dockerfile.notebook -t paypal-notebook:latest .`

**5. Update `.env.example`**
- Remove the now-unused `JUPYTER_TOKEN`.
- Add `JUPYTERHUB_ADMIN=admin` (comma-separated admin usernames).

**6. Update `README.md`**
- Replace single-container instructions with the JupyterHub flow: build the notebook image, `docker compose up --build`, open `http://localhost:8000`, sign up, admin authorizes users.
- Update Security section: per-user container isolation, internal network, resource caps, idle culling. Link `docs/sandboxing-strategy.md`.

### Files retired
- `Dockerfile` (single-user `python:3.11-slim`) and `start.sh` are superseded by JupyterHub — recommend deleting both.

---

## Critical Files
- New: `Dockerfile.hub`, `Dockerfile.notebook`, `jupyterhub_config.py`, `docs/sandboxing-strategy.md`
- Rewritten: `docker-compose.yml`
- Updated: `requirements.txt`, `.env.example`, `README.md`
- Removed: `Dockerfile`, `start.sh`

## Verification (end-to-end)
1. Ensure Docker Desktop is running (`docker info`).
2. Build the single-user image: `docker build -f Dockerfile.notebook -t paypal-notebook:latest .`
3. `cp .env.example .env` and set `JUPYTERHUB_ADMIN` to your username.
4. `docker compose up --build` → Hub on `http://localhost:8000`.
5. Sign up as admin, log in. Confirm a single-user container spawns: `docker ps` shows `jupyter-<username>`.
6. Confirm `/home/jovyan/shared/...` holds the starter notebook + `german_credit.csv` (read-only) and `/home/jovyan/work` is writable/persistent across restarts.
7. **Network isolation check:** in a cell, `import urllib.request; urllib.request.urlopen('https://example.com', timeout=5)` → should fail (no external egress).
8. **Isolation check:** create a second user, confirm a separate container and that users can't see each other's `work` volume.
9. Stop a user's server → confirm `remove=True` deletes the container.
10. Leave a server idle past the timeout → confirm idle-culler stops it.
