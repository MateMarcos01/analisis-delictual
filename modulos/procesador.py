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


# ─── Validación de integridad ────────────────────────────────────────────────

def validar_datos_completos(df: pd.DataFrame) -> dict:
    """
    Valida la integridad y completitud de los datos.
    Retorna un dict con estado y lista de problemas encontrados.

    Parámetros:
        df (pd.DataFrame): DataFrame a validar

    Retorna:
        dict: {
            "valido": bool,
            "problemas": [str],
            "resumen": {estadísticas de validación}
        }
    """
    problemas = []
    resumen = {}

    # ───── 1. VALIDAR NULOS EN COLUMNAS CRÍTICAS ─────────────────────────────
    # .isnull() retorna un DataFrame booleano (True/False) para cada celda
    # .sum() suma los True (=cuenta cuántos nulls hay en cada columna)
    nulls_por_columna = df.isnull().sum()

    # .to_dict() convierte una Series (pandas) a un dict de Python normal
    # Ejemplo: Series([1, 2]) → {"col1": 1, "col2": 2}
    nulls_dict = nulls_por_columna[nulls_por_columna > 0].to_dict()

    if nulls_dict:
        msg = f"Valores NULL encontrados: {nulls_dict}"
        problemas.append(msg)
        resumen["nulls_por_columna"] = nulls_dict
    else:
        resumen["nulls_por_columna"] = "Sin nulos [OK]"


    # ───── 2. VALIDAR HORAS VÁLIDAS ──────────────────────────────────────────
    # Si existe la columna "hora_num" (creada en _limpiar())
    if "hora_num" in df.columns:
        # Crear máscara booleana: True si hora está fuera del rango 0-23
        # .loc[] es un indexador de pandas para seleccionar filas/columnas
        # & es operador AND lógico
        horas_invalidas = df.loc[(df["hora_num"] < 0) | (df["hora_num"] > 23)]

        if len(horas_invalidas) > 0:
            horas_unicas = horas_invalidas["hora_num"].unique().tolist()
            msg = f"{len(horas_invalidas)} horas fuera de rango (0-23): {horas_unicas}"
            problemas.append(msg)
            resumen["horas_invalidas"] = {
                "cantidad": len(horas_invalidas),
                "valores": horas_unicas
            }
        else:
            resumen["horas_invalidas"] = 0


    # ───── 3. VALIDAR FECHAS RAZONABLES ──────────────────────────────────────
    # .min() y .max() retornan el valor mínimo y máximo de una columna
    fecha_min = df["fecha"].min()
    fecha_max = df["fecha"].max()

    # Verificar que no haya fechas del pasado muy lejano (antes de 2000)
    if fecha_min.year < 2000:
        msg = f"Fechas muy antiguas detectadas (antes de 2000): mínima = {fecha_min.date()}"
        problemas.append(msg)
        resumen["fechas_antiguas"] = str(fecha_min.date())

    # Verificar que no haya fechas futuras (hoy es 2026, así que cualquiera > hoy es sospechosa)
    from datetime import datetime
    hoy = datetime.now()
    fechas_futuras = df[df["fecha"] > pd.Timestamp(hoy)]
    if len(fechas_futuras) > 0:
        msg = f"{len(fechas_futuras)} registros con fechas futuras (después de hoy)"
        problemas.append(msg)
        resumen["fechas_futuras"] = len(fechas_futuras)


    # ───── 4. VALIDAR QUE COLUMNAS CLAVE NO ESTÉN VACÍAS ─────────────────────
    # .nunique() cuenta cuántos valores ÚNICOS hay en una columna
    # Si es 0, la columna está completamente vacía
    for col in ["tipo_delito", "jurisdiccion"]:
        if df[col].nunique() == 0:
            msg = f"Columna '{col}' está completamente vacía"
            problemas.append(msg)


    # ───── 5. ESTADÍSTICAS GENERALES ─────────────────────────────────────────
    # len(df) retorna el número de filas del DataFrame
    registros_con_nulos = df.isnull().any(axis=1).sum()
    # .any(axis=1) chequea si hay al menos 1 NULL en CADA FILA
    # axis=1 significa "verificar por fila" (axis=0 sería por columna)

    resumen["total_registros"] = len(df)
    resumen["registros_con_nulos"] = registros_con_nulos
    resumen["registros_sanos"] = len(df) - registros_con_nulos
    resumen["cobertura_datos"] = f"{((len(df) - registros_con_nulos) / len(df) * 100):.1f}%"


    return {
        "valido": len(problemas) == 0,
        "problemas": problemas,
        "resumen": resumen
    }


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
