# Jupyter Notebook Image

A Dockerized Jupyter Notebook environment

## Overview

This project packages a reproducible data analysis environment into a Docker image.

## Project Structure

```
jupyter-notebook-image/
├── notebooks/
│   └── loan_risk_analysis.ipynb   # Notebook example
├── data/
│   ├── raw/
│   │   └── german_credit.csv      # Source dataset. Example
│   ├── processed/                 # Cleaned/transformed data
│   └── external/                  # Third-party data sources
├── src/                           # Python modules (if any)
├── Dockerfile                     # Standalone image definition
├── docker-compose.yml             # Compose-based dev environment
├── start.sh                       # Container entrypoint (validates JUPYTER_TOKEN)
├── requirements.txt               # Pinned Python dependencies
├── .env.example                   # Environment variable template
└── pyproject.toml                 # Project metadata
```

## Dependencies

| Package      | Version |
|-------------|---------|
| pandas       | 2.2.0   |
| numpy        | 1.26.4  |
| matplotlib   | 3.8.2   |
| seaborn      | 0.13.2  |
| pyarrow      | 15.0.0  |

Python 3.11 required.

## Getting Started

### Option 1 — Docker Compose (recommended)

1. Copy the env template and set a strong token:
   ```bash
   cp .env.example .env
   # Edit .env and set JUPYTER_TOKEN to a strong password
   ```

2. Build and start:
   ```bash
   docker compose up --build
   ```

3. Open [http://localhost:8888](http://localhost:8888) and enter your token to log in.

Notebooks and data are mounted as volumes, so edits are persisted locally without rebuilding.

### Option 2 — Dockerfile only

```bash
docker build -t jupyter-paypal .
docker run -p 8888:8888 -e JUPYTER_TOKEN=your-token-here jupyter-paypal
```

### Option 3 — Local (uv)

```bash
uv sync
uv run jupyter notebook
```

## Security

The container runs as an **unprivileged user** (`jupyter_user`). All Python packages are installed as root into `/usr/local/lib/`, making them read-only to the notebook user.

Access is protected by a token set via the `JUPYTER_TOKEN` environment variable. The container will refuse to start if `JUPYTER_TOKEN` is not set. Copy `.env.example` to `.env` and set a strong value before running. Do not expose port 8888 publicly.
