import os

# Hub network
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000

# State files
c.JupyterHub.db_url = 'sqlite:////var/lib/jupyterhub/jupyterhub.sqlite'
c.JupyterHub.cookie_secret_file = '/var/lib/jupyterhub/jupyterhub_cookie_secret'

# DummyAuthenticator: any password accepted — OK for local dev containers
c.JupyterHub.authenticator_class = 'dummy'
c.DummyAuthenticator.password = 'paypal'

c.Authenticator.allowed_users = {'jupyter_user'}
c.Authenticator.admin_users = {'jupyter_user'}

# DockerSpawner: each user gets an isolated, ephemeral container
c.JupyterHub.spawner_class = 'dockerspawner.DockerSpawner'
c.DockerSpawner.image = 'jupyter-paypal-singleuser:latest'
c.DockerSpawner.network_name = 'jupyterhub-network'
c.DockerSpawner.remove = True          # destroy container when server stops (ephemeral)
c.DockerSpawner.notebook_dir = '/home/jovyan/work'
c.DockerSpawner.default_url = '/tree/notebooks'

# Mount host notebooks/data/src into each spawned container.
# HOST_PROJECT_PATH must be the absolute host path to this project dir (set in .env).
host_path = os.environ.get('HOST_PROJECT_PATH', '').rstrip('/').rstrip('\\')
c.DockerSpawner.volumes = {
    f'{host_path}/notebooks': '/home/jovyan/work/notebooks',
    f'{host_path}/data':      '/home/jovyan/work/data',
    f'{host_path}/src':       '/home/jovyan/work/src',
}

# Admin API token
api_token = os.environ.get('JUPYTERHUB_API_TOKEN', '')
if api_token:
    c.JupyterHub.api_tokens = {api_token: 'jupyter_user'}
