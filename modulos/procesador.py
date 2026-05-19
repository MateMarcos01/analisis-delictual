"""
modulos/procesador.py
Carga, limpieza y transformación del Excel de denuncias.
"""
import pandas as pd
import numpy as np
from pathlib import Path


COLUMNAS_REQUERIDAS = {
    "nro_denuncia", "fecha", "hora",
    "tipo_delito", "jurisdiccion",
}

COLUMNAS_OPCIONALES = {
    "modalidad", "estado", "latitud", "longitud", "descripcion",
}


# ─── Carga ────────────────────────────────────────────────────────────────────

def cargar_excel(ruta: str) -> pd.DataFrame:
    """
    Lee un archivo .xlsx o .csv y devuelve un DataFrame limpio.
    Lanza ValueError si faltan columnas obligatorias.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {ruta}")

    if ruta.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(ruta, engine="openpyxl")
    elif ruta.suffix.lower() == ".csv":
        df = pd.read_csv(ruta)
    else:
        raise ValueError("Formato no soportado. Usar .xlsx o .csv")

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    _validar_columnas(df)
    df = _limpiar(df)
    return df


def _validar_columnas(df: pd.DataFrame) -> None:
    faltantes = COLUMNAS_REQUERIDAS - set(df.columns)
    if faltantes:
        raise ValueError(
            f"Faltan columnas obligatorias: {', '.join(sorted(faltantes))}"
        )


# ─── Limpieza ─────────────────────────────────────────────────────────────────

def _limpiar(df: pd.DataFrame) -> pd.DataFrame:
    """Parsea fechas, elimina duplicados, normaliza strings."""
    df = df.copy()

    # Fechas
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    registros_invalidos = df["fecha"].isna().sum()
    if registros_invalidos:
        print(f"  ⚠  {registros_invalidos} registros con fecha inválida eliminados.")
    df = df.dropna(subset=["fecha"])

    # Hora → datetime
    if "hora" in df.columns:
        df["hora_dt"] = pd.to_datetime(
            df["fecha"].dt.date.astype(str) + " " + df["hora"].astype(str),
            errors="coerce"
        )

    # Columnas de texto → strip + title case
    for col in ["tipo_delito", "jurisdiccion", "modalidad", "estado"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title()

    # Eliminar duplicados exactos
    antes = len(df)
    df = df.drop_duplicates(subset=["nro_denuncia"])
    eliminados = antes - len(df)
    if eliminados:
        print(f"  ⚠  {eliminados} duplicados eliminados.")

    # Columnas derivadas útiles
    df["anio"]         = df["fecha"].dt.year
    df["mes"]          = df["fecha"].dt.month
    df["mes_nombre"]   = df["fecha"].dt.strftime("%b")
    df["dia_semana"]   = df["fecha"].dt.day_name()
    df["dia_semana_n"] = df["fecha"].dt.dayofweek   # 0=lunes
    df["trimestre"]    = df["fecha"].dt.quarter
    if "hora_dt" in df.columns:
        df["hora_num"]    = df["hora_dt"].dt.hour
        df["franja"]      = pd.cut(
            df["hora_num"],
            bins=[0, 6, 12, 18, 24],
            labels=["Madrugada", "Mañana", "Tarde", "Noche"],
            right=False
        )

    return df.reset_index(drop=True)


# ─── Filtros ──────────────────────────────────────────────────────────────────

def filtrar(
    df: pd.DataFrame,
    fecha_desde=None,
    fecha_hasta=None,
    jurisdicciones=None,
    tipos_delito=None,
    anio=None,
) -> pd.DataFrame:
    """
    Aplica filtros opcionales y devuelve el DataFrame filtrado.
    """
    mask = pd.Series([True] * len(df), index=df.index)

    if fecha_desde:
        mask &= df["fecha"] >= pd.to_datetime(fecha_desde)
    if fecha_hasta:
        mask &= df["fecha"] <= pd.to_datetime(fecha_hasta)
    if jurisdicciones:
        mask &= df["jurisdiccion"].isin(jurisdicciones)
    if tipos_delito:
        mask &= df["tipo_delito"].isin(tipos_delito)
    if anio:
        mask &= df["anio"] == int(anio)

    return df[mask].copy()


# ─── Resúmenes ────────────────────────────────────────────────────────────────

def resumen_general(df: pd.DataFrame) -> dict:
    """Devuelve un dict con métricas clave para mostrar en la GUI."""
    return {
        "total_denuncias":   len(df),
        "periodo_desde":     df["fecha"].min().strftime("%d/%m/%Y"),
        "periodo_hasta":     df["fecha"].max().strftime("%d/%m/%Y"),
        "tipos_delito":      df["tipo_delito"].nunique(),
        "jurisdicciones":    df["jurisdiccion"].nunique(),
        "delito_principal":  df["tipo_delito"].value_counts().idxmax(),
        "jurisdiccion_top":  df["jurisdiccion"].value_counts().idxmax(),
        "mes_pico":          df["mes_nombre"].value_counts().idxmax(),
    }


def tabla_pivot(df: pd.DataFrame,
                filas="jurisdiccion",
                columnas="tipo_delito") -> pd.DataFrame:
    """Tabla cruzada lista para mostrar o exportar."""
    return pd.crosstab(df[filas], df[columnas], margins=True, margins_name="Total")
