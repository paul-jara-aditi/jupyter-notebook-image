# Auth ↔ JupyterHub Integration — Design

## Goal

Let an already-authenticated user (holding an auth-service session token) open their JupyterHub notebook directly, without seeing the JupyterHub login form. An unauthenticated request must fail with an authentication error.

## Approach

The auth service orchestrates JupyterHub. A new endpoint `POST /auth/jupyter-launch` validates the caller's session token, drives the JupyterHub Admin API to provision and start the user's ephemeral notebook, mints a JupyterHub user token, and returns a ready-to-open URL containing that token.

Opening the returned URL authenticates the browser against JupyterHub via the `?token=` query parameter, so no login form appears.

## Components

### auth-service/main.py
New endpoint `POST /auth/jupyter-launch`:

1. Read `Authorization: Bearer <token>` header. Look up `SESSIONS[token]` → `role`. If missing → `401`.
2. Map `role` → JupyterHub username (identical string: `sales`, `marketing`, `collections`).
3. Call the JupyterHub Admin API (server-side, over the Docker network) with header `Authorization: token <JUPYTERHUB_API_TOKEN>`:
   - `POST {HUB_API_INTERNAL}/users/{username}` — create user. Treat `409 Conflict` (already exists) as success.
   - `POST {HUB_API_INTERNAL}/users/{username}/server` — start server. Treat `201`, `202`, and `400` ("already running") as success.
   - `POST {HUB_API_INTERNAL}/users/{username}/tokens` — mint a user token. Read `token` from the JSON response.
4. Return `200`:
   ```json
   {
     "url": "http://localhost:8000/user/{username}/?token={user_token}",
     "username": "{username}",
     "role": "{role}"
   }
   ```
5. On any Admin API failure (non-success status, connection error) → `502` with the upstream detail.

Configuration read from environment:
- `JUPYTERHUB_API_TOKEN` — admin token for Admin API calls.
- `HUB_API_INTERNAL` — internal Admin API base, default `http://jupyter-paypal:8000/hub/api`.
- `HUB_PUBLIC_URL` — public hub base for the returned browser URL, default `http://localhost:8000`.

### auth-service/requirements.txt
Add `httpx==0.27.2` for the HTTP client.

### jupyterhub_config.py
Expand `allowed_users` and `admin_users` to include the three role usernames:
```python
c.Authenticator.allowed_users = {'jupyter_user', 'sales', 'marketing', 'collections'}
c.Authenticator.admin_users = {'jupyter_user'}
```

### docker-compose.yml
Pass `JUPYTERHUB_API_TOKEN` to the auth-service container via `env_file: .env` (the variable already exists in `.env` for the hub). Both containers already share `jupyterhub-network`.

### Postman
Add a "Jupyter Launch" request to the **Auth Service** collection:
- `POST {{auth_url}}/auth/jupyter-launch`
- Header `Authorization: Bearer {{token}}`
- Test script saves `url` to an environment variable `jupyter_url`.

## Data Flow

```
Postman
  │  POST /auth/login  (email + password)
  ▼
auth-service ──► {token, role}        (token saved in Postman env)
  │
  │  POST /auth/jupyter-launch  (Authorization: Bearer {{token}})
  ▼
auth-service
  │  validate token → role → username
  │  POST /hub/api/users/{u}          (create, ignore 409)
  │  POST /hub/api/users/{u}/server   (start, ignore 400 already-running)
  │  POST /hub/api/users/{u}/tokens   (mint user token)
  ▼
auth-service ──► {url: ".../user/{u}/?token=...", username, role}
  │
  ▼
Browser opens url ──► JupyterHub authenticates via ?token ──► notebook (no login form)
```

## Error Handling

| Condition | Response |
|-----------|----------|
| Missing or invalid Bearer token | `401 {"detail": "Invalid or expired token"}` |
| Admin API returns unexpected non-success status | `502 {"detail": "JupyterHub API error: <status> <body>"}` |
| Cannot reach the hub | `502 {"detail": "Cannot reach JupyterHub"}` |

## Testing

Manual smoke test via curl/Postman:
1. `docker compose up --build -d` (hub + auth-service).
2. `POST /auth/login` as `sales@company.com` → obtain token.
3. `POST /auth/jupyter-launch` with that token → expect `200` with a `url`.
4. Open the `url` in a browser → notebook loads with no login prompt.
5. Repeat `jupyter-launch` with a bogus token → expect `401`.

## Out of Scope

- Real password hashing / persistent user store (still POC).
- Per-email isolation beyond role (one user per role is sufficient).
- Automatic server shutdown / idle culling.
