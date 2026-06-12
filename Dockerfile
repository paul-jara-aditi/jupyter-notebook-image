FROM python:3.11-slim

ENV PYTHONNOUSERSITE=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt /tmp/

# Install Node.js (required by configurable-http-proxy, JupyterHub's default proxy)
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && npm install -g configurable-http-proxy \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Jupyter, JupyterHub, and analysis libraries as root
RUN pip install jupyter jupyterhub -r /tmp/requirements.txt

COPY start.sh /start.sh
RUN chmod +x /start.sh

# Create unprivileged user that JupyterHub will spawn servers as
RUN useradd -ms /bin/bash jupyter_user

WORKDIR /home/jupyter_user
RUN mkdir -p \
    notebooks \
    data/raw \
    data/processed \
    data/external \
    src \
    && chown -R jupyter_user:jupyter_user /home/jupyter_user

COPY --chown=jupyter_user:jupyter_user notebooks/ ./notebooks/
COPY --chown=jupyter_user:jupyter_user data/ ./data/

# JupyterHub state files go here (writable by root)
RUN mkdir -p /var/lib/jupyterhub

# Hub runs as root so LocalProcessSpawner can setuid to jupyter_user
EXPOSE 8000

CMD ["/start.sh"]
