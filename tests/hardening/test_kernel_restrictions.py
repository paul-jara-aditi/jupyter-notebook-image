"""
Tests de restricciones dentro del kernel IPython.

Qué verifica:
  - ip.system() (equivalente a !cmd) levanta RuntimeError
  - %pip magic fue eliminada
  - %conda magic fue eliminada
  - %mamba magic fue eliminada
  - La terminal HTTP API está deshabilitada
  - Código Python legítimo sigue ejecutándose (regresión)

Los tests de kernel ejecutan código real via WebSocket en un kernel remoto.

Estado esperado ANTES de implementar: los tests de bloqueo fallan (los comandos ejecutan).
Estado esperado DESPUÉS de implementar: todos pasan.
"""

import pytest
from .conftest import execute_code_in_kernel


@pytest.fixture(scope="module")
def server_info(running_server):
    return running_server["url"], running_server["token"]


# ---------------------------------------------------------------------------
# Bloqueo de ejecución de shell (!cmd)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shell_system_bloqueado(server_info):
    """
    IPython traduce !ls → get_ipython().system('ls').
    Nuestro startup hook reemplaza ip.system con una función que levanta RuntimeError.
    """
    url, token = server_info
    result = await execute_code_in_kernel(url, token, "get_ipython().system('ls')")

    assert result["status"] == "error", (
        "get_ipython().system() debería fallar con RuntimeError pero ejecutó exitosamente."
    )
    assert result["error"] is not None
    assert result["error"]["ename"] == "RuntimeError", (
        f"Se esperaba RuntimeError, se obtuvo: {result['error']['ename']}"
    )
    assert "disabled" in result["error"]["evalue"].lower(), (
        f"El mensaje de error debe contener 'disabled'. "
        f"Mensaje actual: {result['error']['evalue']!r}"
    )


@pytest.mark.asyncio
async def test_subprocess_run_falla_por_env_bloqueado(server_info):
    """
    subprocess.run() no está directamente bloqueado, pero el entorno conda
    es de solo lectura (root:root 755), así que pip/conda vía subprocess deben fallar.
    """
    url, token = server_info
    result = await execute_code_in_kernel(
        url, token,
        "import subprocess; subprocess.run(['pip', 'install', 'requests'], check=True)"
    )
    assert result["status"] == "error", (
        "pip install vía subprocess debería fallar porque el entorno conda es de solo lectura."
    )


# ---------------------------------------------------------------------------
# Bloqueo de magias de gestores de paquetes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pip_magic_eliminada(server_info):
    """%pip fue eliminada del registro de magias de línea."""
    url, token = server_info
    result = await execute_code_in_kernel(
        url, token,
        "get_ipython().run_line_magic('pip', '--version')"
    )
    assert result["status"] == "error", (
        "La magic %pip debería levantar un error al haber sido eliminada, "
        "pero se ejecutó sin problemas."
    )
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_conda_magic_eliminada(server_info):
    """%conda fue eliminada del registro de magias de línea."""
    url, token = server_info
    result = await execute_code_in_kernel(
        url, token,
        "get_ipython().run_line_magic('conda', '--version')"
    )
    assert result["status"] == "error"
    assert result["error"] is not None


@pytest.mark.asyncio
async def test_mamba_magic_eliminada(server_info):
    """%mamba fue eliminada del registro de magias de línea."""
    url, token = server_info
    result = await execute_code_in_kernel(
        url, token,
        "get_ipython().run_line_magic('mamba', '--version')"
    )
    assert result["status"] == "error"
    assert result["error"] is not None


# ---------------------------------------------------------------------------
# Terminal HTTP API
# ---------------------------------------------------------------------------

def test_terminal_api_deshabilitada(nb_client):
    """
    POST /api/terminals debe ser rechazado cuando terminals_enabled = False.
    El endpoint puede devolver 403, 404 o 503 dependiendo de la versión de Jupyter Server.
    """
    r = nb_client.post("api/terminals")
    assert r.status_code in (403, 404, 503), (
        f"La API de terminales devolvió {r.status_code} en vez de un código de error. "
        "Verificar c.ServerApp.terminals_enabled = False en jupyter_server_config.py."
    )


def test_terminal_list_deshabilitada(nb_client):
    """GET /api/terminals también debe fallar cuando los terminales están deshabilitados."""
    r = nb_client.get("api/terminals")
    assert r.status_code in (403, 404, 503), (
        f"GET /api/terminals devolvió {r.status_code}."
    )


# ---------------------------------------------------------------------------
# Regresión — el código legítimo debe seguir funcionando
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_codigo_python_normal_ejecuta(server_info):
    """
    Verificación de regresión: las restricciones no deben romper la ejecución
    de código Python estándar.
    """
    url, token = server_info
    result = await execute_code_in_kernel(
        url, token,
        "import pandas as pd; df = pd.DataFrame({'a': [1,2,3]}); assert len(df) == 3"
    )
    assert result["status"] == "ok", (
        f"Código Python legítimo falló. Resultado: {result}. "
        "Las restricciones pueden estar bloqueando ejecución normal."
    )


@pytest.mark.asyncio
async def test_importar_librerias_instaladas(server_info):
    """Las librerías del requirements.txt (numpy, pandas, etc.) deben importar sin errores."""
    url, token = server_info
    result = await execute_code_in_kernel(
        url, token,
        "import numpy, pandas, matplotlib, seaborn; print('ok')"
    )
    assert result["status"] == "ok", (
        f"Las librerías del entorno no se pudieron importar. Resultado: {result}"
    )
