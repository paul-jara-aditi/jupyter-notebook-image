# Jupyter Notebook Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the singleuser Jupyter container to block notebook downloads and add layered security controls (resource limits, read-only data, idle culling, security headers).

**Architecture:** A Jupyter Server extension installed into the singleuser image intercepts the `/nbconvert/` and `/files/` URL routes before the built-in handlers — Tornado prepends `add_handlers` entries, so extension handlers win. Additional controls live in `jupyterhub_config.py` (spawner-level limits applied by the Hub before each container starts).

**Tech Stack:** Python, Jupyter Server 2.x extension API, DockerSpawner, Tornado, Docker Compose.

---

## What is already hardened (do NOT re-implement)

| Control | Location |
|---|---|
| conda/pip environment locked to root | `singleuser/Dockerfile` |
| Terminal disabled | `singleuser/Dockerfile` `/etc/jupyter/jupyter_server_config.py` |
| `!cmd` bang-shell blocked | `singleuser/Dockerfile` startup script |
| `%pip / %conda / %mamba` magics removed | `singleuser/Dockerfile` startup script |
| Ephemeral containers (removed on stop) | `jupyterhub_config.py` `c.DockerSpawner.remove = True` |
| Per-user isolated containers | `jupyterhub_config.py` DockerSpawner |
| AUTH_SERVICE_TOKEN injected | `jupyterhub_config.py` `pre_spawn_hook` |

---

## File Structure

| Action | Path | Responsibility |
|---|---|---|
| Create | `singleuser/extensions/block_download/__init__.py` | Jupyter Server extension: blocks `/nbconvert/` and `/files/` |
| Create | `singleuser/extensions/block_download/pyproject.toml` | Makes the extension installable as a Python package |
| Create | `singleuser/jupyter_server_config.py` | Enables the extension + HTTP security headers |
| Modify | `singleuser/Dockerfile` | Copy + pip-install the extension, copy config |
| Modify | `jupyterhub_config.py` | Resource limits, read-only data volume, idle culling |

---

## Task 1: Create the block-download Jupyter Server extension

**Files:**
- Create: `singleuser/extensions/block_download/__init__.py`
- Create: `singleuser/extensions/block_download/pyproject.toml`

- [ ] **Step 1: Create the extension package directory**

```powershell
New-Item -ItemType Directory -Force "singleuser/extensions/block_download"
```

- [ ] **Step 2: Write the extension module**

Create `singleuser/extensions/block_download/__init__.py` with this exact content:

```python
from jupyter_server.base.handlers import JupyterHandler
from jupyter_server.extension.application import ExtensionApp
from tornado import web


class BlockedHandler(JupyterHandler):
    async def get(self, *args, **kwargs):
        self.set_status(403)
        await self.finish({"message": "Downloading notebooks is disabled in this environment."})


class BlockDownloadApp(ExtensionApp):
    name = "block_download"

    def initialize_handlers(self):
        self.handlers = [
            (r"/nbconvert/.*", BlockedHandler),
            (r"/files/.*", BlockedHandler),
        ]


def _jupyter_server_extension_points():
    return [{"app": BlockDownloadApp}]
```

**Why this works:** Jupyter Server calls `webapp.add_handlers(".*$", prepared_handlers)` for each extension. Tornado's `add_handlers` *prepends* to the handler list, so the extension handler is evaluated before the built-in `/nbconvert/` and `/files/` handlers and wins with 403.

- [ ] **Step 3: Write the pyproject.toml**

Create `singleuser/extensions/block_download/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "block_download"
version = "0.1.0"
requires-python = ">=3.8"
dependencies = ["jupyter_server>=2.0"]

[tool.setuptools.packages.find]
where = ["."]
```

- [ ] **Step 4: Verify the package structure looks correct**

```powershell
Get-ChildItem -Recurse singleuser/extensions/
```

Expected output:
```
block_download/
    __init__.py
    pyproject.toml
```

---

## Task 2: Create the singleuser Jupyter Server config

**Files:**
- Create: `singleuser/jupyter_server_config.py`

- [ ] **Step 1: Write the config file**

Create `singleuser/jupyter_server_config.py`:

```python
# Enable the block-download extension installed into the image
c.ServerApp.jpserver_extensions = {
    "block_download": True,
}

# HTTP security headers served with every notebook response
c.ServerApp.tornado_settings = {
    "headers": {
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        ),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
    }
}
```

**Why `frame-ancestors 'none'`:** Prevents this Jupyter instance from being embedded in an iframe on another origin, blocking clickjacking attacks.

---

## Task 3: Update the singleuser Dockerfile

**Files:**
- Modify: `singleuser/Dockerfile`

- [ ] **Step 1: Add the COPY + RUN steps for the extension and config**

Open `singleuser/Dockerfile`. After the existing `COPY singleuser/requirements.txt` block and before the `USER root` section, add:

```dockerfile
# Install the block-download server extension (blocks /nbconvert/ and /files/)
COPY singleuser/extensions/ /tmp/extensions/
RUN pip install --no-cache-dir /tmp/extensions/block_download/

# Bake the Jupyter Server config (enables the extension + security headers)
COPY singleuser/jupyter_server_config.py /etc/jupyter/jupyter_server_config.py
```

The full Dockerfile should look like this after the edit:

```dockerfile
FROM quay.io/jupyter/base-notebook:latest

ENV PYTHONNOUSERSITE=1 \
    PIP_NO_CACHE_DIR=1

# Install packages while /opt/conda is still writable (before the lockdown below)
COPY singleuser/requirements.txt /tmp/requirements.txt
RUN mamba install --yes --quiet --channel conda-forge --file /tmp/requirements.txt \
    && mamba clean --all -f -y

# Bake template notebooks into the image — each container starts with a fresh copy.
COPY notebooks/ /home/jovyan/work/notebooks/

# Install the block-download server extension (blocks /nbconvert/ and /files/)
COPY singleuser/extensions/ /tmp/extensions/
RUN pip install --no-cache-dir /tmp/extensions/block_download/

# Bake the Jupyter Server config (enables the extension + security headers)
COPY singleuser/jupyter_server_config.py /etc/jupyter/jupyter_server_config.py

USER root

# 1. Lock down the Python/conda environment
RUN chown -R root:root /opt/conda \
    && chmod -R 755 /opt/conda

# 2. Disable the Jupyter terminal
RUN mkdir -p /etc/jupyter \
    && printf '%s\n' \
        'c.ServerApp.terminals_enabled = False' \
        'c.NotebookApp.terminals_enabled = False' \
       >> /etc/jupyter/jupyter_server_config.py

# 3. Block shell execution and package-manager magics inside notebooks
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

**Note on `>>` vs `>`:** We append (`>>`) terminal settings to the existing `jupyter_server_config.py` (which is copied via COPY) so we don't overwrite the extension enablement and security headers already written by the COPY step.

- [ ] **Step 2: Build the image to verify it builds cleanly**

```powershell
docker build -t jupyter-paypal-singleuser:latest -f singleuser/Dockerfile .
```

Expected: build completes without errors. The `pip install` step should show `Successfully installed block-download-0.1.0`.

- [ ] **Step 3: Smoke-test the extension is loaded**

```powershell
docker run --rm jupyter-paypal-singleuser:latest jupyter server extension list
```

Expected output includes:
```
block_download  enabled
```

- [ ] **Step 4: Commit**

```bash
git add singleuser/extensions/ singleuser/jupyter_server_config.py singleuser/Dockerfile
git commit -m "feat(singleuser): block notebook downloads via Jupyter Server extension"
```

---

## Task 4: Add resource limits and read-only data volume

**Files:**
- Modify: `jupyterhub_config.py`

- [ ] **Step 1: Add CPU, memory limits and read-only data mount**

In `jupyterhub_config.py`, replace the existing `c.DockerSpawner.volumes` block and add resource limits:

```python
# Mount data read-only — users can query data via the auth-service API but
# cannot modify the source files on the host.
c.DockerSpawner.volumes = {
    f'{host_path}/data': {'bind': '/home/jovyan/work/data', 'mode': 'ro'},
    f'{host_path}/src':  '/home/jovyan/work/src',
}

# Limit each singleuser container to 1 CPU and 1 GB RAM.
# cpu_quota / cpu_period = 1.0 CPU core.
c.DockerSpawner.extra_host_config = {
    "cpu_period": 100_000,
    "cpu_quota":  100_000,
    "mem_limit":  "1g",
    "memswap_limit": "1g",  # disable swap (same as mem_limit = no extra swap)
}
```

- [ ] **Step 2: Verify the config parses without error**

```powershell
python -c "exec(open('jupyterhub_config.py').read()); print('OK')"
```

Expected: `OK` (no Python syntax errors).

- [ ] **Step 3: Commit**

```bash
git add jupyterhub_config.py
git commit -m "feat(hub): read-only data mount, CPU/memory limits per spawned container"
```

---

## Task 5: Add idle server culling

**Files:**
- Modify: `jupyterhub_config.py`
- Modify: `hub/requirements.txt`

JupyterHub ships a built-in idle culler since 2.x. We enable it as an internal service.

- [ ] **Step 1: Add the idle-culler service to jupyterhub_config.py**

Add this block at the bottom of `jupyterhub_config.py`:

```python
# Auto-stop idle notebook servers after 30 minutes of no kernel activity.
# The culler is a managed service that runs inside the Hub container.
c.JupyterHub.load_roles = [
    {
        "name": "jupyterhub-idle-culler-role",
        "description": "Cull idle single-user servers",
        "scopes": [
            "list:users",
            "read:users:activity",
            "read:servers",
            "delete:servers",
        ],
        "services": ["jupyterhub-idle-culler"],
    }
]
c.JupyterHub.services = [
    {
        "name": "jupyterhub-idle-culler",
        "command": [
            "python3",
            "-m", "jupyterhub_idle_culler",
            "--timeout=1800",   # 30 minutes in seconds
            "--cull-every=300", # check every 5 minutes
        ],
    }
]
```

- [ ] **Step 2: Install jupyterhub-idle-culler in the hub image**

Open `hub/requirements.txt` and add:

```
jupyterhub-idle-culler
```

- [ ] **Step 3: Rebuild the hub image**

```powershell
docker compose build jupyter
```

Expected: hub image rebuilds and includes `jupyterhub-idle-culler`.

- [ ] **Step 4: Commit**

```bash
git add jupyterhub_config.py hub/requirements.txt
git commit -m "feat(hub): auto-stop idle notebook servers after 30 minutes"
```

---

## Task 6: End-to-end smoke tests

These tests verify the hardening controls work. Run them after `docker compose up -d`.

- [ ] **Test 1 — nbconvert endpoint is blocked**

From a terminal (replace `<token>` with a valid JupyterHub token):

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: token <token>" \
  http://localhost:8000/user/<username>/nbconvert/script/work/notebooks/demo.ipynb
```

Expected: `403`

- [ ] **Test 2 — files endpoint is blocked**

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: token <token>" \
  http://localhost:8000/user/<username>/files/work/notebooks/demo.ipynb
```

Expected: `403`

- [ ] **Test 3 — notebook can still be opened (contents API unaffected)**

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: token <token>" \
  "http://localhost:8000/user/<username>/api/contents/work/notebooks/demo.ipynb?content=1"
```

Expected: `200` (opening in the editor still works)

- [ ] **Test 4 — security headers are present**

```bash
curl -sI -H "Authorization: token <token>" \
  http://localhost:8000/user/<username>/lab \
  | grep -E "X-Frame|X-Content|Content-Security"
```

Expected: headers `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy` are present.

- [ ] **Test 5 — data directory is read-only**

In a notebook cell:

```python
open('/home/jovyan/work/data/test_write.txt', 'w').write('hello')
```

Expected: `PermissionError: [Errno 30] Read-only file system: '/home/jovyan/work/data/test_write.txt'`

- [ ] **Step 6: Commit if all tests pass**

```bash
git add .
git commit -m "test: verify hardening controls (manual smoke test results OK)"
```

---

## Limitations and future work

| Limitation | Explanation |
|---|---|
| JupyterLab "Download" button in the UI | When a user clicks Download in JupyterLab, the browser calls `GET /api/contents/<path>?content=1` (same as opening the file) then creates a Blob URL client-side. There is no server-side distinction between "open" and "download". Full suppression requires a JupyterLab TypeScript frontend extension to remove the `docmanager:download` command from the UI. |
| `src` volume is still writable | Users can write files to `/home/jovyan/work/src`. If the src directory contains helper modules loaded by notebooks, assess whether `:ro` is appropriate. |
| No network egress restriction | singleuser containers share `jupyterhub-network` and can reach any host reachable from Docker's bridge. Consider a dedicated restricted network with explicit allow-list for auth-service only. |
