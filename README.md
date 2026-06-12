# JupyterHub — Loan Risk Analysis

JupyterHub with role-based authentication. Each user gets an isolated, ephemeral Jupyter container started on demand. An Auth Service (POC) handles login and role-based access to Big Data views.

## Requirements

- Docker Desktop (with Docker Compose v2)

## Setup

**1. Create a `.env` file in the project root:**

```env
JUPYTERHUB_API_TOKEN=super-secret-paypal-token-2026
HOST_PROJECT_PATH=C:/Users/<your-user>/path/to/jupyter-notebook-image
```

**2. Build the singleuser image:**

```bash
docker build -t jupyter-paypal-singleuser:latest ./singleuser
```

**3. Start all services:**

```bash
docker compose up --build -d
```

## Docker Images

| Dockerfile | Image | Role |
|---|---|---|
| `Dockerfile` | `jupyter-paypal` | Hub orchestrator (port 8000) |
| `singleuser/Dockerfile` | `jupyter-paypal-singleuser` | Ephemeral workspace per user |
| `auth-service/Dockerfile` | `auth-paypal` | Auth Service (port 8001) |

## Auth Service

### Credentials

| Email | Password | Role | Table |
|-------|----------|------|-------|
| sales@company.com | sales123 | sales | `risk` |
| marketing@company.com | marketing123 | marketing | `fraud` |
| collections@company.com | collections123 | collections | `average_debt` |

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/login` | Login — returns `token` and `role` |
| `GET` | `/dashboard` | Big Data table for the authenticated role |
| `POST` | `/auth/jupyter-launch` | Launches a notebook and returns a direct URL |
| `GET` | `/health` | Health check |

### Flow from Postman

1. **Login** → saves `{{token}}`
2. **Jupyter Launch** → saves `{{jupyter_url}}`
3. Open `{{jupyter_url}}` in the browser — opens Jupyter without a login form

> Import the **Auth Service** collection and the **JupyterHub Local** environment from the PayPal workspace in Postman.

## Useful Commands

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs
docker compose logs -f

# Rebuild after changes to Dockerfile or requirements.txt
docker compose up --build -d

# Rebuild singleuser image
docker build -t jupyter-paypal-singleuser:latest ./singleuser

# Reload config without rebuild (jupyterhub_config.py changes)
docker compose restart
```
