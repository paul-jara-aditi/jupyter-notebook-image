import os
from jupyterhub.handlers import BaseHandler
from jupyterhub import orm
from tornado import web


class TokenAutoLoginHandler(BaseHandler):
    """Exchange a Hub API token for a browser session.

    GET /hub/token-login?token=<api_token>[&next=<path>]

    Validates the token against the Hub DB, sets the session cookie, and
    redirects to `next`. This sidesteps the URL-token auth that was removed
    in JupyterHub 4.x for security reasons.
    """

    async def get(self):
        token_str = self.get_argument("token", "")
        if not token_str:
            raise web.HTTPError(400, "token parameter required")

        orm_token = orm.APIToken.find(self.db, token_str)
        if orm_token is None:
            raise web.HTTPError(403, "Invalid or expired token")

        user = self.users[orm_token.user.name]
        self.set_login_cookie(user)
        next_url = self.get_argument("next", f"/user/{orm_token.user.name}/")
        self.redirect(next_url)


# Hub network
c.JupyterHub.ip = '0.0.0.0'
c.JupyterHub.port = 8000
# hub_ip must be 0.0.0.0 so spawned containers can reach the hub API via Docker network
c.JupyterHub.hub_ip = '0.0.0.0'

# State files
c.JupyterHub.db_url = 'sqlite:////var/lib/jupyterhub/jupyterhub.sqlite'
c.JupyterHub.cookie_secret_file = '/var/lib/jupyterhub/jupyterhub_cookie_secret'

# DummyAuthenticator: any password accepted — OK for local dev containers
c.JupyterHub.authenticator_class = 'dummy'
c.DummyAuthenticator.password = 'paypal'

# allow_all lets any username authenticate — usernames are now derived from email
# addresses (e.g. sales_company_com) and cannot be hardcoded.
# Access is controlled by the auth-service: only authenticated users receive a Hub
# API token that can reach /hub/token-login.
c.Authenticator.allow_all = True
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
# notebooks is intentionally absent — it is baked into the image and is ephemeral.
c.DockerSpawner.volumes = {
    f'{host_path}/data': '/home/jovyan/work/data',
    f'{host_path}/src':  '/home/jovyan/work/src',
}

async def pre_spawn_hook(spawner):
    token = spawner.user_options.get('AUTH_SERVICE_TOKEN', '')
    if token:
        spawner.environment['AUTH_SERVICE_TOKEN'] = token


c.Spawner.pre_spawn_hook = pre_spawn_hook

# Admin API token
api_token = os.environ.get('JUPYTERHUB_API_TOKEN', '')
if api_token:
    c.JupyterHub.api_tokens = {api_token: 'jupyter_user'}

# Custom handler: exchanges a Hub API token for a browser session cookie.
# Note: hub_prefix (/hub) is prepended automatically by add_url_prefix,
# so the pattern here must NOT include /hub — it becomes /hub/token-login.
c.JupyterHub.extra_handlers = [
    (r'/token-login', TokenAutoLoginHandler),
]
