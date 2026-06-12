FROM quay.io/jupyter/base-notebook:latest

# Disable user-local installs (pip install --user) and skip the download cache
ENV PYTHONNOUSERSITE=1 \
    PIP_NO_CACHE_DIR=1

# Install packages while /opt/conda is still writable (before the lockdown below)
COPY requirements.txt /tmp/requirements.txt
RUN mamba install --yes --quiet --channel conda-forge --file /tmp/requirements.txt \
    && mamba clean --all -f -y

USER root

# 1. Lock down the Python/conda environment
#    Transfer ownership to root and set 755 so jovyan can read/execute but not write.
#    This prevents any global package installation even via `python -m pip`.
RUN chown -R root:root /opt/conda \
    && chmod -R 755 /opt/conda

# 2. Disable the Jupyter terminal to block direct shell access
#    ServerApp covers JupyterLab / Jupyter Server; NotebookApp covers classic Notebook.
RUN mkdir -p /etc/jupyter \
    && printf '%s\n' \
        'c.ServerApp.terminals_enabled = False' \
        'c.NotebookApp.terminals_enabled = False' \
       > /etc/jupyter/jupyter_server_config.py

# 3. Block shell execution and package-manager magics inside notebooks
#    - ip.system intercepts !cmd bang-shell calls and raises instead of executing
#    - Removing line magics disables %pip, %conda, and %mamba install shortcuts
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

# Switch back to the default notebook user
USER ${NB_UID}
