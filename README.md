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
├── requirements.txt               # Pinned Python dependencies
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

```bash
docker compose up --build
```

Then open [http://localhost:8888](http://localhost:8888) in your browser.

Notebooks and data are mounted as volumes, so edits are persisted locally without rebuilding.

### Option 2 — Dockerfile only

```bash
docker build -t jupyter-paypal .
docker run -p 8888:8888 jupyter-paypal
```

### Option 3 — Local (uv)

```bash
uv sync
uv run jupyter notebook
```

## Security

The container runs as an **unprivileged user** (`jupyter_user`). All Python packages are installed as root into `/usr/local/lib/`, making them read-only to the notebook user. No authentication token is required in the local dev setup — do not expose port 8888 publicly.
