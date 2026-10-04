# Su sola presencia hace que pytest agregue la raíz del proyecto a sys.path,
# para que los tests puedan importar "modulos".
import pytest

from modulos.rutas import VARIABLE_CARPETA


@pytest.fixture(autouse=True)
def carpeta_de_trabajo(tmp_path, monkeypatch):
    """Los tests nunca escriben en la carpeta de trabajo real del usuario."""
    carpeta = tmp_path / "app"
    monkeypatch.setenv(VARIABLE_CARPETA, str(carpeta))
    return carpeta
