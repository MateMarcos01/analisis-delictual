"""
modulos/rutas.py
Dónde escribe la aplicación sus archivos de trabajo.

Una app instalada no puede escribir junto a su ejecutable ni confiar en el
directorio desde el que se la abrió, así que todo lo que genera por su cuenta
(gráficos intermedios, mapa, registro de errores) va a la carpeta de datos del
usuario. Lo que el usuario exporta (PDF, Excel) se guarda donde él elige.
"""
import os
from pathlib import Path

NOMBRE_APP = "AnalizadorDelictual"
# Permite redirigir la carpeta de trabajo (tests, instalaciones portables)
VARIABLE_CARPETA = "ANALIZADOR_DELICTUAL_DIR"


def carpeta_app() -> Path:
    """Carpeta de trabajo de la aplicación: %LOCALAPPDATA%\\AnalizadorDelictual."""
    forzada = os.environ.get(VARIABLE_CARPETA)
    if forzada:
        carpeta = Path(forzada)
    else:
        base = os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share"
        carpeta = Path(base) / NOMBRE_APP
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _subcarpeta(nombre: str) -> Path:
    carpeta = carpeta_app() / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def carpeta_graficos() -> Path:
    return _subcarpeta("graficos")


def carpeta_logs() -> Path:
    return _subcarpeta("logs")


def ruta_mapa() -> Path:
    return carpeta_app() / "mapa.html"


def carpeta_documentos() -> Path:
    """Carpeta sugerida al exportar. Si no existe 'Documents', la del usuario."""
    documentos = Path.home() / "Documents"
    return documentos if documentos.is_dir() else Path.home()
