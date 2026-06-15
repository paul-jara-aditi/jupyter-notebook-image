"""
Fixtures compartidos para los tests de hardening.

Requisitos antes de ejecutar:
    1. docker compose up -d
    2. docker build -t jupyter-paypal-singleuser:latest -f singleuser/Dockerfile .
    3. Variables de entorno:
         JUPYTERHUB_API_TOKEN=<token-admin>   (el mismo del .env)
         HUB_URL=http://localhost:8000        (por defecto)

Ejecutar:
    pip install -r tests/hardening/requirements.txt
    pytest tests/hardening/ -v
"""

import asyncio
import json
import os
import time
import uuid

import docker as docker_sdk
import httpx
import pytest
import websockets

HUB_URL = os.getenv("HUB_URL", "http://localhost:8000")
HUB_ADMIN_TOKEN = os.getenv("JUPYTERHUB_API_TOKEN", "")
TEST_USERNAME = "htest_hardening"


# ---------------------------------------------------------------------------
# Hub + singleuser server fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def hub():
    """Cliente httpx con token admin apuntando al Hub API."""
    with httpx.Client(
        base_url=f"{HUB_URL}/hub/api",
        headers={"Authorization": f"token {HUB_ADMIN_TOKEN}"},
        timeout=30,
    ) as client:
        yield client


@pytest.fixture(scope="session")
def running_server(hub):
    """
    Crea un usuario de prueba, arranca su servidor singleuser, hace yield de
    {url, token, username} y limpia todo al terminar.
    """
    assert HUB_ADMIN_TOKEN, (
        "Falta la variable JUPYTERHUB_API_TOKEN. "
        "Exportala antes de correr los tests."
    )

    r = hub.post(f"/users/{TEST_USERNAME}")
    assert r.status_code in (201, 409), f"Crear usuario falló: {r.status_code} {r.text}"

    r = hub.post(f"/users/{TEST_USERNAME}/server")
    assert r.status_code in (201, 202, 400), f"Arrancar servidor falló: {r.status_code} {r.text}"

    for _ in range(30):
        data = hub.get(f"/users/{TEST_USERNAME}").json()
        if data.get("servers", {}).get("", {}).get("ready"):
            break
        time.sleep(2)
    else:
        pytest.fail(
            f"El servidor singleuser de '{TEST_USERNAME}' no quedó listo en 60s. "
            "¿Está construida la imagen jupyter-paypal-singleuser:latest?"
        )

    r = hub.post(f"/users/{TEST_USERNAME}/tokens", json={"note": "hardening-tests"})
    assert r.status_code == 201, f"Crear token falló: {r.status_code} {r.text}"
    token = r.json()["token"]

    yield {
        "url": f"{HUB_URL}/user/{TEST_USERNAME}",
        "token": token,
        "username": TEST_USERNAME,
    }

    hub.delete(f"/users/{TEST_USERNAME}/server")
    time.sleep(3)
    hub.delete(f"/users/{TEST_USERNAME}")


@pytest.fixture(scope="session")
def nb_client(running_server):
    """Cliente httpx autenticado apuntando a la raíz del servidor singleuser."""
    with httpx.Client(
        base_url=running_server["url"] + "/",
        headers={"Authorization": f"token {running_server['token']}"},
        timeout=30,
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Docker fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def docker_client():
    return docker_sdk.from_env()


@pytest.fixture(scope="session")
def singleuser_container(docker_client, running_server):
    """El contenedor Docker que corre el servidor de notebooks del usuario de prueba."""
    username = running_server["username"]
    containers = docker_client.containers.list(
        filters={"label": f"jupyterhub-user={username}"}
    )
    assert len(containers) == 1, (
        f"Se esperaba 1 contenedor con label jupyterhub-user={username}, "
        f"se encontraron {len(containers)}."
    )
    return containers[0]


# ---------------------------------------------------------------------------
# Helper para ejecutar código en un kernel remoto via WebSocket
# ---------------------------------------------------------------------------

async def execute_code_in_kernel(server_url: str, token: str, code: str) -> dict:
    """
    Crea un kernel Python, ejecuta `code`, devuelve el resultado y borra el kernel.

    Retorna:
        {"status": "ok" | "error", "error": {"ename": ..., "evalue": ...} | None}
    """
    headers = {"Authorization": f"token {token}"}

    async with httpx.AsyncClient(
        base_url=server_url + "/",
        headers=headers,
        timeout=30,
    ) as client:
        r = await client.post("api/kernels", json={"name": "python3"})
        r.raise_for_status()
        kernel_id = r.json()["id"]

    ws_base = server_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_base}/api/kernels/{kernel_id}/channels?token={token}"

    result: dict = {"status": "unknown", "error": None}

    try:
        async with websockets.connect(ws_url) as ws:
            msg_id = str(uuid.uuid4())
            await ws.send(json.dumps({
                "header": {
                    "msg_id": msg_id,
                    "msg_type": "execute_request",
                    "username": "test",
                    "session": str(uuid.uuid4()),
                    "date": "",
                    "version": "5.3",
                },
                "parent_header": {},
                "metadata": {},
                "content": {
                    "code": code,
                    "silent": False,
                    "store_history": False,
                    "user_expressions": {},
                    "allow_stdin": False,
                    "stop_on_error": True,
                },
                "channel": "shell",
                "buffers": [],
            }))

            deadline = asyncio.get_event_loop().time() + 30
            while asyncio.get_event_loop().time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    continue

                msg = json.loads(raw)
                if msg.get("parent_header", {}).get("msg_id") != msg_id:
                    continue

                msg_type = msg.get("msg_type", "")
                if msg_type == "error":
                    result["error"] = {
                        "ename": msg["content"]["ename"],
                        "evalue": msg["content"]["evalue"],
                    }
                elif msg_type == "execute_reply":
                    result["status"] = msg["content"]["status"]
                    break
    finally:
        async with httpx.AsyncClient(
            base_url=server_url + "/",
            headers=headers,
            timeout=10,
        ) as client:
            await client.delete(f"api/kernels/{kernel_id}")

    return result
