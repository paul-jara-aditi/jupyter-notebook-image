# Plan: Add Jupyter Token Authentication

## Context

The original setup explicitly disabled Jupyter authentication by passing `--ServerApp.token=''` and `--ServerApp.password=''` in both `Dockerfile` and the inline `docker-compose.yml` dockerfile. A `.env.example` with `JUPYTER_TOKEN=change-me-to-a-strong-password` existed but was never wired up. The goal was to connect that env var to the Jupyter startup so the notebook server requires a password before granting access.

---

## Changes Made

### 1. `start.sh` (new file)

A startup script that validates `JUPYTER_TOKEN` is set and non-empty before launching Jupyter. If the variable is missing, the container exits immediately with a clear error message.

```bash
#!/bin/bash
set -e

if [ -z "${JUPYTER_TOKEN}" ]; then
  echo "ERROR: JUPYTER_TOKEN must be set in .env (see .env.example)" >&2
  exit 1
fi

exec jupyter notebook --ip=0.0.0.0 --port=8888 --no-browser \
  --ServerApp.token="${JUPYTER_TOKEN}"
```

### 2. `Dockerfile`

- Added `COPY start.sh /start.sh` and `RUN chmod +x /start.sh` (as root, before the user switch)
- Replaced the `CMD` that disabled auth with `CMD ["/start.sh"]`

```dockerfile
# After pip install, before USER switch:
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Replaces the old CMD with disabled auth:
CMD ["/start.sh"]
```

### 3. `docker-compose.yml`

- Switched from `dockerfile_inline` to `dockerfile: Dockerfile` — `COPY` does not work with inline Dockerfiles in Compose
- Added `env_file: .env` so Docker Compose injects `JUPYTER_TOKEN` from the local `.env` file into the container

```yaml
services:
   jupyter:
      env_file: .env
      build:
         context: docs
         dockerfile: Dockerfile
```

### 4. `README.md`

- Updated setup steps to include copying `.env.example` to `.env` before running
- Updated the Security section to document the token requirement
- Added `-e JUPYTER_TOKEN=...` to the standalone `docker run` example

---

## File Summary

| File | Change |
|------|--------|
| `start.sh` | Created — entrypoint with token validation |
| `Dockerfile` | Added COPY/chmod for `start.sh`, replaced CMD |
| `docker-compose.yml` | Switched to `dockerfile: Dockerfile`, added `env_file` |
| `README.md` | Updated setup and security documentation |

---

## Verification

1. Copy `.env.example` to `.env` and set a strong token:
   ```bash
   cp .env.example .env
   # Edit .env: JUPYTER_TOKEN=my-strong-password
   ```
2. Build and start:
   ```bash
   docker compose up --build
   ```
3. Open `http://localhost:8888` — should show the Jupyter login page
4. Enter the token — should grant access to notebooks

**Error case:** Set `JUPYTER_TOKEN=` (empty) in `.env` and restart. The container should exit immediately with:
```
ERROR: JUPYTER_TOKEN must be set in .env (see .env.example)
```
