# Plan: Sandboxing de Jupyter — Documento de Decisión + Nivel 3 (JupyterHub Multiusuario)

## Contexto

El proyecto actual es un Jupyter **monousuario** dockerizado (`Dockerfile` personalizado sobre `python:3.11-slim`, usuario sin privilegios `jupyter_user`, autenticación por token vía `start.sh`). El objetivo es avanzar hacia un sandboxing adecuado basado en una referencia de 4 niveles (1: contenedores rootless, 2: gVisor/microVMs, 3: serverless/JupyterHub multi-tenant, 4: JupyterLite en el navegador).

Decisiones tomadas:
- **Entregable: Ambos** — un documento de decisión/comparación *y* una implementación.
- **Modelo de amenaza: Multiusuario / equipo** → objetivo **Nivel 3: JupyterHub + DockerSpawner**.

**Restricción de plataforma:** el host es Windows 11 + Docker Desktop. El runtime `runsc` de gVisor (Nivel 2) solo funciona en un host Linux, por lo que se documenta como opción futura/cloud, no se implementa aquí. JupyterHub + DockerSpawner funciona en Docker Desktop a través del socket de Docker montado. JupyterLite (Nivel 4) es totalmente multiplataforma y se documenta como complemento.

---

## Parte A — Documento de Decisión

**Archivo nuevo:** `docs/sandboxing-strategy.md`

Una comparación concisa de los 4 niveles aplicados a este proyecto.

- **Dónde estamos hoy:** Nivel 1 parcial (imagen personalizada, usuario sin privilegios, paquetes de solo lectura, autenticación por token).

| Nivel | Herramientas | Windows/Docker Desktop | Mejor para |
|-------|--------------|------------------------|------------|
| 1 Ligero | Docker/Podman rootless, jupyter docker-stacks (uid 1000), bridges de red | ✅ Nativo | Un solo usuario, código confiable |
| 2 Profundo | gVisor `runsc`, Kata/Firecracker, KubeArmor | ⚠️ Solo host Linux (no Docker Desktop) | Ejecución de código no confiable |
| 3 Cloud/Multi-tenant | **JupyterHub + DockerSpawner**, idle-culler | ✅ Vía socket de Docker | **Equipos (elegido)** |
| 4 Solo navegador | JupyterLite + Pyodide (WASM) | ✅ Sitio estático, sin backend | Compartir/demos, código totalmente no confiable |

- **Recomendación:** Implementar **Nivel 3** ahora para el equipo. Escalar a **Nivel 2 (gVisor)** solo si hay que ejecutar código no confiable, en un host Linux o VM en la nube (`--runtime=runsc`). Ofrecer **Nivel 4 (JupyterLite)** como canal complementario sin infraestructura para notebooks de solo lectura/demos.
- **Nota sobre aislamiento de red:** los contenedores de usuario en una red Docker `internal` quedan aislados de la LAN/intranet del host y de internet; el Hub hace de puente hacia el host para que el navegador pueda alcanzarlo.

---

## Parte B — Implementación Nivel 3 (JupyterHub + DockerSpawner)

### Arquitectura
- **Contenedor Hub** (puerto 8000): autenticación + spawning. Monta el socket de Docker para crear contenedores por usuario.
- **Contenedores monousuario**: uno por usuario conectado, creado bajo demanda, eliminado automáticamente al cerrar sesión, con límites de CPU/memoria.
- **Dos redes**:
  - `hub-public` (bridge): host ↔ Hub en `:8000`, y salida del Hub.
  - `hub-internal` (`internal: true`): Hub ↔ contenedores monousuario. Los contenedores de usuario se unen **solo** a esta → sin acceso a LAN/internet. El Hub se une a ambas.

### Archivos a crear

**1. `Dockerfile.hub`** — la imagen del Hub
```dockerfile
FROM quay.io/jupyterhub/jupyterhub:5
RUN pip install --no-cache-dir \
    dockerspawner \
    jupyterhub-nativeauthenticator \
    jupyterhub-idle-culler
COPY jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py
```

**2. `Dockerfile.notebook`** — imagen monousuario (reemplaza el rol del `Dockerfile` actual)
```dockerfile
# La imagen oficial ya corre como usuario sin privilegios jovyan (uid 1000) = base Nivel 1
FROM quay.io/jupyter/scipy-notebook:latest
COPY --chown=1000:1000 requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
```

**3. `jupyterhub_config.py`** — configuración principal
- `c.JupyterHub.spawner_class = 'dockerspawner.DockerSpawner'`
- `c.DockerSpawner.image = os.environ['DOCKER_NOTEBOOK_IMAGE']`
- `c.DockerSpawner.network_name = 'hub-internal'`
- `c.JupyterHub.hub_connect_ip = 'jupyterhub'` ; `c.JupyterHub.hub_ip = '0.0.0.0'`
- Volumen por usuario: `c.DockerSpawner.volumes = {'jupyterhub-user-{username}': '/home/jovyan/work'}`
- Datos compartidos + notebook inicial montados en solo lectura en `/home/jovyan/shared` (`mode: 'ro'`)
- `c.DockerSpawner.remove = True`
- Límites de recursos: `mem_limit='2G'`, `cpu_limit=1.0` (ajustable)
- Autenticación: `c.JupyterHub.authenticator_class = 'nativeauthenticator.NativeAuthenticator'`, `c.NativeAuthenticator.open_signup = False`, `c.Authenticator.admin_users = set(os.environ.get('JUPYTERHUB_ADMIN','admin').split(','))`
- BD: `c.JupyterHub.db_url = 'sqlite:////srv/jupyterhub/data/jupyterhub.sqlite'`
- Apagado por inactividad vía servicio del Hub `jupyterhub-idle-culler` (p. ej. 1h inactivo)

**4. Reescribir `docker-compose.yml`**

```yaml
services:
  jupyterhub:
    build: { context: docs, dockerfile: Dockerfile.hub }
    container_name: jupyterhub
    ports: [ "8000:8000" ]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:rw
      - jupyterhub-data:/srv/jupyterhub/data
      - ./data:/srv/shared-data:ro
      - ./notebooks:/srv/shared-notebooks:ro
    environment:
      DOCKER_NOTEBOOK_IMAGE: paypal-notebook:latest
      JUPYTERHUB_ADMIN: ${JUPYTERHUB_ADMIN}
    networks: [ hub-public, hub-internal ]
    restart: unless-stopped

networks:
  hub-public:
  hub-internal:
    internal: true

volumes:
  jupyterhub-data:
```
> Construir la imagen monousuario por separado para que exista en el daemon del host:
> `docker build -f Dockerfile.notebook -t paypal-notebook:latest .`

**5. Actualizar `.env.example`**
- Eliminar el ahora inutilizado `JUPYTER_TOKEN`.
- Añadir `JUPYTERHUB_ADMIN=admin` (nombres de admin separados por comas).

**6. Actualizar `README.md`**
- Reemplazar las instrucciones de un solo contenedor por el flujo de JupyterHub: construir la imagen del notebook, `docker compose up --build`, abrir `http://localhost:8000`, registrarse, el admin autoriza usuarios.
- Actualizar la sección de Seguridad: aislamiento por contenedor de usuario, red interna, límites de recursos, apagado por inactividad. Enlazar `docs/sandboxing-strategy.md`.

### Archivos retirados
- `Dockerfile` (monousuario `python:3.11-slim`) y `start.sh` quedan obsoletos con JupyterHub — se recomienda eliminarlos.

---

## Archivos Críticos
- Nuevos: `Dockerfile.hub`, `Dockerfile.notebook`, `jupyterhub_config.py`, `docs/sandboxing-strategy.md`
- Reescritos: `docker-compose.yml`
- Actualizados: `requirements.txt`, `.env.example`, `README.md`
- Eliminados: `Dockerfile`, `start.sh`

## Verificación (de extremo a extremo)
1. Asegurar que Docker Desktop esté corriendo (`docker info`).
2. Construir la imagen monousuario: `docker build -f Dockerfile.notebook -t paypal-notebook:latest .`
3. `cp .env.example .env` y poner tu usuario en `JUPYTERHUB_ADMIN`.
4. `docker compose up --build` → Hub en `http://localhost:8000`.
5. Registrarse como admin, iniciar sesión. Confirmar que se crea un contenedor monousuario: `docker ps` muestra `jupyter-<usuario>`.
6. Confirmar que `/home/jovyan/shared/...` contiene el notebook inicial + `german_credit.csv` (solo lectura) y que `/home/jovyan/work` es escribible/persistente entre reinicios.
7. **Prueba de aislamiento de red:** en una celda, `import urllib.request; urllib.request.urlopen('https://example.com', timeout=5)` → debe fallar (sin salida externa).
8. **Prueba de aislamiento:** crear un segundo usuario, confirmar un contenedor separado y que los usuarios no ven el volumen `work` del otro.
9. Detener el servidor de un usuario → confirmar que `remove=True` elimina el contenedor.
10. Dejar un servidor inactivo más allá del timeout → confirmar que el idle-culler lo detiene.
