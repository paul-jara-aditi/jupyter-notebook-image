# Plan de Implementación: Hardening de Jupyter Notebook

> **Para agentes de ejecución:** SUB-SKILL REQUERIDA: Usar superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementar este plan tarea por tarea. Los pasos usan sintaxis de casilla (`- [ ]`) para seguimiento.

**Objetivo:** Endurecer el contenedor singleuser de Jupyter para bloquear descargas de notebooks y agregar controles de seguridad en capas (límites de recursos, datos de solo lectura, cierre por inactividad, cabeceras HTTP de seguridad).

**Arquitectura:** Una extensión de Jupyter Server instalada en la imagen singleuser intercepta las rutas URL `/nbconvert/` y `/files/` antes que los manejadores predeterminados — Tornado antepone las entradas de `add_handlers`, por lo que los manejadores de extensión ganan. Los controles adicionales viven en `jupyterhub_config.py` (límites a nivel de spawner aplicados por el Hub antes de que inicie cada contenedor).

**Stack tecnológico:** Python, Jupyter Server 2.x extension API, DockerSpawner, Tornado, Docker Compose.

---

## Lo que ya está protegido (NO reimplementar)

| Control | Ubicación |
|---|---|
| Entorno conda/pip bloqueado como root | `singleuser/Dockerfile` |
| Terminal deshabilitada | `singleuser/Dockerfile` `/etc/jupyter/jupyter_server_config.py` |
| Ejecución de shell con `!cmd` bloqueada | `singleuser/Dockerfile` script de arranque |
| Magias `%pip / %conda / %mamba` eliminadas | `singleuser/Dockerfile` script de arranque |
| Contenedores efímeros (eliminados al parar) | `jupyterhub_config.py` `c.DockerSpawner.remove = True` |
| Contenedores aislados por usuario | `jupyterhub_config.py` DockerSpawner |
| AUTH_SERVICE_TOKEN inyectado | `jupyterhub_config.py` `pre_spawn_hook` |

---

## Estructura de archivos

| Acción | Ruta | Responsabilidad |
|---|---|---|
| Crear | `singleuser/extensions/block_download/__init__.py` | Extensión de Jupyter Server: bloquea `/nbconvert/` y `/files/` |
| Crear | `singleuser/extensions/block_download/pyproject.toml` | Hace la extensión instalable como paquete Python |
| Crear | `singleuser/jupyter_server_config.py` | Habilita la extensión + cabeceras HTTP de seguridad |
| Modificar | `singleuser/Dockerfile` | Copiar e instalar la extensión vía pip, copiar config |
| Modificar | `jupyterhub_config.py` | Límites de recursos, volumen de datos de solo lectura, cierre por inactividad |

---

## Tarea 1: Crear la extensión Jupyter Server para bloquear descargas

**Archivos:**
- Crear: `singleuser/extensions/block_download/__init__.py`
- Crear: `singleuser/extensions/block_download/pyproject.toml`

- [ ] **Paso 1: Crear el directorio del paquete de extensión**

```powershell
New-Item -ItemType Directory -Force "singleuser/extensions/block_download"
```

- [ ] **Paso 2: Escribir el módulo de extensión**

Crear `singleuser/extensions/block_download/__init__.py` con este contenido exacto:

```python
from jupyter_server.base.handlers import JupyterHandler
from jupyter_server.extension.application import ExtensionApp
from tornado import web


class BlockedHandler(JupyterHandler):
    async def get(self, *args, **kwargs):
        self.set_status(403)
        await self.finish({"message": "La descarga de notebooks está deshabilitada en este entorno."})


class BlockDownloadApp(ExtensionApp):
    name = "block_download"

    def initialize_handlers(self):
        self.handlers = [
            (r"/nbconvert/.*", BlockedHandler),
            (r"/files/.*", BlockedHandler),
        ]


def _jupyter_server_extension_points():
    return [{"app": BlockDownloadApp}]
```

**Por qué funciona:** Jupyter Server llama a `webapp.add_handlers(".*$", prepared_handlers)` para cada extensión. El método `add_handlers` de Tornado *antepone* entradas a la lista de manejadores, por lo que el manejador de la extensión se evalúa antes que los manejadores predeterminados de `/nbconvert/` y `/files/` y responde primero con 403.

- [ ] **Paso 3: Escribir el pyproject.toml**

Crear `singleuser/extensions/block_download/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "block_download"
version = "0.1.0"
requires-python = ">=3.8"
dependencies = ["jupyter_server>=2.0"]

[tool.setuptools.packages.find]
where = ["."]
```

- [ ] **Paso 4: Verificar que la estructura del paquete sea correcta**

```powershell
Get-ChildItem -Recurse singleuser/extensions/
```

Salida esperada:
```
block_download/
    __init__.py
    pyproject.toml
```

---

## Tarea 2: Crear la config de Jupyter Server para singleuser

**Archivos:**
- Crear: `singleuser/jupyter_server_config.py`

- [ ] **Paso 1: Escribir el archivo de configuración**

Crear `singleuser/jupyter_server_config.py`:

```python
# Habilitar la extensión block-download instalada en la imagen
c.ServerApp.jpserver_extensions = {
    "block_download": True,
}

# Cabeceras HTTP de seguridad servidas con cada respuesta del notebook
c.ServerApp.tornado_settings = {
    "headers": {
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        ),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
    }
}
```

**Por qué `frame-ancestors 'none'`:** Evita que esta instancia de Jupyter sea embebida en un iframe desde otro origen, bloqueando ataques de clickjacking.

---

## Tarea 3: Actualizar el Dockerfile de singleuser

**Archivos:**
- Modificar: `singleuser/Dockerfile`

- [ ] **Paso 1: Agregar los pasos COPY + RUN para la extensión y la config**

Abrir `singleuser/Dockerfile`. Después del bloque existente `COPY singleuser/requirements.txt` y antes de la sección `USER root`, agregar:

```dockerfile
# Instalar la extensión block-download (bloquea /nbconvert/ y /files/)
COPY singleuser/extensions/ /tmp/extensions/
RUN pip install --no-cache-dir /tmp/extensions/block_download/

# Copiar la config de Jupyter Server (habilita la extensión + cabeceras de seguridad)
COPY singleuser/jupyter_server_config.py /etc/jupyter/jupyter_server_config.py
```

El Dockerfile completo debe verse así después de la edición:

```dockerfile
FROM quay.io/jupyter/base-notebook:latest

ENV PYTHONNOUSERSITE=1 \
    PIP_NO_CACHE_DIR=1

# Instalar paquetes mientras /opt/conda aún es escribible (antes del bloqueo)
COPY singleuser/requirements.txt /tmp/requirements.txt
RUN mamba install --yes --quiet --channel conda-forge --file /tmp/requirements.txt \
    && mamba clean --all -f -y

# Copiar notebooks plantilla a la imagen — cada contenedor comienza con una copia fresca.
COPY notebooks/ /home/jovyan/work/notebooks/

# Instalar la extensión block-download (bloquea /nbconvert/ y /files/)
COPY singleuser/extensions/ /tmp/extensions/
RUN pip install --no-cache-dir /tmp/extensions/block_download/

# Copiar la config de Jupyter Server (habilita la extensión + cabeceras de seguridad)
COPY singleuser/jupyter_server_config.py /etc/jupyter/jupyter_server_config.py

USER root

# 1. Bloquear el entorno Python/conda
RUN chown -R root:root /opt/conda \
    && chmod -R 755 /opt/conda

# 2. Deshabilitar la terminal de Jupyter
RUN mkdir -p /etc/jupyter \
    && printf '%s\n' \
        'c.ServerApp.terminals_enabled = False' \
        'c.NotebookApp.terminals_enabled = False' \
       >> /etc/jupyter/jupyter_server_config.py

# 3. Bloquear ejecución de shell y magias de gestores de paquetes en notebooks
RUN mkdir -p /etc/ipython/profile_default/startup \
    && cat > /etc/ipython/profile_default/startup/00-block-system.py << 'EOF'
from IPython import get_ipython

ip = get_ipython()
if ip:
    def _blocked(cmd, *args, **kwargs):
        raise RuntimeError("La ejecución de comandos del sistema está deshabilitada en este entorno.")

    ip.system = _blocked

    for magic in ("pip", "conda", "mamba"):
        ip.magics_manager.magics["line"].pop(magic, None)
EOF

USER ${NB_UID}
```

**Nota sobre `>>` vs `>`:** Se usa append (`>>`) para los ajustes de terminal sobre el `jupyter_server_config.py` existente (copiado por el paso COPY) para no sobreescribir la habilitación de la extensión y las cabeceras de seguridad ya escritas.

- [ ] **Paso 2: Construir la imagen y verificar que compila sin errores**

```powershell
docker build -t jupyter-paypal-singleuser:latest -f singleuser/Dockerfile .
```

Esperado: la construcción finaliza sin errores. El paso `pip install` debe mostrar `Successfully installed block-download-0.1.0`.

- [ ] **Paso 3: Smoke-test — verificar que la extensión está cargada**

```powershell
docker run --rm jupyter-paypal-singleuser:latest jupyter server extension list
```

Salida esperada incluye:
```
block_download  enabled
```

- [ ] **Paso 4: Commit**

```bash
git add singleuser/extensions/ singleuser/jupyter_server_config.py singleuser/Dockerfile
git commit -m "feat(singleuser): bloquear descarga de notebooks via Jupyter Server extension"
```

---

## Tarea 4: Agregar límites de recursos y volumen de datos de solo lectura

**Archivos:**
- Modificar: `jupyterhub_config.py`

- [ ] **Paso 1: Agregar límites de CPU, memoria y montar datos como solo lectura**

En `jupyterhub_config.py`, reemplazar el bloque existente de `c.DockerSpawner.volumes` y agregar los límites de recursos:

```python
# Montar datos como solo lectura — los usuarios pueden consultar datos via la API
# del auth-service pero no pueden modificar los archivos fuente en el host.
c.DockerSpawner.volumes = {
    f'{host_path}/data': {'bind': '/home/jovyan/work/data', 'mode': 'ro'},
    f'{host_path}/src':  '/home/jovyan/work/src',
}

# Limitar cada contenedor singleuser a 1 CPU y 1 GB de RAM.
# cpu_quota / cpu_period = 1.0 core de CPU.
c.DockerSpawner.extra_host_config = {
    "cpu_period": 100_000,
    "cpu_quota":  100_000,
    "mem_limit":  "1g",
    "memswap_limit": "1g",  # deshabilitar swap (igual a mem_limit = sin swap extra)
}
```

- [ ] **Paso 2: Verificar que la config se parsea sin errores**

```powershell
python -c "exec(open('jupyterhub_config.py').read()); print('OK')"
```

Esperado: `OK` (sin errores de sintaxis Python).

- [ ] **Paso 3: Commit**

```bash
git add jupyterhub_config.py
git commit -m "feat(hub): volumen de datos solo lectura, límites de CPU/memoria por contenedor"
```

---

## Tarea 5: Agregar cierre automático por inactividad

**Archivos:**
- Modificar: `jupyterhub_config.py`
- Modificar: `hub/requirements.txt`

JupyterHub incluye un culler de inactividad integrado desde la versión 2.x. Se habilita como servicio interno.

- [ ] **Paso 1: Agregar el servicio culler a jupyterhub_config.py**

Agregar este bloque al final de `jupyterhub_config.py`:

```python
# Detener automáticamente servidores de notebooks inactivos después de 30 minutos.
# El culler es un servicio gestionado que corre dentro del contenedor del Hub.
c.JupyterHub.load_roles = [
    {
        "name": "jupyterhub-idle-culler-role",
        "description": "Cierra servidores singleuser inactivos",
        "scopes": [
            "list:users",
            "read:users:activity",
            "read:servers",
            "delete:servers",
        ],
        "services": ["jupyterhub-idle-culler"],
    }
]
c.JupyterHub.services = [
    {
        "name": "jupyterhub-idle-culler",
        "command": [
            "python3",
            "-m", "jupyterhub_idle_culler",
            "--timeout=1800",   # 30 minutos en segundos
            "--cull-every=300", # verificar cada 5 minutos
        ],
    }
]
```

- [ ] **Paso 2: Instalar jupyterhub-idle-culler en la imagen del hub**

Abrir `hub/requirements.txt` y agregar:

```
jupyterhub-idle-culler
```

- [ ] **Paso 3: Reconstruir la imagen del hub**

```powershell
docker compose build jupyter
```

Esperado: la imagen del hub se reconstruye e incluye `jupyterhub-idle-culler`.

- [ ] **Paso 4: Commit**

```bash
git add jupyterhub_config.py hub/requirements.txt
git commit -m "feat(hub): cierre automático de servidores inactivos después de 30 minutos"
```

---

## Tarea 6: Pruebas de humo end-to-end

Estas pruebas verifican que los controles de hardening funcionan. Ejecutar después de `docker compose up -d`.

- [ ] **Prueba 1 — el endpoint nbconvert está bloqueado**

Desde una terminal (reemplazar `<token>` con un token válido de JupyterHub):

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: token <token>" \
  http://localhost:8000/user/<username>/nbconvert/script/work/notebooks/demo.ipynb
```

Esperado: `403`

- [ ] **Prueba 2 — el endpoint files está bloqueado**

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: token <token>" \
  http://localhost:8000/user/<username>/files/work/notebooks/demo.ipynb
```

Esperado: `403`

- [ ] **Prueba 3 — el notebook aún puede abrirse (contents API no afectada)**

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: token <token>" \
  "http://localhost:8000/user/<username>/api/contents/work/notebooks/demo.ipynb?content=1"
```

Esperado: `200` (abrir en el editor sigue funcionando)

- [ ] **Prueba 4 — las cabeceras de seguridad están presentes**

```bash
curl -sI -H "Authorization: token <token>" \
  http://localhost:8000/user/<username>/lab \
  | grep -E "X-Frame|X-Content|Content-Security"
```

Esperado: las cabeceras `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy` están presentes.

- [ ] **Prueba 5 — el directorio de datos es de solo lectura**

En una celda de notebook:

```python
open('/home/jovyan/work/data/test_write.txt', 'w').write('hello')
```

Esperado: `PermissionError: [Errno 30] Read-only file system: '/home/jovyan/work/data/test_write.txt'`

- [ ] **Paso 6: Commit si todas las pruebas pasan**

```bash
git add .
git commit -m "test: verificar controles de hardening (resultados de prueba manual OK)"
```

---

## Limitaciones y trabajo futuro

| Limitación | Explicación |
|---|---|
| Botón "Download" de JupyterLab en la UI | Cuando un usuario hace clic en Descargar en JupyterLab, el navegador llama a `GET /api/contents/<path>?content=1` (igual que abrir el archivo) y luego crea una Blob URL del lado del cliente. No existe distinción del lado del servidor entre "abrir" y "descargar". La supresión completa requiere una extensión frontend TypeScript de JupyterLab para eliminar el comando `docmanager:download` de la UI. |
| El volumen `src` sigue siendo escribible | Los usuarios pueden escribir archivos en `/home/jovyan/work/src`. Si ese directorio contiene módulos auxiliares cargados por notebooks, evaluar si `:ro` es apropiado. |
| Sin restricción de egreso de red | Los contenedores singleuser comparten `jupyterhub-network` y pueden alcanzar cualquier host accesible desde el bridge de Docker. Considerar una red restringida dedicada con lista de permisos explícita solo para auth-service. |
