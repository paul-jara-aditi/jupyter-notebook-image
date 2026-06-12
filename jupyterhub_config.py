import os

# Hub network
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000

# State files location (writable by root, outside volume-mounted dirs)
c.JupyterHub.db_url = 'sqlite:////var/lib/jupyterhub/jupyterhub.sqlite'
c.JupyterHub.cookie_secret_file = '/var/lib/jupyterhub/jupyterhub_cookie_secret'

# DummyAuthenticator: any password accepted — OK for local dev containers
c.JupyterHub.authenticator_class = 'dummy'
c.DummyAuthenticator.password = 'paypal'

# Allow jupyter_user to log in and mark as admin
c.Authenticator.allowed_users = {'jupyter_user'}
c.Authenticator.admin_users = {'jupyter_user'}

# SimpleLocalProcessSpawner: spawns notebook server as the same user as the hub (root)
# --allow-root is required because the hub runs as root inside Docker
c.JupyterHub.spawner_class = 'simple'
c.Spawner.notebook_dir = '/home/jupyter_user'
c.Spawner.default_url = '/tree/notebooks'
c.Spawner.args = ['--allow-root']

# Admin API token — read from env var set in docker-compose / .env
api_token = os.environ.get('JUPYTERHUB_API_TOKEN', '')
if api_token:
    c.JupyterHub.api_tokens = {api_token: 'jupyter_user'}
