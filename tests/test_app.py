"""Tests del estado de la interfaz (main.py) y del modo terminal (cli.py), sin abrir ventana."""
import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

import cli
import main
from modulos import graficos, rutas
from modulos.graficos import generar_todos
from modulos.mapa import generar_mapa_html, tipos_disponibles
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

    asyncio.run(app._exportar_pdf())
    assert app.alertas == ["Sin gráficos"]


def _elegir_destino(monkeypatch, ruta, al_elegir=None):
    """Simula el diálogo 'Guardar como' devolviendo 'ruta'."""
    async def save_file(self, **kwargs):
        if al_elegir:
            al_elegir()
        return ruta
    monkeypatch.setattr(main.ft.FilePicker, "save_file", save_file)


def test_el_pdf_se_guarda_donde_elige_el_usuario(app, monkeypatch, tmp_path, carpeta_de_trabajo):
    app.rutas_graficos = generar_todos(app.df_filtrado)
    assert all(Path(r).is_relative_to(carpeta_de_trabajo) for r in app.rutas_graficos.values())

    destino = tmp_path / "mis reportes" / "informe"       # sin extensión
    _elegir_destino(monkeypatch, str(destino))
    asyncio.run(app._exportar_pdf())

    assert app.alertas == ["PDF Exportado"]
    assert destino.with_suffix(".pdf").read_bytes().startswith(b"%PDF")


def test_el_pdf_conserva_los_puntos_del_nombre(app, monkeypatch, tmp_path):
    app.rutas_graficos = generar_todos(app.df_filtrado)
    _elegir_destino(monkeypatch, str(tmp_path / "informe v1.2"))
    asyncio.run(app._exportar_pdf())
    assert (tmp_path / "informe v1.2.pdf").exists()
    assert not (tmp_path / "informe v1.pdf").exists()


def test_no_pisa_un_pdf_que_el_dialogo_no_confirmo(app, monkeypatch, tmp_path):
    existente = tmp_path / "informe.pdf"
    existente.write_bytes(b"otro reporte")
    _elegir_destino(monkeypatch, str(tmp_path / "informe"))
    asyncio.run(app._exportar_pdf())
    assert app.alertas == ["El archivo ya existe"]
    assert existente.read_bytes() == b"otro reporte"


def test_la_carpeta_de_trabajo_siempre_es_absoluta(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(rutas.VARIABLE_CARPETA, "portable datos")
    assert rutas.ruta_mapa() == tmp_path / "portable datos" / "mapa.html"
    assert rutas.carpeta_documentos().is_dir()


def test_la_app_abre_aunque_no_se_pueda_crear_el_registro(monkeypatch, tmp_path):
    estorbo = tmp_path / "es_un_archivo"
    estorbo.write_text("x")
    monkeypatch.setenv(rutas.VARIABLE_CARPETA, str(estorbo))
    monkeypatch.setattr(main.logging, "basicConfig", lambda **kw: None)
    main.configurar_registro()   # no debe lanzar


def test_cancelar_el_dialogo_no_exporta(app, monkeypatch):
    _elegir_destino(monkeypatch, None)
    asyncio.run(app._exportar_pdf())
    assert app.alertas == []


def test_si_los_datos_cambian_con_el_dialogo_abierto_no_se_exporta(app, monkeypatch, tmp_path):
    destino = tmp_path / "informe.pdf"
    _elegir_destino(monkeypatch, str(destino),
                    al_elegir=lambda: app.aplicar_filtros({"jurisdicciones": ["Comisaria 13°"]}))
    asyncio.run(app._exportar_pdf())
    assert app.alertas == ["Los datos cambiaron"]
    assert not destino.exists()


def test_un_grafico_que_falla_se_informa_en_actividad(app, monkeypatch, tmp_path):
    def roto(df, carpeta):
        raise RuntimeError("sin datos de hora")
    monkeypatch.setattr(graficos, "grafico_heatmap_horario", roto)

    rutas = generar_todos(app.df_filtrado, carpeta=tmp_path)

    assert "heatmap_horario" not in rutas and len(rutas) == 5
    assert "heatmap_horario" in app.txt_log.value
    assert "sin datos de hora" in app.txt_log.value


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


def test_el_mapa_se_guarda_en_la_carpeta_de_trabajo(carpeta_de_trabajo):
    df = _datos()
    df["latitud"] = -31.53
    df["longitud"] = -68.53
    ruta = generar_mapa_html(df)
    assert ruta == carpeta_de_trabajo / "mapa.html"
    assert ruta.stat().st_size > 0


def test_las_capas_del_mapa_son_los_delitos_y_no_las_caratulas(tmp_path):
    df = _limpiar(pd.DataFrame([
        {"legajo": i, "fecha": "4/3/2025", "hora": "10:00", "jurisdiccion": "COMISARIA 13°",
         "tipo_delito": caratula, "DELITO": delito, "latitud": -31.53, "longitud": -68.53}
        for i, (caratula, delito) in enumerate([
            ("ROBO AGRAVADO", "ROBO"), ("HURTO CALIFICADO", "HURTO"),
            ("ABIGEATO", "OTROS"), ("TTVA. ROBO", "TTVA ROBO"),
        ])
    ]).rename(columns={"DELITO": "delito"}))

    assert tipos_disponibles(df) == ["Robo", "Hurto", "Ttva Robo", "Otros"]

    contenido = generar_mapa_html(df, ruta=tmp_path / "mapa.html").read_text(encoding="utf-8")
    capas = contenido[contenido.index("overlays"):]
    assert '"Robo"' in capas and '"Otros"' in capas
    assert "Robo Agravado" not in capas and "Abigeato" not in capas
    assert "tile.openstreetmap.fr" not in capas          # el mapa base no es una opción
    assert "Car\\u00e1tula" in contenido or "Carátula" in contenido   # el detalle va en el globo


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
