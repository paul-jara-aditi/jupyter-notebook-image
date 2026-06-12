# JupyterHub — Loan Risk Analysis

JupyterHub environment for loan risk analysis. Each user gets an isolated, ephemeral Jupyter Notebook container started on demand via the JupyterHub REST API.

## Architecture

```
Postman / Browser
       │
       ▼  :8000
┌─────────────────────┐
│   JupyterHub (hub)  │  ← Docker container: jupyter-paypal
│   DummyAuthenticator│
│   DockerSpawner     │──── /var/run/docker.sock
└─────────────────────┘
       │  API call: POST /hub/api/users/{user}/server
       ▼
┌─────────────────────┐
│  Notebook container │  ← Created per user, destroyed on stop
│  jupyter-paypal-    │
│  singleuser:latest  │
│                     │
│  /home/jovyan/work/ │
│    notebooks/  ─────┼── bind mount → ./notebooks
│    data/       ─────┼── bind mount → ./data
│    src/        ─────┼── bind mount → ./src
└─────────────────────┘
```

- **Isolated**: each user runs in their own Docker container
- **Ephemeral**: container is destroyed when the server is stopped (`DockerSpawner.remove = True`)
- **Pre-loaded**: `loan_risk_analysis.ipynb` and `german_credit.csv` are available on start

---

## Prerequisites

- Docker Desktop (with Docker Compose v2)
- Postman (desktop app)
- Node.js is bundled inside the hub image — no local install needed

---

## Setup

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd jupyter-notebook-image
```

Create a `.env` file in the project root:

```env
JUPYTERHUB_API_TOKEN=super-secret-paypal-token-2026
HOST_PROJECT_PATH=C:/Users/<your-user>/path/to/jupyter-notebook-image
```

> `HOST_PROJECT_PATH` must be the **absolute path on your host machine** using forward slashes.
> Example on Windows: `C:/Users/john/workspace/jupyter-notebook-image`
> Example on Mac/Linux: `/home/john/workspace/jupyter-notebook-image`

### 2. Build the singleuser image

This image is used by DockerSpawner to create user containers.

```bash
docker build -t jupyter-paypal-singleuser:latest -f Dockerfile.singleuser .
```

### 3. Start JupyterHub

```bash
docker compose up --build -d
```

Verify the hub is running:

```bash
docker compose logs --tail=5
# Expected: JupyterHub is now running at http://0.0.0.0:8000/
```

---

## Usage

### Via browser (manual login)

1. Open `http://localhost:8000`
2. Log in with username `jupyter_user` and password `paypal`
3. JupyterHub starts a notebook server automatically on login
4. Navigate to `notebooks/loan_risk_analysis.ipynb`

### Via Postman (API)

Import the **JupyterHub API** collection from the **PayPal** workspace in Postman and select the **JupyterHub Local** environment.

| Step | Request | Method | Endpoint |
|------|---------|--------|----------|
| 1 | Create User | `POST` | `/hub/api/users/{{username}}` |
| 2 | Start Server | `POST` | `/hub/api/users/{{username}}/server` |
| 3 | Get Status | `GET` | `/hub/api/users/{{username}}` |
| 4 | Stop Server | `DELETE` | `/hub/api/users/{{username}}/server` |

All requests use `Authorization: token {{api_token}}` header.

### Via curl (quick test)

```bash
# Start a notebook server
curl -X POST http://localhost:8000/hub/api/users/jupyter_user/server \
  -H "Authorization: token super-secret-paypal-token-2026" \
  -H "Content-Type: application/json" \
  -d "{}"

# Check status
curl http://localhost:8000/hub/api/users/jupyter_user \
  -H "Authorization: token super-secret-paypal-token-2026"

# Stop the server (destroys the container)
curl -X DELETE http://localhost:8000/hub/api/users/jupyter_user/server \
  -H "Authorization: token super-secret-paypal-token-2026"
```

Once started, the notebook server is available at:
`http://localhost:8000/user/jupyter_user/`

---

## Project structure

```
.
├── Dockerfile              # Hub image (JupyterHub + Node.js + configurable-http-proxy)
├── Dockerfile.singleuser   # User container image (Jupyter + analysis libs)
├── docker-compose.yml      # Hub service + jupyterhub-network
├── jupyterhub_config.py    # JupyterHub configuration (DockerSpawner, auth, tokens)
├── start.sh                # Hub entrypoint
├── requirements.txt        # Python dependencies (shared by both images)
├── notebooks/
│   └── loan_risk_analysis.ipynb
├── data/
│   └── raw/
│       └── german_credit.csv
└── src/
```

---

## Configuration reference

All configuration lives in `jupyterhub_config.py`, which is mounted as a volume — changes take effect after `docker compose restart` without a full rebuild.

| Setting | Value | Description |
|---------|-------|-------------|
| `hub_url` | `http://localhost:8000` | JupyterHub public URL |
| `hub_ip` | `0.0.0.0` | Hub API must bind to all interfaces so spawned containers can reach it |
| `authenticator` | `DummyAuthenticator` | Any password accepted — for local dev only |
| `password` | `paypal` | Login password for all users |
| `spawner` | `DockerSpawner` | Spawns a Docker container per user |
| `singleuser image` | `jupyter-paypal-singleuser:latest` | Built from `Dockerfile.singleuser` |
| `network` | `jupyterhub-network` | Docker network shared by hub and user containers |
| `remove` | `True` | Container destroyed when server stops (ephemeral) |

### Environment variables (`.env`)

| Variable | Description |
|----------|-------------|
| `JUPYTERHUB_API_TOKEN` | Admin token for API requests — use in Postman `Authorization: token <value>` |
| `HOST_PROJECT_PATH` | Absolute host path to the project root — used for volume mounts in spawned containers |

---

## Common commands

```bash
# Start hub
docker compose up -d

# Stop hub
docker compose down

# Rebuild hub image (e.g. after changing Dockerfile or requirements.txt)
docker compose up --build -d

# Rebuild singleuser image (e.g. after changing Dockerfile.singleuser)
docker build -t jupyter-paypal-singleuser:latest -f Dockerfile.singleuser .

# Reload config without rebuild (jupyterhub_config.py changes)
docker compose restart

# View hub logs
docker compose logs -f

# List running user containers
docker ps --filter "name=jupyter-jupyter" --format "table {{.Names}}\t{{.Status}}"

# Remove all stopped user containers manually
docker container prune -f
```

---

## Postman environment variables

| Variable | Value |
|----------|-------|
| `hub_url` | `http://localhost:8000` |
| `api_token` | `super-secret-paypal-token-2026` |
| `username` | `jupyter_user` |
