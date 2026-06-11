#!/bin/bash
set -e

if [ -z "${JUPYTER_TOKEN}" ]; then
  echo "ERROR: JUPYTER_TOKEN must be set in .env (see .env.example)" >&2
  exit 1
fi

exec jupyter notebook --ip=0.0.0.0 --port=8888 --no-browser \
  --ServerApp.token="${JUPYTER_TOKEN}"
