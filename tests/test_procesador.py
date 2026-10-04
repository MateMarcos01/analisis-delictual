"""Tests de carga, limpieza, filtros y resúmenes (modulos/procesador.py)."""
from datetime import datetime, time

import pandas as pd
import pytest

from modulos.procesador import (
    _limpiar, cargar_excel, filtrar, resumen_general, tabla_pivot,
    validar_datos_completos,
)


def _crudo(fechas, horas=None, legajos=None, jurisdicciones=None, delitos=None):
    """Arma un DataFrame como el que sale de leer el archivo, antes de limpiar."""
    n = len(fechas)
    return pd.DataFrame({
        "legajo": pd.Series(legajos if legajos is not None else range(1, n + 1), dtype=object),
        "fecha": pd.Series(fechas, dtype=object),
        "hora": pd.Series(horas if horas is not None else ["10:00"] * n, dtype=object),
        "tipo_delito": delitos if delitos is not None else ["ROBO"] * n,
        "jurisdiccion": jurisdicciones if jurisdicciones is not None else ["COMISARIA 13°"] * n,
    })


def _fechas(df):
    return df["fecha"].dt.strftime("%Y-%m-%d").tolist()


# ─── Fechas ───────────────────────────────────────────────────────────────────

def test_fechas_iso_en_texto_no_cruzan_dia_y_mes():
    df = _limpiar(_crudo(["2025-01-04", "2025-02-05", "2025-03-06"]))
    assert _fechas(df) == ["2025-01-04", "2025-02-05", "2025-03-06"]


def test_fechas_dia_mes_anio_se_leen_con_dia_primero():
    df = _limpiar(_crudo(["4/1/2025", "13/1/2025", "01/02/2025"]))
    assert _fechas(df) == ["2025-01-04", "2025-01-13", "2025-02-01"]


def test_fechas_en_formatos_mezclados_no_se_pierden():
    df = _limpiar(_crudo([
        "4/1/2025", "2025-01-15", "15-01-2025", "4/1/25",
        datetime(2025, 3, 2), "2025-06-07 00:00:00", 45667,
    ]))
    assert _fechas(df) == [
        "2025-01-04", "2025-01-15", "2025-01-15", "2025-01-04",
        "2025-03-02", "2025-06-07", "2025-01-10",
    ]
    assert df.attrs["descartes"]["fechas_invalidas"] == 0


def test_fechas_invalidas_se_descartan_y_se_informan():
    df = _limpiar(_crudo(["4/1/2025", "no es fecha", None, "32/1/2025", 7]))
    assert _fechas(df) == ["2025-01-04"]
    assert df.attrs["descartes"]["fechas_invalidas"] == 4


@pytest.mark.parametrize("mala", ["5/1/2925", "01/01/1500", datetime(2925, 1, 5)])
def test_anio_mal_tipeado_descarta_solo_esa_fila(mala):
    df = _limpiar(_crudo(["4/1/2025", mala, "6/1/2025"]))
    assert _fechas(df) == ["2025-01-04", "2025-01-06"]
    assert df.attrs["descartes"]["fechas_invalidas"] == 1


def test_fecha_estilo_mes_dia_no_se_interpreta_mal():
    df = _limpiar(_crudo(["4/1/2025", "1/13/2025"]))
    assert _fechas(df) == ["2025-01-04"]


def test_mes_en_castellano_sin_depender_del_sistema():
    df = _limpiar(_crudo(["15/1/2025", "15/8/2025", "15/12/2025"]))
    assert df["mes_nombre"].tolist() == ["Ene", "Ago", "Dic"]


# ─── Horas ────────────────────────────────────────────────────────────────────

def test_horas_en_distintos_formatos():
    df = _limpiar(_crudo(
        ["4/1/2025"] * 6,
        horas=["02:45", "19:10:00", time(21, 50), "7:05", "14.30", "23h59"],
    ))
    assert df["hora_num"].tolist() == [2, 19, 21, 7, 14, 23]
    assert df["franja"].astype(str).tolist() == [
        "Madrugada", "Noche", "Noche", "Mañana", "Tarde", "Noche",
    ]
    assert df.attrs["descartes"]["horas_invalidas"] == 0


def test_horas_con_am_pm():
    df = _limpiar(_crudo(
        ["4/1/2025"] * 5,
        horas=["9:05 PM", "1:30 pm", "12:15 AM", "11:59 p.m.", "12:30hs"],
    ))
    assert df["hora_num"].tolist() == [21, 13, 0, 23, 12]


def test_hora_invalida_no_descarta_el_registro():
    horas = ["25:30", "sin dato", None, "12:345", "13:00 PM", pd.NaT]
    df = _limpiar(_crudo(["4/1/2025"] * len(horas), horas=horas))
    assert len(df) == len(horas)
    assert df["hora_num"].isna().all()
    assert df.attrs["descartes"]["horas_invalidas"] == len(horas)


# ─── Duplicados ───────────────────────────────────────────────────────────────

def test_duplicado_real_se_elimina():
    df = _limpiar(_crudo(["4/1/2025", "5/1/2025"], legajos=[7, 7]))
    assert len(df) == 1
    assert df.attrs["descartes"]["duplicados"] == 1


def test_mismo_legajo_en_otra_jurisdiccion_o_en_otro_anio_se_conserva():
    df = _limpiar(_crudo(
        ["4/1/2025", "4/1/2025", "4/1/2024"],
        legajos=[7, 7, 7],
        jurisdicciones=["COMISARIA 13°", "COMISARIA 15°", "COMISARIA 13°"],
    ))
    assert len(df) == 3


def test_registros_sin_legajo_se_conservan():
    df = _limpiar(_crudo(["4/1/2025", "5/1/2025", "6/1/2025"], legajos=[None, None, None]))
    assert len(df) == 3


# ─── Filtros y resúmenes ──────────────────────────────────────────────────────

@pytest.fixture
def df_ejemplo():
    return _limpiar(_crudo(
        ["4/1/2025", "5/1/2025", "6/2/2025", "7/2/2025"],
        legajos=[1, 2, 1, 2],
        jurisdicciones=["COMISARIA 13°", "COMISARIA 13°", "COMISARIA 15°", "COMISARIA 15°"],
        delitos=["ROBO", "HURTO", "ROBO", "ROBO"],
    ))


def test_resumen_general(df_ejemplo):
    r = resumen_general(df_ejemplo)
    assert r["total_denuncias"] == 4
    assert r["periodo_desde"] == "04/01/2025"
    assert r["periodo_hasta"] == "07/02/2025"
    assert r["delito_principal"] == "Robo"


def test_filtro_sin_resultados_no_rompe(df_ejemplo):
    vacio = filtrar(df_ejemplo, jurisdicciones=["Comisaria 13°"], anio=1990)
    assert vacio.empty
    r = resumen_general(vacio)
    assert r["total_denuncias"] == 0
    assert r["mes_pico"] == "—"
    assert validar_datos_completos(vacio)["resumen"]["cobertura_datos"] == "0.0%"
    tabla_pivot(vacio)   # no debe lanzar


def test_filtro_por_jurisdiccion_y_delito(df_ejemplo):
    f = filtrar(df_ejemplo, jurisdicciones=["Comisaria 15°"], tipos_delito=["Robo"])
    assert len(f) == 2


def test_tabla_pivot_incluye_totales(df_ejemplo):
    p = tabla_pivot(df_ejemplo)
    assert p.loc["Total", "Total"] == 4
    assert p.loc["Comisaria 13°", "Hurto"] == 1


# ─── Lectura de archivos ──────────────────────────────────────────────────────

def test_csv_con_punto_y_coma_latin1_y_fechas_iso(tmp_path):
    ruta = tmp_path / "denuncias.csv"
    ruta.write_text(
        "legajo;fecha;hora;tipo_delito;jurisdiccion\n"
        "1;2025-01-04;10:00;Daño;COMISARÍA 13°\n"
        "2;2025-02-05;11:30;Robo;COMISARÍA 13°\n",
        encoding="latin1",
    )
    df = cargar_excel(str(ruta))
    assert _fechas(df) == ["2025-01-04", "2025-02-05"]
    assert df["tipo_delito"].tolist() == ["Daño", "Robo"]


def test_xlsx_descarta_columnas_sin_encabezado(tmp_path):
    ruta = tmp_path / "denuncias.xlsx"
    crudo = _crudo(["2025-01-04", "2025-02-05"])
    crudo["Unnamed: 9"] = [None, 1.0]
    crudo.to_excel(ruta, index=False)
    df = cargar_excel(str(ruta))
    assert not [c for c in df.columns if c.startswith("unnamed")]
    assert _fechas(df) == ["2025-01-04", "2025-02-05"]


def test_csv_vacio_da_un_error_claro(tmp_path):
    ruta = tmp_path / "vacio.csv"
    ruta.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="No se pudo leer"):
        cargar_excel(str(ruta))


def test_faltan_columnas_obligatorias(tmp_path):
    ruta = tmp_path / "mal.csv"
    ruta.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Faltan columnas obligatorias"):
        cargar_excel(str(ruta))
