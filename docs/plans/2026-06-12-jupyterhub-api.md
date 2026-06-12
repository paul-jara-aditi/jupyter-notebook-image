# JupyterHub API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy JupyterHub so that each Postman API call starts an isolated, ephemeral Jupyter Notebook container per user — pre-loaded with the existing notebooks, dataset, and src directory — and destroyed when stopped.

**Architecture:** JupyterHub (hub container) uses `DockerSpawner` to create a sibling Docker container per user on the host daemon. Each spawned container mounts `./notebooks`, `./data`, and `./src` as bind mounts from the host. `DockerSpawner.remove = True` ensures the container is destroyed when the server stops (ephemeral). Users are isolated because each runs in their own container with their own filesystem namespace.

**Tech Stack:** JupyterHub 4.x, DockerSpawner, DummyAuthenticator, Docker Compose, Postman (MCP)

---

## File Structure

| Status | Action | Path | Responsibility |
|--------|--------|------|----------------|
| ✅ DONE | Modify | `Dockerfile` | Hub image: jupyterhub + Node.js + configurable-http-proxy |
| ✅ DONE | Modify | `start.sh` | Starts jupyterhub |
| ✅ DONE | Postman | PayPal workspace | Collection "JupyterHub API" + Environment "JupyterHub Local" |
| 🔄 UPDATE | Modify | `requirements.txt` | Add `dockerspawner` |
| 🔄 UPDATE | Modify | `Dockerfile` | Add `dockerspawner` to pip install |
| 🆕 NEW | Create | `singleuser/Dockerfile`, `singleuser/requirements.txt` | Lean image for spawned user containers (jupyter + analysis libs) |
| 🔄 UPDATE | Modify | `jupyterhub_config.py` | Switch to DockerSpawner, configure image/network/volumes/remove |
| 🔄 UPDATE | Modify | `docker-compose.yml` | Add Docker socket mount + named network; remove notebook volumes from hub |
| 🔄 UPDATE | Modify | `.env` | Add `HOST_PROJECT_PATH` for DockerSpawner bind mounts |

---

## Task 1: Add dockerspawner to hub image ✅ PARTIALLY DONE

jupyterhub is already installed. Only need to add `dockerspawner`.

**Files:**
- Modify: `requirements.txt`
- Modify: `Dockerfile`

- [ ] **Step 1: Add dockerspawner to requirements.txt**

```
pandas==2.2.0
numpy==1.26.4
matplotlib==3.8.2
seaborn==0.13.2
pyarrow==15.0.0
jupyterhub==4.1.6
dockerspawner==13.0.0
```

- [ ] **Step 2: Add dockerspawner to the pip install line in Dockerfile**

Find the existing line:
```dockerfile
RUN pip install jupyter jupyterhub -r /tmp/requirements.txt
```

Replace with:
```dockerfile
RUN pip install jupyter jupyterhub dockerspawner -r /tmp/requirements.txt
```

- [ ] **Step 3: Verify syntax**

```bash
python -m py_compile requirements.txt 2>/dev/null; echo "OK"
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt Dockerfile
git commit -m "feat: add dockerspawner to hub image"
```

---

## Task 2: Create singleuser/Dockerfile 🆕 NEW

This image is used by DockerSpawner to spawn one container per user. It is intentionally lean — no JupyterHub server, just the client (`jupyterhub-singleuser`) and the analysis libraries.

**Files:**
- Create: `singleuser/Dockerfile`
- Create: `singleuser/requirements.txt`

- [ ] **Step 1: Create singleuser/Dockerfile**

```dockerfile
FROM python:3.11-slim

ENV PYTHONNOUSERSITE=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt /tmp/

RUN pip install jupyterhub notebook -r /tmp/requirements.txt

# Standard jupyter/docker-stacks username convention
RUN useradd -ms /bin/bash jovyan

WORKDIR /home/jovyan/work
RUN chown -R jovyan:jovyan /home/jovyan/work

USER jovyan

CMD ["jupyterhub-singleuser", "--ip=0.0.0.0"]
```

- [ ] **Step 2: Build the singleuser image**

```bash
docker build -t jupyter-paypal-singleuser:latest ./singleuser
```

Expected: image `jupyter-paypal-singleuser:latest` appears in `docker images`.

- [ ] **Step 3: Verify jupyterhub-singleuser is available in the image**

```bash
docker run --rm jupyter-paypal-singleuser:latest jupyterhub-singleuser --version
```

Expected: prints a version number without error.

- [ ] **Step 4: Commit**

```bash
git add singleuser/
git commit -m "feat: add singleuser image for DockerSpawner"
```

---

## Task 3: Update jupyterhub_config.py for DockerSpawner 🔄 UPDATE

**Files:**
- Modify: `jupyterhub_config.py`

- [ ] **Step 1: Replace jupyterhub_config.py**

```python
import os

# Hub network
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000

# State files
c.JupyterHub.db_url = 'sqlite:////var/lib/jupyterhub/jupyterhub.sqlite'
c.JupyterHub.cookie_secret_file = '/var/lib/jupyterhub/jupyterhub_cookie_secret'

# DummyAuthenticator: any password accepted — OK for local dev containers
c.JupyterHub.authenticator_class = 'dummy'
c.DummyAuthenticator.password = 'paypal'

c.Authenticator.allowed_users = {'jupyter_user'}
c.Authenticator.admin_users = {'jupyter_user'}

# DockerSpawner: each user gets an isolated, ephemeral container
c.JupyterHub.spawner_class = 'dockerspawner.DockerSpawner'
c.DockerSpawner.image = 'jupyter-paypal-singleuser:latest'
c.DockerSpawner.network_name = 'jupyterhub-network'
c.DockerSpawner.remove = True          # destroy container when server stops (ephemeral)
c.DockerSpawner.notebook_dir = '/home/jovyan/work'
c.DockerSpawner.default_url = '/tree/notebooks'

# Mount host notebooks/data/src into each spawned container.
# HOST_PROJECT_PATH must be the absolute host path to this project dir (set in .env).
host_path = os.environ.get('HOST_PROJECT_PATH', '').rstrip('/').rstrip('\\')
c.DockerSpawner.volumes = {
    f'{host_path}/notebooks': '/home/jovyan/work/notebooks',
    f'{host_path}/data':      '/home/jovyan/work/data',
    f'{host_path}/src':       '/home/jovyan/work/src',
}

# Admin API token
api_token = os.environ.get('JUPYTERHUB_API_TOKEN', '')
if api_token:
    c.JupyterHub.api_tokens = {api_token: 'jupyter_user'}
```

- [ ] **Step 2: Verify syntax**

```bash
python -m py_compile jupyterhub_config.py && echo "syntax OK"
```

Expected: `syntax OK`

- [ ] **Step 3: Commit**

```bash
git add jupyterhub_config.py
git commit -m "feat: switch to DockerSpawner for isolated ephemeral user containers"
```

---

## Task 4: Update docker-compose.yml and .env 🔄 UPDATE

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env`

Changes from the current version:
- Add `/var/run/docker.sock` mount so the hub can call the Docker daemon
- Add named network `jupyterhub-network` (DockerSpawner needs a known network to attach spawned containers)
- Remove `./notebooks`, `./data`, `./src` volume mounts from the hub — DockerSpawner mounts them directly into spawned containers using `HOST_PROJECT_PATH`

- [ ] **Step 1: Replace docker-compose.yml**

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
```

- [ ] **Step 2: Add HOST_PROJECT_PATH to .env**

Open `.env` and add the absolute host path (Windows forward-slash format):

```
JUPYTERHUB_API_TOKEN=super-secret-paypal-token-2026
HOST_PROJECT_PATH=C:/Users/CristianPaulJara/workspace-paypal/jupyter-notebook-image
```

- [ ] **Step 3: Rebuild and start the hub**

```bash
docker compose up --build -d
```

Wait for log line: `JupyterHub is now running at http://0.0.0.0:8000/`

```bash
docker compose logs --tail=5
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml .env
git commit -m "feat: add Docker socket and network for DockerSpawner"
```

---

## Task 5: Postman collection ✅ DONE

Collection `JupyterHub API` and environment `JupyterHub Local` already exist in the PayPal workspace. No changes needed — the API calls are identical regardless of spawner type.

---

## Task 6: End-to-End Verification 🔄 UPDATE

Verifies isolation (each user = separate container) and ephemeral behavior (container removed on stop).

- [ ] **Step 1: Confirm hub is running**

```bash
docker compose logs --tail=3
```

Expected: `JupyterHub is now running at http://0.0.0.0:8000/`

- [ ] **Step 2: Create user via API**

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST \
  http://localhost:8000/hub/api/users/jupyter_user \
  -H "Authorization: token super-secret-paypal-token-2026"
```

Expected: `HTTP 201` or `HTTP 409` (already exists)

- [ ] **Step 3: Start notebook server via API**

```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST \
  http://localhost:8000/hub/api/users/jupyter_user/server \
  -H "Authorization: token super-secret-paypal-token-2026" \
  -H "Content-Type: application/json" -d "{}"
```

Expected: `HTTP 201` or `HTTP 202`

- [ ] **Step 4: Verify a Docker container was created for the user**

```bash
docker ps --filter "name=jupyter-" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
```

Expected: a container named `jupyter-jupyter_user` using image `jupyter-paypal-singleuser:latest`

- [ ] **Step 5: Verify server is ready and files are accessible**

```bash
curl -s http://localhost:8000/hub/api/users/jupyter_user \
  -H "Authorization: token super-secret-paypal-token-2026" \
  | python -m json.tool | grep -E '"ready"|"url"'
```

Expected:
```
"ready": true,
"url": "/user/jupyter_user/",
```

```bash
curl -s "http://localhost:8000/user/jupyter_user/api/contents/" \
  -H "Authorization: token super-secret-paypal-token-2026" \
  | python -c "import sys,json; [print(i['type'], i['name']) for i in json.load(sys.stdin)['content']]"
```

Expected: `directory notebooks`, `directory data`, `directory src`

- [ ] **Step 6: Verify notebook and dataset are present**

```bash
curl -s "http://localhost:8000/user/jupyter_user/api/contents/notebooks" \
  -H "Authorization: token super-secret-paypal-token-2026" \
  | python -c "import sys,json; [print(i['name']) for i in json.load(sys.stdin)['content']]"
```

Expected: `loan_risk_analysis.ipynb`

- [ ] **Step 7: Stop the server and verify container is removed (ephemeral)**

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X DELETE \
  http://localhost:8000/hub/api/users/jupyter_user/server \
  -H "Authorization: token super-secret-paypal-token-2026"
```

Expected: `HTTP 204`

```bash
sleep 3 && docker ps --filter "name=jupyter-jupyter_user" --format "{{.Names}}"
```

Expected: **empty output** — container was destroyed.

- [ ] **Step 8: Final commit**

```bash
git add .
git commit -m "feat: complete isolated ephemeral JupyterHub setup with DockerSpawner"
```

---

## Key Design Decisions

| Decision | Reason |
|----------|--------|
| **DockerSpawner over SimpleLocalProcessSpawner** | True OS-level isolation — each user runs in a separate container with its own filesystem, process space, and network namespace |
| **`DockerSpawner.remove = True`** | Container destroyed on stop = ephemeral. User state doesn't persist between sessions |
| **Separate `singleuser/Dockerfile`** | Hub image doesn't need analysis libs; singleuser image doesn't need the hub proxy. Smaller, purpose-built images |
| **`HOST_PROJECT_PATH` env var** | DockerSpawner runs inside a container but creates sibling containers on the host daemon — it needs host-absolute paths, not container-internal paths |
| **Named network `jupyterhub-network`** | Hub and spawned containers must be on the same Docker network for the hub proxy to reach them |
| **Notebooks/data/src not mounted in hub** | The hub doesn't need these files — only the spawned user containers do |
