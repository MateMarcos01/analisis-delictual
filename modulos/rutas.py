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
    # Siempre absoluta: no debe depender del directorio desde el que se abre la app
    carpeta = carpeta.expanduser().resolve()
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
    """Carpeta sugerida al exportar: 'Documentos' del usuario, o su carpeta personal."""
    candidatas = [_documentos_de_windows(), Path.home() / "Documents"]
    for carpeta in candidatas:
        if carpeta and carpeta.is_dir():
            return carpeta
    return Path.home()


def _documentos_de_windows():
    """'Documentos' según Windows: puede estar redirigida (por ejemplo a OneDrive)."""
    try:
        import winreg
        clave = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, clave) as k:
            valor, _ = winreg.QueryValueEx(k, "Personal")
        return Path(os.path.expandvars(valor))
    except (ImportError, OSError):
        return None
