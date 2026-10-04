"""Tests del estado de la interfaz (main.py) y del modo terminal (cli.py), sin abrir ventana."""
from unittest.mock import MagicMock

import pandas as pd
import pytest

import cli
import main
from modulos.procesador import _limpiar


def _datos():
    return _limpiar(pd.DataFrame([
        {"legajo": i, "fecha": f"{i + 1}/3/2025", "hora": "10:00",
         "tipo_delito": ["ROBO", "HURTO"][i % 2],
         "jurisdiccion": ["COMISARIA 13°", "COMISARIA 15°"][i % 2]}
        for i in range(10)
    ]))


@pytest.fixture
def app():
    app = main.AnalizadorApp(MagicMock())
    app.alertas = []
    app._mostrar_alerta = lambda titulo, mensaje: app.alertas.append(titulo)
    app.df_original = _datos()
    app.df_filtrado = app.df_original.copy()
    app.rutas_graficos = {"donut": "donut.png"}
    return app


def test_filtrar_invalida_los_graficos_anteriores(app):
    app.aplicar_filtros({"jurisdicciones": ["Comisaria 13°"]})
    assert len(app.df_filtrado) == 5
    assert app.rutas_graficos == {}
    assert app.tarjetas["total_denuncias"].value == "5"

    app._exportar_pdf()
    assert app.alertas == ["Sin gráficos"]


def test_filtro_sin_resultados_no_cambia_el_estado(app):
    antes = app.df_filtrado
    # Comisaria 13° solo tiene robos
    app.aplicar_filtros({"jurisdicciones": ["Comisaria 13°"], "tipos_delito": ["Hurto"]})
    assert app.alertas == ["Sin resultados"]
    assert app.df_filtrado is antes
    assert app.rutas_graficos == {"donut": "donut.png"}


def test_repetir_el_mismo_filtro_conserva_los_graficos(app):
    app.aplicar_filtros({})   # "Limpiar" sin haber filtrado nunca
    assert app.rutas_graficos == {"donut": "donut.png"}


def test_si_falla_el_refresco_igual_se_invalidan_los_graficos(app):
    app._poblar_tabla = MagicMock(side_effect=RuntimeError("falla de pantalla"))
    app.aplicar_filtros({"jurisdicciones": ["Comisaria 13°"]})
    assert app.alertas == ["Error al filtrar"]
    assert app.rutas_graficos == {}


def test_no_se_generan_graficos_dos_veces_a_la_vez(app, monkeypatch):
    lanzados = []
    monkeypatch.setattr(main.threading, "Thread", lambda **kw: lanzados.append(kw) or MagicMock())
    app._generar_graficos()
    app._generar_graficos()
    assert len(lanzados) == 1
    assert app.alertas == ["Gráficos"]


def test_graficos_de_datos_que_ya_cambiaron_se_descartan(app, monkeypatch, tmp_path):
    app.rutas_graficos = {}
    tareas = []
    monkeypatch.setattr(main.threading, "Thread", lambda **kw: tareas.append(kw["target"]) or MagicMock())
    monkeypatch.setattr(main, "generar_todos", lambda df: {"donut": "donut.png"})

    app._generar_graficos()
    app.aplicar_filtros({"jurisdicciones": ["Comisaria 13°"]})   # cambia mientras se generan
    tareas[0]()

    assert app.rutas_graficos == {}
    assert app._generando is False


# ─── Modo terminal ────────────────────────────────────────────────────────────

@pytest.fixture
def archivo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ruta = tmp_path / "denuncias.csv"
    _datos()[["legajo", "fecha", "hora", "tipo_delito", "jurisdiccion"]].to_csv(ruta, index=False)
    return str(ruta)


def test_cli_completa(archivo, monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["cli.py", "--archivo", archivo])
    assert cli.main() == 0
    assert len(list((tmp_path / "salidas" / "graficos").glob("*.png"))) == 6
    assert len(list((tmp_path / "salidas" / "reportes").glob("*.pdf"))) == 1


def test_cli_filtro_sin_resultados(archivo, monkeypatch):
    monkeypatch.setattr("sys.argv", ["cli.py", "--archivo", archivo, "--anio", "1990"])
    assert cli.main() == 1


def test_cli_archivo_inexistente(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["cli.py", "--archivo", str(tmp_path / "nada.xlsx")])
    assert cli.main() == 1
