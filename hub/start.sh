#!/bin/bash
set -e

if [ -z "${JUPYTERHUB_API_TOKEN}" ]; then
  echo "ERROR: JUPYTERHUB_API_TOKEN must be set in .env" >&2
  exit 1
fi

exec jupyterhub \
  --config /home/jupyter_user/jupyterhub_config.py \
  --JupyterHub.db_url=sqlite:////var/lib/jupyterhub/jupyterhub.sqlite
