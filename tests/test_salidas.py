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
        "barras_tipo", "serie_temporal", "barras_jurisdiccion", "heatmap_horario",
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


def _con_anios(anios, jurisdicciones=2):
    return _limpiar(pd.DataFrame([
        {"legajo": i, "fecha": f"{(i % 27) + 1}/{(i % 12) + 1}/{anios[i % len(anios)]}",
         "hora": f"{i % 24:02d}:00", "tipo_delito": ["ROBO", "HURTO", "Ttva Robo", "Estafa"][i % 4],
         "jurisdiccion": f"COMISARIA {i % jurisdicciones + 1}°"}
        for i in range(240)
    ]))


def test_el_tablero_de_la_app_arma_una_tarjeta_por_grafico():
    from modulos.graficos_app import tablero
    assert len(tablero(_df()).controls) == 4
    assert len(tablero(_con_anios([2023, 2024, 2025])).controls) == 5


def test_cada_delito_conserva_su_color_y_su_orden():
    from modulos.graficos import COLORES_DELITO, _color_delito, conteo_delitos
    df = _con_anios([2025])
    assert list(conteo_delitos(df).index) == ["Robo", "Hurto", "Ttva Robo", "Estafa"]
    # Filtrar no repinta: el color sigue al delito, no a su posición
    solo_hurto = filtrar(df, tipos_delito=["Hurto"])
    assert _color_delito(conteo_delitos(solo_hurto).index[0]) == COLORES_DELITO["hurto"]


def test_la_matriz_horaria_cuenta_cada_denuncia_una_vez():
    from modulos.graficos import matriz_horaria
    df = _df()
    tabla = matriz_horaria(df)
    assert tabla.shape == (4, 7)
    assert tabla.values.sum() == df["hora_num"].notna().sum()


def test_un_pdf_con_muchas_jurisdicciones_entra_en_la_hoja(tmp_path):
    df = _con_anios([2025], jurisdicciones=40)
    rutas = generar_todos(df, carpeta=str(tmp_path))
    ruta_pdf = generar_reporte(resumen_general(df), rutas, tabla_pivot(df), carpeta=str(tmp_path))
    assert Path(ruta_pdf).read_bytes().startswith(b"%PDF")


def test_el_informe_redacta_las_cifras_de_los_datos():
    from datetime import date
    from modulos.informe import construir_informe, html_informe
    informe = construir_informe(_df(), hoy=date(2026, 10, 9))
    assert informe["emitido"] == "09/10/2026"
    assert informe["textos"]["resumen"].startswith("Entre el ")
    assert "60 hechos en 2 comisarías" in informe["textos"]["resumen"]
    # Robo, Hurto y Ttva Robo aparecen 20 veces cada uno
    assert informe["textos"]["delitos"].startswith("El delito más frecuente fue ")
    assert [d["cantidad"] for d in informe["delitos"]] == [20, 20, 20]
    assert [f["franja"] for f in informe["horario"]["filas"]][0] == "00:00 a 05:59"
    assert sum(f["total"] for f in informe["horario"]["filas"]) == 60
    pagina = html_informe(informe)
    assert "Informe de evaluación delictual" in pagina and "60" in pagina


def test_el_informe_escapa_los_textos_de_la_planilla():
    from modulos.informe import construir_informe, html_informe
    df = _df()
    df["jurisdiccion"] = "<script>alert(1)</script>"
    pagina = html_informe(construir_informe(df))
    assert "<script>alert(1)" not in pagina


def test_el_informe_sin_datos_lo_dice():
    from modulos.informe import construir_informe, html_informe
    pagina = html_informe(construir_informe(filtrar(_df(), anio=1990)))
    assert "no hay nada que informar" in pagina


def test_el_informe_pdf_se_imprime_con_el_navegador(tmp_path):
    import pytest
    from modulos.informe import buscar_navegadores, exportar_informe
    if not buscar_navegadores():
        pytest.skip("No hay Edge ni Chrome en esta computadora")
    ruta = exportar_informe(_df(), tmp_path / "informe.pdf")
    assert ruta.read_bytes().startswith(b"%PDF")


def test_si_un_navegador_falla_se_prueba_el_siguiente(tmp_path):
    import pytest
    from modulos.informe import NavegadorNoEncontrado, buscar_navegadores, exportar_informe
    roto = str(tmp_path / "no_existe.exe")
    with pytest.raises(NavegadorNoEncontrado):
        exportar_informe(_df(), tmp_path / "a.pdf", navegadores=[roto])
    if buscar_navegadores():
        ruta = exportar_informe(_df(), tmp_path / "b.pdf", navegadores=[roto, *buscar_navegadores()])
        assert ruta.read_bytes().startswith(b"%PDF")


def _df_con_coordenadas():
    df = _df()
    df["latitud"] = [-31.53 - i / 1000 for i in range(len(df))]
    df["longitud"] = -68.53
    df.loc[0, "latitud"] = None   # sin coordenadas: no entra en el mapa
    return df


def test_la_hoja_de_mapa_trae_puntos_y_leyenda_por_delito():
    import pytest
    from modulos.informe import construir_mapa, html_informe
    mapa = construir_mapa(_df_con_coordenadas())
    assert mapa["con_coordenadas"] == 59 and mapa["sin_coordenadas"] == 1
    assert [d["nombre"] for d in mapa["delitos"]] == ["Robo", "Hurto", "Ttva Robo"]
    assert sum(d["cantidad"] for d in mapa["delitos"]) == len(mapa["puntos"]) == 59
    pagina = html_informe(mapa, "mapa.html")
    assert "Mapa de hechos" in pagina and "A4 landscape" in pagina
    with pytest.raises(ValueError):
        construir_mapa(_df())   # sin columnas de coordenadas


def test_la_hoja_de_mapa_se_imprime_en_una_pagina(tmp_path):
    import re
    import pytest
    from modulos.informe import buscar_navegadores, exportar_mapa
    if not buscar_navegadores():
        pytest.skip("No hay Edge ni Chrome en esta computadora")
    contenido = exportar_mapa(_df_con_coordenadas(), tmp_path / "mapa.pdf").read_bytes()
    assert contenido.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page[^s]", contenido)) == 1
