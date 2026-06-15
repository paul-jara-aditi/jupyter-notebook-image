"""
Tests de bloqueo de descarga de notebooks.

Qué verifica:
  - /nbconvert/<format>/<path> devuelve 403 (bloquea exportación a script/HTML/PDF)
  - /files/<path> devuelve 403 (bloquea servicio directo de archivos)
  - /api/contents/ sigue devolviendo 200 (abrir notebooks en el editor no se rompe)
  - La UI de JupyterLab sigue cargando (regresión)

Estado esperado ANTES de implementar: todos los tests fallan (nbconvert y files devuelven 200).
Estado esperado DESPUÉS de implementar: todos los tests pasan.
"""


def test_nbconvert_script_export_bloqueado(nb_client):
    r = nb_client.get("nbconvert/script/work/notebooks/ejemplo.ipynb")
    assert r.status_code == 403, (
        f"Se esperaba 403, se obtuvo {r.status_code}. "
        "La extensión block-download probablemente no está instalada."
    )


def test_nbconvert_html_export_bloqueado(nb_client):
    r = nb_client.get("nbconvert/html/work/notebooks/ejemplo.ipynb")
    assert r.status_code == 403


def test_nbconvert_pdf_export_bloqueado(nb_client):
    r = nb_client.get("nbconvert/pdf/work/notebooks/ejemplo.ipynb")
    assert r.status_code == 403


def test_nbconvert_notebook_export_bloqueado(nb_client):
    """Bloquea incluso la descarga en formato .ipynb vía nbconvert."""
    r = nb_client.get("nbconvert/notebook/work/notebooks/ejemplo.ipynb")
    assert r.status_code == 403


def test_files_notebook_bloqueado(nb_client):
    r = nb_client.get("files/work/notebooks/ejemplo.ipynb")
    assert r.status_code == 403


def test_files_csv_bloqueado(nb_client):
    """Cualquier archivo bajo /files/ debe estar bloqueado, no solo .ipynb."""
    r = nb_client.get("files/work/data/datos.csv")
    assert r.status_code == 403


def test_files_ruta_arbitraria_bloqueada(nb_client):
    r = nb_client.get("files/cualquier/ruta/archivo.txt")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Regresiones — estas deben PASAR tanto antes como después de la implementación
# ---------------------------------------------------------------------------

def test_contents_api_sigue_accesible(nb_client):
    """
    La Contents API (/api/contents/) debe seguir respondiendo 200.
    JupyterLab la usa para listar y abrir notebooks; bloquearla rompería el editor.
    """
    r = nb_client.get("api/contents/")
    assert r.status_code == 200, (
        f"La Contents API devolvió {r.status_code}. "
        "La extensión block-download puede haber roto el acceso normal a notebooks."
    )


def test_jupyterlab_ui_carga(nb_client):
    """La interfaz de JupyterLab debe seguir cargando correctamente."""
    r = nb_client.get("lab", follow_redirects=True)
    assert r.status_code == 200, (
        f"JupyterLab devolvió {r.status_code}. "
        "Revisar que la extensión no esté interceptando rutas de la UI."
    )
