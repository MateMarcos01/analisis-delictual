"""
modulos/marca.py
Identidad de la aplicación: nombre, lema y archivos del logo.
La usan la interfaz (main.py) y el reporte PDF (exportador.py).
"""
from pathlib import Path

NOMBRE_VISIBLE = "Vistana"
LEMA = "De Excel a reportes PDF"
VERSION = "1.2"

CARPETA_ICONOS = Path(__file__).resolve().parent.parent / "Iconos"
ICONO_VENTANA = CARPETA_ICONOS / "vistana_logo.ico"
LOGO = CARPETA_ICONOS / "vistana_logo.png"
