"""
modulos/procesador.py
Carga, limpieza y transformación del Excel de denuncias.
"""
import pandas as pd
import numpy as np
import csv
from pathlib import Path


COLUMNAS_REQUERIDAS = {
    "legajo", "fecha", "hora",
    "tipo_delito", "jurisdiccion",
}

COLUMNAS_OPCIONALES = {
    "modalidad", "estado", "latitud", "longitud", "descripcion", "delito",
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
        # Intentar lectura directa primero
        try:
            df = pd.read_csv(ruta)
        except Exception:
            df = None

        # Normalizar nombres y comprobar columnas; si faltan, reintentar
        def _cols_ok(df_):
            if df_ is None:
                return False
            cols = [c.strip().lower().replace(" ", "_") for c in df_.columns]
            return COLUMNAS_REQUERIDAS.issubset(set(cols))

        if not _cols_ok(df):
            # Intentar detectar separador con csv.Sniffer y reintentar con encoding comunes
            contenido = None
            try:
                with open(ruta, "r", errors="replace") as f:
                    contenido = f.read(8192)
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(contenido)
                sep = dialect.delimiter
            except Exception:
                sep = None

            intentos = []
            if sep:
                intentos.append({"sep": sep, "encoding": None})
            # probar separadores comunes y codificaciones
            for s in [";", "\t", ",", "|"]:
                intentos.append({"sep": s, "encoding": None})
                intentos.append({"sep": s, "encoding": "latin1"})

            df_ok = None
            for intento in intentos:
                try:
                    if intento["encoding"]:
                        df_try = pd.read_csv(ruta, sep=intento["sep"], encoding=intento["encoding"] )
                    else:
                        df_try = pd.read_csv(ruta, sep=intento["sep"])
                    if _cols_ok(df_try):
                        df_ok = df_try
                        break
                except Exception:
                    continue

            if df_ok is not None:
                df = df_ok
            else:
                # último intento: leer con engine python y sep=None (pandas inferirá)
                try:
                    df = pd.read_csv(ruta, sep=None, engine="python")
                except Exception:
                    # dejar df como estaba (posible None) y que la validación posterior falle
                    pass
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
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce", dayfirst=True)
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
    for col in ["tipo_delito", "delito", "jurisdiccion", "modalidad", "estado"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title()

    # Eliminar duplicados exactos
    # (el nro_denuncia puede repetirse entre jurisdicciones distintas;
    # el duplicado real es la combinación jurisdiccion + nro_denuncia)
    
    
    antes = len(df)
    subset_dup = ["jurisdiccion", "legajo"] if "jurisdiccion" in df.columns else ["legajo"]
    df = df.drop_duplicates(subset=subset_dup)
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
        col = _col_delito(df)
        mask &= df[col].isin(tipos_delito)
    if anio:
        mask &= df["anio"] == int(anio)

    return df[mask].copy()


# ─── Resúmenes ────────────────────────────────────────────────────────────────

def _col_delito(df: pd.DataFrame) -> str:
    """Devuelve 'delito' si la columna existe, sino 'tipo_delito'."""
    return "delito" if "delito" in df.columns else "tipo_delito"


def resumen_general(df: pd.DataFrame) -> dict:
    """Devuelve un dict con métricas clave para mostrar en la GUI."""
    col = _col_delito(df)
    return {
        "total_denuncias":   len(df),
        "periodo_desde":     df["fecha"].min().strftime("%d/%m/%Y"),
        "periodo_hasta":     df["fecha"].max().strftime("%d/%m/%Y"),
        "tipos_delito":      df[col].nunique(),
        "jurisdicciones":    df["jurisdiccion"].nunique(),
        "delito_principal":  df[col].value_counts().idxmax(),
        "jurisdiccion_top":  df["jurisdiccion"].value_counts().idxmax(),
        "mes_pico":          df["mes_nombre"].value_counts().idxmax(),
    }


def tabla_pivot(df: pd.DataFrame,
                filas="jurisdiccion",
                columnas=None) -> pd.DataFrame:
    """Tabla cruzada lista para mostrar o exportar."""
    if columnas is None:
        columnas = _col_delito(df)
    return pd.crosstab(df[filas], df[columnas], margins=True, margins_name="Total")
