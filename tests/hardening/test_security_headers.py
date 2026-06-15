"""
Tests de cabeceras HTTP de seguridad en el servidor singleuser.

Qué verifica:
  - X-Frame-Options: DENY (anti-clickjacking)
  - X-Content-Type-Options: nosniff (anti-MIME sniffing)
  - Content-Security-Policy con frame-ancestors 'none' y default-src 'self'
  - Referrer-Policy: no-referrer

Estado esperado ANTES de implementar: todos fallan (cabeceras ausentes).
Estado esperado DESPUÉS de implementar: todos pasan.
"""

import pytest


@pytest.fixture(scope="module")
def respuesta_lab(nb_client):
    """Carga JupyterLab una sola vez y reutiliza la respuesta en todos los tests del módulo."""
    r = nb_client.get("lab", follow_redirects=True)
    assert r.status_code == 200, f"JupyterLab no cargó: {r.status_code}"
    return r


def test_x_frame_options_deny(respuesta_lab):
    valor = respuesta_lab.headers.get("X-Frame-Options")
    assert valor == "DENY", (
        f"X-Frame-Options debe ser 'DENY' para bloquear embedding en iframes, "
        f"se obtuvo: {valor!r}"
    )


def test_x_content_type_nosniff(respuesta_lab):
    valor = respuesta_lab.headers.get("X-Content-Type-Options")
    assert valor == "nosniff", (
        f"X-Content-Type-Options debe ser 'nosniff', se obtuvo: {valor!r}"
    )


def test_content_security_policy_presente(respuesta_lab):
    assert "Content-Security-Policy" in respuesta_lab.headers, (
        "La cabecera Content-Security-Policy está ausente. "
        "Agregar en c.ServerApp.tornado_settings['headers']."
    )


def test_csp_bloquea_embedding_en_iframe(respuesta_lab):
    csp = respuesta_lab.headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in csp, (
        f"La CSP debe incluir \"frame-ancestors 'none'\" para bloquear clickjacking. "
        f"CSP actual: {csp!r}"
    )


def test_csp_default_src_self(respuesta_lab):
    csp = respuesta_lab.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp, (
        f"La CSP debe incluir \"default-src 'self'\". CSP actual: {csp!r}"
    )


def test_referrer_policy_no_referrer(respuesta_lab):
    valor = respuesta_lab.headers.get("Referrer-Policy")
    assert valor == "no-referrer", (
        f"Referrer-Policy debe ser 'no-referrer', se obtuvo: {valor!r}"
    )


def test_cabeceras_presentes_en_api_contents(nb_client):
    """Las cabeceras de seguridad deben aplicarse también a las respuestas de la API."""
    r = nb_client.get("api/contents/")
    assert r.status_code == 200
    assert "X-Content-Type-Options" in r.headers, (
        "Las cabeceras de seguridad deben estar presentes también en las respuestas JSON de la API."
    )
