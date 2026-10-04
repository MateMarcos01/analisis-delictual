"""
modulos/procesador.py
Carga, limpieza y transformación del Excel de denuncias.
"""
import pandas as pd
import numpy as np
import csv
import logging
import re
from datetime import date, datetime, time
from pathlib import Path

logger = logging.getLogger(__name__)

MESES_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

# Formatos de fecha aceptados cuando la celda viene como texto. Son explícitos
# a propósito: dejar que pandas adivine cruza día y mes en fechas ISO.
FORMATOS_FECHA = [
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%Y-%m-%d", "%Y/%m/%d",
    "%d/%m/%y", "%d-%m-%y",
]

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

    if df is None:
        raise ValueError("No se pudo leer el archivo: está vacío o no es una tabla válida.")

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    # Columnas sin encabezado que Excel agrega por celdas sueltas fuera de la tabla
    df = df.loc[:, [c for c in df.columns if not c.startswith("unnamed")]]
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

def _parsear_fechas(serie: pd.Series) -> pd.Series:
    """
    Convierte la columna de fechas a datetime sin adivinar el formato.
    Acepta celdas que ya son fecha, números de serie de Excel y textos en
    alguno de FORMATOS_FECHA (con día primero cuando hay ambigüedad).
    Lo que no se puede interpretar queda como NaT.
    """
    if pd.api.types.is_datetime64_any_dtype(serie):
        return _solo_anios_razonables(serie.dt.tz_localize(None).dt.normalize())

    # Microsegundos y no nanosegundos: un año mal tipeado (2925) no entra en el
    # rango de nanosegundos y haría fallar toda la carga en vez de una fila.
    resultado = pd.Series(pd.NaT, index=serie.index, dtype="datetime64[us]")

    es_fecha = serie.map(lambda v: isinstance(v, (datetime, date)) and not pd.isna(v))
    if es_fecha.any():
        resultado[es_fecha] = serie[es_fecha].map(
            lambda v: datetime(v.year, v.month, v.day)
        ).astype("datetime64[us]")

    # Número de serie de Excel (días desde 1899-12-30); se limita a 1950–2099
    # para no convertir en fecha un número cualquiera.
    es_serial = serie.map(
        lambda v: isinstance(v, (int, float, np.integer, np.floating))
        and not isinstance(v, bool) and 18264 <= v <= 73050
    )
    if es_serial.any():
        resultado[es_serial] = pd.to_datetime(
            serie[es_serial].astype(float), unit="D", origin="1899-12-30"
        ).astype("datetime64[us]")

    es_texto = serie.map(lambda v: isinstance(v, str))
    pendientes = (
        serie[es_texto].astype(str).str.strip()
        # "2025-01-04 00:00:00" o "2025-01-04T00:00:00": se descarta la hora
        .str.replace(r"[ T]\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?$", "", regex=True)
    )
    for formato in FORMATOS_FECHA:
        if pendientes.empty:
            break
        parseadas = pd.to_datetime(pendientes, format=formato, errors="coerce")
        ok = parseadas.notna()
        resultado[parseadas.index[ok]] = parseadas[ok].astype("datetime64[us]")
        pendientes = pendientes[~ok]

    return _solo_anios_razonables(resultado.dt.normalize())


def _solo_anios_razonables(fechas: pd.Series) -> pd.Series:
    """Deja como NaT las fechas fuera de 1950–2099: son errores de tipeo."""
    return fechas.where(fechas.dt.year.between(1950, 2099))


_RE_HORA = re.compile(
    r"^(\d{1,2})\s*[:.h]\s*(\d{2})"          # 14:30, 14.30, 14h30
    r"(?:\s*:\s*\d{2}(?:\.\d+)?)?"           # segundos opcionales
    r"\s*(hs?\.?|[ap]\.?\s*m\.?)?$",         # "hs" o a.m./p.m.
    re.IGNORECASE,
)


def _parsear_hora(valor):
    """Devuelve (hora, minuto) o None si el valor no es una hora válida."""
    if valor is None or valor is pd.NaT:
        return None
    if isinstance(valor, (time, datetime)):
        return valor.hour, valor.minute
    if not isinstance(valor, str):
        return None
    m = _RE_HORA.match(valor.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    sufijo = (m.group(3) or "").lower()
    if sufijo[:1] in ("a", "p"):
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if sufijo[0] == "p" else 0)
    if h > 23 or mi > 59:
        return None
    return h, mi


def _limpiar(df: pd.DataFrame) -> pd.DataFrame:
    """Parsea fechas, elimina duplicados, normaliza strings."""
    df = df.copy()

    # Fechas
    df["fecha"] = _parsear_fechas(df["fecha"])
    registros_invalidos = int(df["fecha"].isna().sum())
    if registros_invalidos:
        logger.warning("%d registros con fecha inválida eliminados.", registros_invalidos)
    df = df.dropna(subset=["fecha"])

    # Hora → datetime
    horas_invalidas = 0
    if "hora" in df.columns:
        partes = df["hora"].map(_parsear_hora)
        horas_invalidas = int(partes.isna().sum())
        if horas_invalidas:
            logger.warning("%d registros con hora no interpretable.", horas_invalidas)
        minutos = partes.map(lambda p: p[0] * 60 + p[1] if p else np.nan)
        df["hora_dt"] = df["fecha"] + pd.to_timedelta(minutos, unit="m")

    # Columnas de texto → strip + title case
    for col in ["tipo_delito", "delito", "jurisdiccion", "modalidad", "estado"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title()

    df["anio"] = df["fecha"].dt.year

    # Eliminar duplicados
    # (cada jurisdicción numera sus legajos desde 1 y vuelve a empezar cada año:
    # el duplicado real es la combinación jurisdiccion + año + legajo.
    # Las filas sin legajo no se pueden comparar, así que se conservan.)
    antes = len(df)
    duplicada = df["legajo"].notna() & df.duplicated(subset=["jurisdiccion", "anio", "legajo"])
    df = df[~duplicada]
    eliminados = antes - len(df)
    if eliminados:
        logger.warning("%d duplicados eliminados.", eliminados)

    # Columnas derivadas útiles
    df["mes"]          = df["fecha"].dt.month
    df["mes_nombre"]   = df["mes"].map(lambda m: MESES_ES[m - 1])
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

    df = df.reset_index(drop=True)
    # Lo que se descartó al limpiar, para que la interfaz pueda informarlo
    df.attrs["descartes"] = {
        "fechas_invalidas": registros_invalidos,
        "duplicados": eliminados,
        "horas_invalidas": horas_invalidas,
    }
    return df


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
    cobertura = (len(df) - registros_con_nulos) / len(df) * 100 if len(df) else 0.0
    resumen["cobertura_datos"] = f"{cobertura:.1f}%"


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
    if df.empty:
        return {
            "total_denuncias":   0,
            "periodo_desde":     "—",
            "periodo_hasta":     "—",
            "tipos_delito":      0,
            "jurisdicciones":    0,
            "delito_principal":  "—",
            "jurisdiccion_top":  "—",
            "mes_pico":          "—",
        }
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
