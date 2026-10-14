"""
modulos/graficos.py
Paleta y datos de los gráficos, y su versión en imagen (PNG) para el PDF.

Los mismos datos (conteo_delitos, serie_mensual, ...) alimentan los gráficos
interactivos de la app (modulos/graficos_app.py): app y PDF muestran lo mismo.
"""
import matplotlib
matplotlib.use("Agg")          # sin pantalla (para servidor / tests)
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import numpy as np
import logging
import threading
from pathlib import Path
from matplotlib.patches import FancyBboxPatch

from modulos.procesador import MESES_ES, col_delito
from modulos.rutas import carpeta_graficos

logger = logging.getLogger(__name__)
_CANDADO = threading.Lock()

# ─── Paleta ───────────────────────────────────────────────────────────────────
# Tinta y grilla: los mismos tonos que la interfaz (main.py)
TINTA = "#1E293B"
TENUE = "#64748B"
GRILLA = "#E2E8F0"
SUPERFICIE = "#FFFFFF"

# Azul: el total de denuncias (ningún delito usa azul, así no se confunde con
# uno). Es la serie que importa; el resto va en gris de contexto.
ACENTO = "#2A78D6"
CONTEXTO = ["#94A3B8", "#CBD5E1", "#E2E8F0"]

# Un color fijo por delito, los mismos que usa el sistema web del Departamento
# Planeamiento: rojo robo, verde hurto, naranja tentativa de robo, amarillo
# tentativa de hurto, violeta el resto. Rojo y verde se confunden con
# daltonismo: por eso los gráficos siempre llevan leyenda o nombre al lado.
COLORES_DELITO = {
    "robo":       "#E60000",  # rojo
    "hurto":      "#00A63E",  # verde
    "ttva_robo":  "#FF7A00",  # naranja
    "ttva_hurto": "#FFD000",  # amarillo
    "otros":      "#8E24D6",  # violeta
}
# Delitos agrupados cuando son demasiados para mostrarlos uno por uno
COLOR_RESTO = "#9AA39A"
_GRUPOS = ["robo", "hurto", "ttva_robo", "ttva_hurto", "otros"]

# Rampa del mapa de calor: un solo tono, de casi blanco a azul oscuro.
# Tiene pasos intermedios: mezclar directo los extremos da un tono apagado.
_CALOR_PASOS = [0, 0.45, 0.8, 1]
_CALOR_COLORES = np.array([[0xEE, 0xF5, 0xFD], [0x9E, 0xC5, 0xF4], [0x2A, 0x78, 0xD6], [0x10, 0x42, 0x81]])
# Desde acá la celda lleva texto blanco
CALOR_TEXTO_BLANCO = 0.55

DIAS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
FRANJAS = ["00:00 a 05:59", "06:00 a 11:59", "12:00 a 17:59", "18:00 a 23:59"]


def _grupo_delito(nombre: str) -> str:
    n = str(nombre).lower()
    tentativa = any(p in n for p in ("tentativa", "ttva", "intento"))
    if "robo" in n:
        return "ttva_robo" if tentativa else "robo"
    if "hurto" in n:
        return "ttva_hurto" if tentativa else "hurto"
    return "otros"


def _color_delito(nombre: str) -> str:
    """Color fijo del delito: sigue al delito aunque cambien los filtros."""
    return COLORES_DELITO[_grupo_delito(nombre)]


def orden_delito(nombre: str):
    """Robo, Hurto, Ttva Robo, Ttva Hurto y el resto, en todos los gráficos y el mapa."""
    return (_GRUPOS.index(_grupo_delito(nombre)), str(nombre).lower())


def color_calor(t: float) -> str:
    """Color de la rampa del mapa de calor para t entre 0 y 1."""
    r, g, b = (round(float(np.interp(t, _CALOR_PASOS, _CALOR_COLORES[:, c]))) for c in range(3))
    return f"#{r:02X}{g:02X}{b:02X}"


def etiqueta_mes(periodo, con_anio: bool) -> str:
    return f"{MESES_ES[periodo.month - 1]} {periodo.year}" if con_anio else MESES_ES[periodo.month - 1]


# ─── Datos de cada gráfico (los usan la app y el PDF) ─────────────────────────

def conteo_delitos(df: pd.DataFrame) -> pd.Series:
    """Denuncias por delito, en el orden fijo de los delitos."""
    conteo = df[col_delito(df)].value_counts()
    return conteo[sorted(conteo.index, key=lambda n: (orden_delito(n)[0], -conteo[n]))]


def serie_mensual(df: pd.DataFrame) -> pd.Series:
    """Denuncias por mes; los meses sin denuncias aparecen con 0 en vez de saltearse."""
    serie = df["fecha"].dropna().dt.to_period("M").value_counts().sort_index()
    if serie.empty:
        return serie
    return serie.reindex(
        pd.period_range(serie.index.min(), serie.index.max(), freq="M"), fill_value=0
    )


def delitos_por_jurisdiccion(df: pd.DataFrame) -> pd.DataFrame:
    """Jurisdicción × delito; la jurisdicción con más denuncias primero."""
    tabla = pd.crosstab(df["jurisdiccion"], df[col_delito(df)])
    tabla = tabla[sorted(tabla.columns, key=orden_delito)]
    return tabla.loc[tabla.sum(axis=1).sort_values(ascending=False).index]


def matriz_horaria(df: pd.DataFrame) -> pd.DataFrame:
    """Franja de 6 h × día de la semana; siempre 4 × 7, aunque falten datos."""
    if "hora_num" not in df.columns:
        raise ValueError("El DataFrame no tiene columna 'hora_num'. Ejecutar procesador primero.")
    datos = df.dropna(subset=["hora_num", "dia_semana"])
    franja = (datos["hora_num"] // 6).astype(int).clip(0, 3)
    tabla = (
        datos.groupby([franja, datos["dia_semana"]]).size().unstack(fill_value=0)
             .reindex(index=range(len(FRANJAS)), columns=DIAS_EN, fill_value=0)
    )
    tabla.index, tabla.columns = FRANJAS, DIAS_ES
    return tabla


def mensual_por_anio(df: pd.DataFrame) -> pd.DataFrame:
    """Mes (1–12) × año."""
    return (
        df.groupby(["mes", "anio"]).size().unstack(fill_value=0)
          .reindex(range(1, 13), fill_value=0)
    )


# ─── Estilo de las imágenes ───────────────────────────────────────────────────

def _estilo():
    """Estilo global: fondo blanco, sin bordes, grilla y ejes en segundo plano."""
    plt.rcdefaults()
    plt.rcParams.update({
        "font.family":        "sans-serif",
        "font.sans-serif":    ["Segoe UI", "Calibri", "Arial", "DejaVu Sans"],
        "font.size":          10,
        "text.color":         TINTA,
        "axes.labelcolor":    TENUE,
        "xtick.color":        TENUE,
        "ytick.color":        TENUE,
        "xtick.labelsize":    9.5,
        "ytick.labelsize":    9.5,
        "axes.facecolor":     SUPERFICIE,
        "figure.facecolor":   SUPERFICIE,
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        "axes.spines.left":   False,
        "axes.spines.bottom": False,
        "axes.grid":          False,
        "grid.color":         GRILLA,
        "grid.linewidth":     0.8,
        "axes.axisbelow":     True,
        "xtick.major.size":   0,
        "ytick.major.size":   0,
        "figure.dpi":         130,
    })


def _subtitulo(ax, texto: str):
    """Lo que hay que leer del gráfico, arriba a la izquierda (el título lo pone el PDF)."""
    ax.text(0, 1.04, texto, transform=ax.transAxes, ha="left", va="bottom",
            fontsize=10.5, color=TENUE)


def _guardar(fig, carpeta: str, nombre: str) -> str:
    """Guarda la figura y devuelve la ruta (sin 'carpeta': la de trabajo de la app)."""
    carpeta = Path(carpeta).resolve() if carpeta else carpeta_graficos()
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = str(carpeta / nombre)
    fig.savefig(ruta, bbox_inches="tight", dpi=150)
    return ruta, fig


def _barras_h(ax, valores, colores, alto=0.5, izquierda=None):
    """Barras horizontales con el extremo de datos redondeado. Fila 0 arriba."""
    izquierda = np.zeros(len(valores)) if izquierda is None else izquierda
    ax.barh(range(len(valores)), valores, left=izquierda, height=alto,
            color=colores, edgecolor=SUPERFICIE, linewidth=1.2)
    ax.invert_yaxis()


def _porcentaje(parte, total) -> str:
    return f"{parte / total * 100:.1f}".replace(".", ",") + "%"


# ─── 1. Denuncias por delito ──────────────────────────────────────────────────

def grafico_barras_tipo(df: pd.DataFrame, carpeta=None):
    _estilo()
    conteo = conteo_delitos(df)
    total = conteo.sum()

    fig, ax = plt.subplots(figsize=(9, 0.9 + 0.42 * len(conteo)))
    _barras_h(ax, conteo.values, [_color_delito(n) for n in conteo.index])
    for i, v in enumerate(conteo.values):
        ax.text(v + conteo.max() * 0.015, i, f"{v:,}  ·  {_porcentaje(v, total)}",
                va="center", fontsize=10, color=TINTA)
    ax.set_yticks(range(len(conteo)), [str(n) for n in conteo.index], fontsize=10)
    ax.set_xticks([])
    ax.set_xlim(0, conteo.max() * 1.22)
    principal = conteo.idxmax()
    _subtitulo(ax, f"{principal}: {_porcentaje(conteo.max(), total)} de {total:,} denuncias")
    return _guardar(fig, carpeta, "barras_tipo_delito.png")


# ─── 2. Evolución mensual ─────────────────────────────────────────────────────

def grafico_serie_temporal(df: pd.DataFrame, carpeta=None):
    _estilo()
    serie = serie_mensual(df)
    n = len(serie)
    x = np.arange(n)
    y = serie.values
    varios_anios = serie.index.year.nunique() > 1

    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.grid(axis="y")
    ax.fill_between(x, y, color=ACENTO, alpha=0.08, linewidth=0)
    ax.plot(x, y, color=ACENTO, linewidth=1.8, solid_capstyle="round", solid_joinstyle="round")

    # Solo el pico y el último mes llevan punto y valor
    imax = int(y.argmax())
    for i in sorted({imax, n - 1}):
        ax.scatter([i], [y[i]], s=42, color=ACENTO, edgecolor=SUPERFICIE, linewidth=1.6, zorder=4)
        ax.annotate(f"{int(y[i]):,}", (i, y[i]), xytext=(0, 9), textcoords="offset points",
                    ha="center", va="bottom", fontsize=10, fontweight="semibold", color=TINTA)

    paso = max(1, n // 12)
    ax.set_xticks(x[::paso], [etiqueta_mes(p, varios_anios).replace(" ", "\n") for p in serie.index[::paso]])
    ax.set_xlim(-0.3, n - 0.7)
    ax.set_ylim(0, y.max() * 1.2)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=4, integer=True))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    _subtitulo(ax, f"Pico: {etiqueta_mes(serie.index[imax], True)}, {int(y[imax]):,} denuncias"
                   f"  ·  promedio {y.mean():,.0f} por mes")
    return _guardar(fig, carpeta, "serie_temporal.png")


# ─── 3. Delitos por jurisdicción ──────────────────────────────────────────────

def grafico_barras_jurisdiccion(df: pd.DataFrame, carpeta=None):
    _estilo()
    tabla = delitos_por_jurisdiccion(df)
    totales = tabla.sum(axis=1)

    fig, ax = plt.subplots(figsize=(10, 1.3 + 0.46 * len(tabla)))
    izquierda = np.zeros(len(tabla))
    for delito in tabla.columns:
        ax.barh(range(len(tabla)), tabla[delito].values, left=izquierda, height=0.5,
                color=_color_delito(delito), edgecolor=SUPERFICIE, linewidth=1.2, label=str(delito))
        izquierda += tabla[delito].values
    ax.invert_yaxis()
    for i, t in enumerate(totales.values):
        ax.text(t + totales.max() * 0.012, i, f"{int(t):,}", va="center", fontsize=10,
                fontweight="semibold", color=TINTA)
    ax.set_yticks(range(len(tabla)), [str(j) for j in tabla.index], fontsize=10)
    ax.set_xticks([])
    ax.set_xlim(0, totales.max() * 1.1)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=min(len(tabla.columns), 6),
              frameon=False, fontsize=9.5, handlelength=0.9, handleheight=0.9,
              columnspacing=1.4, borderaxespad=0.3, labelcolor=TENUE)
    ax.set_title(f"{tabla.index[0]} concentra {_porcentaje(totales.iloc[0], totales.sum())} de las denuncias",
                 loc="left", fontsize=10.5, color=TENUE, pad=30, fontweight="normal")
    return _guardar(fig, carpeta, "barras_jurisdiccion.png")


# ─── 4. Franja horaria × día ──────────────────────────────────────────────────

def grafico_heatmap_horario(df: pd.DataFrame, carpeta=None):
    _estilo()
    tabla = matriz_horaria(df)
    valores = tabla.values
    vmin, vmax = valores.min(), valores.max()
    imax = np.unravel_index(valores.argmax(), valores.shape)

    ancho, alto, paso_y = 0.9, 0.56, 0.66
    fig, ax = plt.subplots(figsize=(9, 3.6))
    for i in range(valores.shape[0]):
        for j in range(valores.shape[1]):
            v = valores[i, j]
            t = (v - vmin) / (vmax - vmin) if vmax > vmin else 0
            ax.add_patch(FancyBboxPatch(
                (j - ancho / 2, i * paso_y - alto / 2), ancho, alto,
                boxstyle="round,pad=0,rounding_size=0.08",
                facecolor=color_calor(t), edgecolor="none",
            ))
            ax.text(j, i * paso_y, f"{int(v)}", ha="center", va="center", fontsize=10,
                    fontweight="semibold" if (i, j) == imax else "normal",
                    color="white" if t > CALOR_TEXTO_BLANCO else TINTA)

    ax.set_xlim(-0.55, 6.55)
    ax.set_ylim((len(FRANJAS) - 1) * paso_y + 0.4, -0.4)
    ax.set_aspect("equal")
    ax.set_xticks(range(7), DIAS_ES)
    ax.xaxis.tick_top()
    ax.set_yticks([i * paso_y for i in range(len(FRANJAS))], FRANJAS)
    ax.set_title(f"Pico: {DIAS_ES[imax[1]]} de {FRANJAS[imax[0]]}, {int(vmax):,} denuncias",
                 loc="left", fontsize=10.5, color=TENUE, pad=30, fontweight="normal")
    return _guardar(fig, carpeta, "heatmap_horario.png")


# ─── 5. Comparación entre años ────────────────────────────────────────────────

def grafico_comparacion_anual(df: pd.DataFrame, carpeta=None):
    _estilo()
    tabla = mensual_por_anio(df)
    if tabla.shape[1] < 2:
        raise ValueError("Se necesitan al menos 2 años para comparar.")
    anios = list(tabla.columns)
    ultimo = anios[-1]

    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.grid(axis="y")
    x = np.arange(12)
    # Los años anteriores son contexto (gris); el último año es el que se lee
    for k, anio in enumerate(reversed(anios)):
        es_ultimo = anio == ultimo
        color = ACENTO if es_ultimo else CONTEXTO[min(k - 1, len(CONTEXTO) - 1)]
        y = tabla[anio].values
        ax.plot(x, y, color=color, linewidth=1.8 if es_ultimo else 1.4,
                zorder=3 if es_ultimo else 2, solid_capstyle="round", label=str(anio))
        ax.annotate(str(anio), (11, y[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9.5, color=TINTA if es_ultimo else TENUE)

    ax.set_xticks(x, MESES_ES)
    ax.set_xlim(-0.3, 11.6)
    ax.set_ylim(0, tabla.values.max() * 1.15)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=4, integer=True))
    previo = tabla[anios[-2]].sum()
    cambio = (tabla[ultimo].sum() - previo) / previo * 100 if previo else 0
    _subtitulo(ax, f"{ultimo}: {tabla[ultimo].sum():,} denuncias, "
                   f"{'+' if cambio >= 0 else '−'}{abs(cambio):.0f}% frente a {anios[-2]}".replace(".", ","))
    return _guardar(fig, carpeta, "comparacion_anual.png")


# ─── Generar todos de una vez ─────────────────────────────────────────────────

def generar_todos(df: pd.DataFrame, carpeta=None) -> dict:
    """Genera todos los gráficos y devuelve {nombre: ruta_png} con rutas absolutas.
    Sin 'carpeta', se guardan en la carpeta de trabajo de la aplicación."""
    if carpeta is None:
        carpeta = carpeta_graficos()
    # pyplot guarda estado global y los archivos tienen nombre fijo:
    # dos generaciones a la vez se pisarían entre sí.
    with _CANDADO:
        return _generar_todos(df, carpeta)


def _generar_todos(df: pd.DataFrame, carpeta) -> dict:
    rutas = {}
    if df.empty:
        return rutas
    funciones = [
        ("serie_temporal",      grafico_serie_temporal),
        ("barras_tipo",         grafico_barras_tipo),
        ("barras_jurisdiccion", grafico_barras_jurisdiccion),
        ("heatmap_horario",     grafico_heatmap_horario),
    ]
    if df["anio"].nunique() >= 2:
        funciones.append(("comparacion_anual", grafico_comparacion_anual))

    for nombre, fn in funciones:
        try:
            ruta, _ = fn(df, carpeta)
            rutas[nombre] = ruta
        except Exception:
            logger.exception("No se pudo generar el gráfico '%s'", nombre)
        finally:
            # También cierra la figura de un gráfico que falló a mitad de camino
            plt.close("all")
    return rutas
