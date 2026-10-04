"""Tests de gráficos y reporte PDF (modulos/graficos.py, modulos/exportador.py)."""
from pathlib import Path

import pandas as pd

from modulos.exportador import generar_reporte
from modulos.graficos import generar_todos
from modulos.procesador import _limpiar, filtrar, resumen_general, tabla_pivot


def _df():
    filas = []
    for i in range(60):
        filas.append({
            "legajo": i + 1,
            "fecha": f"{(i % 27) + 1}/{(i % 12) + 1}/2025",
            "hora": f"{i % 24:02d}:15",
            "tipo_delito": ["ROBO", "HURTO", "TTVA ROBO"][i % 3],
            "jurisdiccion": ["COMISARIA 13°", "COMISARIA 15°"][i % 2],
        })
    return _limpiar(pd.DataFrame(filas))


def test_generar_todos_devuelve_rutas_de_png(tmp_path):
    rutas = generar_todos(_df(), carpeta=str(tmp_path))
    assert isinstance(rutas, dict)
    assert set(rutas) == {
        "barras_tipo", "serie_temporal", "barras_jurisdiccion",
        "heatmap_horario", "donut", "ranking_jurisdiccion",
    }
    for ruta in rutas.values():
        assert Path(ruta).stat().st_size > 0


def test_generar_todos_no_deja_figuras_abiertas(tmp_path):
    import matplotlib.pyplot as plt
    generar_todos(_df(), carpeta=str(tmp_path))
    assert plt.get_fignums() == []


def test_generar_todos_con_dos_anios_agrega_la_comparacion(tmp_path):
    crudo = pd.DataFrame([
        {"legajo": i, "fecha": f"{(i % 27) + 1}/{(i % 12) + 1}/{2024 + i % 2}",
         "hora": "10:00", "tipo_delito": "ROBO", "jurisdiccion": "COMISARIA 13°"}
        for i in range(40)
    ])
    rutas = generar_todos(_limpiar(crudo), carpeta=str(tmp_path))
    assert "comparacion_anual" in rutas


def test_generar_reporte_sin_graficos(tmp_path):
    df = _df()
    ruta_pdf = generar_reporte(resumen_general(df), {}, tabla_pivot(df), carpeta=str(tmp_path))
    assert Path(ruta_pdf).read_bytes().startswith(b"%PDF")


def test_generar_todos_con_datos_vacios_no_genera_nada(tmp_path):
    vacio = filtrar(_df(), anio=1990)
    assert generar_todos(vacio, carpeta=str(tmp_path)) == {}


def test_generar_reporte_crea_el_pdf(tmp_path):
    df = _df()
    rutas = generar_todos(df, carpeta=str(tmp_path / "graficos"))
    ruta_pdf = generar_reporte(
        resumen_general(df), rutas, tabla_pivot(df), carpeta=str(tmp_path / "reportes"),
    )
    assert Path(ruta_pdf).read_bytes().startswith(b"%PDF")
