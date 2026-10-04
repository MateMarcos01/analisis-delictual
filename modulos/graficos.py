"""
modulos/graficos.py
Todas las visualizaciones del proyecto.
Cada función recibe un DataFrame procesado y devuelve fig de matplotlib.
"""
import matplotlib
matplotlib.use("Agg")          # sin pantalla (para servidor / tests)
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import pandas as pd
import numpy as np
import logging
import threading
from pathlib import Path
from matplotlib.patches import FancyBboxPatch
from matplotlib.colors import LinearSegmentedColormap

logger = logging.getLogger(__name__)
_CANDADO = threading.Lock()

# ─── Paleta corporativa ───────────────────────────────────────────────────────

PALETA = ["#534AB7", "#1D9E75", "#D85A30", "#BA7517", "#185FA5", "#993556"]
FUENTE = {"family": "sans-serif", "size": 10}

def _estilo():
    """Estilo global: fondo suave, sin bordes, tipografía limpia."""
    sns.set_theme(style="white", palette=PALETA)
    plt.rcParams.update({
        "font.family":        "sans-serif",
        "font.sans-serif":    ["Segoe UI", "Calibri", "Arial", "DejaVu Sans"],
        "font.size":          10,
        "text.color":         "#2D2D3A",
        "axes.labelcolor":    "#6B6B7B",
        "xtick.color":        "#6B6B7B",
        "ytick.color":        "#6B6B7B",
        "axes.facecolor":     "#FFFFFF",
        "figure.facecolor":   "#FFFFFF",
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        "axes.spines.left":   False,
        "axes.spines.bottom": False,
        "axes.grid":          True,
        "axes.grid.axis":     "y",
        "grid.color":         "#ECECF1",
        "grid.linewidth":     0.8,
        "axes.axisbelow":     True,
        "axes.titlesize":     15,
        "axes.titleweight":   "bold",
        "axes.titlelocation": "left",
        "axes.titlepad":      16,
        "xtick.major.size":   0,
        "ytick.major.size":   0,
        "figure.dpi":         130,
    })

def _guardar(fig, carpeta: str, nombre: str) -> str:
    """Guarda la figura y devuelve la ruta."""
    Path(carpeta).mkdir(parents=True, exist_ok=True)
    ruta = str(Path(carpeta) / nombre)
    fig.savefig(ruta, bbox_inches="tight", dpi=150)
    return ruta, fig


# ─── 1. Barras por tipo de delito ─────────────────────────────────────────────

def _col_delito(df):
    return "delito" if "delito" in df.columns else "tipo_delito"

def _barras_redondeadas(ax, x, alturas, colores, ancho=0.6, radio=0.12):
    """Dibuja barras verticales con la parte de arriba redondeada."""
    if isinstance(colores, str):
        colores = [colores] * len(alturas)
    ymax = max(alturas) if len(alturas) else 1
    for xi, h, c in zip(x, alturas, colores):
        caja = FancyBboxPatch(
            (xi - ancho / 2, 0), ancho, h,
            boxstyle=f"round,pad=0,rounding_size={radio}",
            mutation_aspect=ymax / 10,
            facecolor=c, edgecolor="none",
        )
        ax.add_patch(caja)
    ax.set_xlim(-0.6, len(x) - 0.4)
    ax.set_ylim(0, ymax * 1.15)

import textwrap

COLORES_DELITO = {
    "robo":       "#D7263D",  # rojo
    "hurto":      "#2E9E5B",  # verde
    "ttva_robo":  "#F28C28",  # naranja
    "ttva_hurto": "#F2C230",  # amarillo
    "otros":      "#534AB7",  # morado
}

AZUL = "#2A78D6"
AZUL_SUAVE = "#A9C9EF"
MESES_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

def _color_delito(nombre: str) -> str:
    """Devuelve el color fijo según el tipo de delito."""
    n = str(nombre).lower()
    es_tentativa = "tentativa" in n or "ttva" in n
    if "robo" in n:
        return COLORES_DELITO["ttva_robo" if es_tentativa else "robo"]
    if "hurto" in n:
        return COLORES_DELITO["ttva_hurto" if es_tentativa else "hurto"]
    return COLORES_DELITO["otros"]

def grafico_barras_tipo(df: pd.DataFrame, carpeta="salidas/graficos"):
    _estilo()
    col = _col_delito(df)
    conteo = df[col].value_counts().sort_values(ascending=False)
    x = range(len(conteo))
    colores = [_color_delito(n) for n in conteo.index]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    _barras_redondeadas(ax, x, conteo.values, colores)

    for xi, v in zip(x, conteo.values):
        ax.text(xi, v + conteo.max() * 0.02, f"{int(v)}",
                ha="center", va="bottom", fontsize=11,
                fontweight="bold", color="#2D2D3A")

    ax.set_xticks(list(x))
    ax.set_xticklabels(
        [textwrap.fill(str(n), 14) for n in conteo.index],
        rotation=0, ha="center", fontsize=10, fontweight="semibold",
    )
    ax.set_title("Denuncias por delito")
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    plt.tight_layout()
    return _guardar(fig, carpeta, "barras_tipo_delito.png")

# ─── 2. Serie temporal mensual ────────────────────────────────────────────────

def grafico_serie_temporal(df: pd.DataFrame, carpeta="salidas/graficos"):
    _estilo()
    fechas = df["fecha"].dropna()
    serie = fechas.dt.to_period("M").value_counts().sort_index()
    # Si falta algún mes en el medio, aparece con 0 en vez de saltearse
    serie = serie.reindex(
        pd.period_range(serie.index.min(), serie.index.max(), freq="M"),
        fill_value=0,
    )
    n = len(serie)
    x = np.arange(n)
    y = serie.values
    varios_anios = serie.index.year.nunique() > 1
    etiquetas = [
        f"{MESES_ES[p.month - 1]}\n{p.year}" if varios_anios else MESES_ES[p.month - 1]
        for p in serie.index
    ]
    promedio = y.mean()

    fig, ax = plt.subplots(figsize=(10, 4.2))

    # Línea de promedio
    ax.axhline(promedio, color="#898781", linestyle=(0, (4, 4)), linewidth=1, zorder=1)
    ax.text(n - 1, promedio + y.max() * 0.015, f"Promedio {promedio:.0f}",
            ha="right", va="bottom", fontsize=9, color="#6B6B7B")

    # Línea principal
    ax.plot(x, y, color=AZUL, linewidth=2.6, zorder=3,
            solid_capstyle="round", solid_joinstyle="round")

    # Solo el pico y el mínimo llevan punto y etiqueta
    imax, imin = int(y.argmax()), int(y.argmin())
    marcas = [(imax, "Pico", 12, "bottom")]
    if imin != imax:
        marcas.append((imin, "Mínimo", -12, "top"))
    for i, texto, desplazo, va in marcas:
        ax.scatter([i], [y[i]], s=80, color=AZUL, edgecolor="white",
                   linewidth=2, zorder=4)
        ax.annotate(f"{texto}  {int(y[i])}", (i, y[i]),
                    xytext=(0, desplazo), textcoords="offset points",
                    ha="center", va=va, fontsize=10,
                    fontweight="bold", color="#2D2D3A")

    paso = max(1, n // 12)
    ax.set_xticks(x[::paso])
    ax.set_xticklabels(etiquetas[::paso], rotation=0, ha="center",
                       fontsize=10, fontweight="semibold")
    ax.set_xlim(-0.4, n - 0.6)
    ax.set_ylim(0, y.max() * 1.18)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.set_title("Evolución mensual de denuncias")
    ax.set_xlabel("")
    ax.set_ylabel("")
    plt.tight_layout()
    return _guardar(fig, carpeta, "serie_temporal.png")


# ─── 3. Barras apiladas por jurisdicción ─────────────────────────────────────

def _barras_h_redondeadas(ax, valores, colores, alto=0.62):
    """Barras horizontales con extremos redondeados (largo exacto)."""
    n = len(valores)
    xmax = max(valores) * 1.3
    ax.set_xlim(0, xmax)
    ax.set_ylim(-0.6, n - 0.4)
    radio = xmax * 0.016
    aspecto = 2 * n / xmax   # compensa la escala distinta de cada eje
    for i, (v, c) in enumerate(zip(valores, colores)):
        ax.add_patch(FancyBboxPatch(
            (0, i - alto / 2), v, alto,
            boxstyle=f"round,pad=0,rounding_size={radio}",
            mutation_aspect=aspecto,
            facecolor=c, edgecolor="none",
        ))

def grafico_ranking_jurisdiccion(df: pd.DataFrame, carpeta="salidas/graficos"):
    _estilo()
    # Ascendente: la barra más larga queda arriba
    conteo = df["jurisdiccion"].value_counts().sort_values(ascending=True)
    total = conteo.sum()
    maximo = conteo.max()
    colores = [AZUL if v == maximo else AZUL_SUAVE for v in conteo.values]

    fig, ax = plt.subplots(figsize=(8, 4))
    _barras_h_redondeadas(ax, conteo.values, colores)

    for i, v in enumerate(conteo.values):
        pct = f"{v / total * 100:.1f}".replace(".", ",")
        ax.text(v + maximo * 0.02, i, f"{int(v)}  ·  {pct}%",
                va="center", ha="left", fontsize=11,
                fontweight="bold" if v == maximo else "semibold",
                color="#2D2D3A")

    ax.set_yticks(range(len(conteo)))
    ax.set_yticklabels(conteo.index, fontsize=11, fontweight="semibold")
    ax.set_xticks([])
    ax.grid(False)
    ax.tick_params(length=0)
    ax.set_title("Denuncias por jurisdicción")
    ax.set_xlabel("")
    plt.tight_layout()
    return _guardar(fig, carpeta, "ranking_jurisdiccion.png")

# ─── 4. Heatmap hora × día de la semana ──────────────────────────────────────

def grafico_heatmap_horario(df: pd.DataFrame, carpeta="salidas/graficos"):
    _estilo()
    if "hora_num" not in df.columns:
        raise ValueError("El DataFrame no tiene columna 'hora_num'. Ejecutar procesador primero.")

    ORDEN_DIAS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    NOMBRES_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    FRANJAS    = ["0–4 h", "4–8 h", "8–12 h", "12–16 h", "16–20 h", "20–24 h"]

    df2 = df.dropna(subset=["hora_num", "dia_semana"]).copy()
    df2["franja_num"] = (df2["hora_num"] // 4).astype(int).clip(0, 5)

    # Siempre 6 franjas x 7 días, aunque falte algún dato
    pivot = (
        df2.groupby(["franja_num", "dia_semana"]).size()
           .unstack(fill_value=0)
           .reindex(index=range(6), columns=ORDEN_DIAS, fill_value=0)
    )
    valores = pivot.values
    vmin, vmax = valores.min(), valores.max()
    cmap = LinearSegmentedColormap.from_list("azul_suave", ["#EAF2FC", "#2A78D6"])

    ancho, alto, paso_y = 0.92, 0.58, 0.7
    imax = np.unravel_index(valores.argmax(), valores.shape)

    fig, ax = plt.subplots(figsize=(9, 5))
    for i in range(valores.shape[0]):
        for j in range(valores.shape[1]):
            v = valores[i, j]
            t = (v - vmin) / (vmax - vmin) if vmax > vmin else 0
            es_pico = (i, j) == imax
            ax.add_patch(FancyBboxPatch(
                (j - ancho / 2, i * paso_y - alto / 2), ancho, alto,
                boxstyle="round,pad=0,rounding_size=0.1",
                facecolor=cmap(t),
                edgecolor="#2D2D3A" if es_pico else "none",
                linewidth=2 if es_pico else 0,
            ))
            ax.text(j, i * paso_y, f"{int(v)}", ha="center", va="center",
                    fontsize=11, fontweight="bold",
                    color="white" if t > 0.55 else "#2D2D3A")

    ax.set_xlim(-0.55, 6.55)
    ax.set_ylim(5 * paso_y + 0.4, -0.4)
    ax.set_aspect("equal")
    ax.grid(False)

    ax.set_xticks(range(7))
    ax.set_xticklabels(NOMBRES_ES, fontsize=10, fontweight="semibold")
    ax.xaxis.tick_top()
    ax.set_yticks([i * paso_y for i in range(6)])
    ax.set_yticklabels(FRANJAS, fontsize=10, fontweight="semibold")
    ax.tick_params(length=0)

    ax.set_title("Denuncias por franja horaria y día", pad=46)
    ax.annotate(
        f"Pico: {NOMBRES_ES[imax[1]]}, {FRANJAS[imax[0]]}  ·  {int(vmax)} denuncias",
        xy=(0, 1), xycoords="axes fraction",
        xytext=(0, 24), textcoords="offset points",
        fontsize=10, color="#6B6B7B",
    )
    plt.tight_layout()
    return _guardar(fig, carpeta, "heatmap_horario.png")

# ─── 5. Donut de proporción por tipo ─────────────────────────────────────────

def grafico_donut(df: pd.DataFrame, carpeta="salidas/graficos"):
    _estilo()
    col = _col_delito(df)
    conteo = df[col].value_counts()
    total = conteo.sum()
    colores = [_color_delito(n) for n in conteo.index]

    fig, ax = plt.subplots(figsize=(7, 5))
    wedges, _ = ax.pie(
        conteo.values,
        colors=colores,
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=0.38, edgecolor="white", linewidth=2),
    )

    ax.legend(
        wedges,
        [f"{k}  ·  {v:,}  ({v / total:.1%})" for k, v in conteo.items()],
        loc="center left", bbox_to_anchor=(1, 0.5),
        fontsize=10, frameon=False, labelspacing=1.1,
    )
    ax.text(0, 0.06, f"{total:,}", ha="center", va="center",
            fontsize=22, fontweight="bold", color="#2D2D3A")
    ax.text(0, -0.16, "denuncias", ha="center", va="center",
            fontsize=10, color="#6B6B7B")
    ax.set_title("Distribución por delito")
    plt.tight_layout()
    return _guardar(fig, carpeta, "donut_tipos.png")


# ─── 6. Ranking de jurisdicciones ────────────────────────────────────────────

def grafico_barras_jurisdiccion(df: pd.DataFrame, carpeta="salidas/graficos"):
    _estilo()
    col = _col_delito(df)
    pivot = pd.crosstab(df["jurisdiccion"], df[col])

    # Orden fijo de apilado: Robo, Hurto, Ttva Robo, Ttva Hurto, Otros
    def _orden(nombre):
        n = str(nombre).lower()
        tentativa = "tentativa" in n or "ttva" in n
        if "robo" in n:
            return 2 if tentativa else 0
        if "hurto" in n:
            return 3 if tentativa else 1
        return 4

    pivot = pivot[sorted(pivot.columns, key=_orden)]

    fig, ax = plt.subplots(figsize=(10, 5))
    pivot.plot(
        kind="bar", stacked=True, ax=ax,
        color=[_color_delito(c) for c in pivot.columns],
        edgecolor="white", linewidth=1, width=0.62,
    )

    # Total encima de cada barra
    totales = pivot.sum(axis=1)
    for i, t in enumerate(totales.values):
        ax.text(i, t + totales.max() * 0.015, f"{int(t):,}",
                ha="center", va="bottom", fontsize=11,
                fontweight="bold", color="#2D2D3A")
    ax.set_ylim(0, totales.max() * 1.12)

    ax.set_title("Delito por jurisdicción")
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=0)
    for lbl in ax.get_xticklabels():
        lbl.set_fontweight("semibold")
        lbl.set_ha("center")
    ax.legend(title=None, bbox_to_anchor=(1.02, 1), loc="upper left",
              fontsize=10, frameon=False, labelspacing=1.0)
    plt.tight_layout()
    return _guardar(fig, carpeta, "barras_jurisdiccion.png")

# ─── 7. Evolución anual comparada ────────────────────────────────────────────

def grafico_comparacion_anual(df: pd.DataFrame,
                               carpeta="salidas/graficos") -> str:
    _estilo()
    anios = sorted(df["anio"].unique())
    if len(anios) < 2:
        raise ValueError("Se necesitan al menos 2 años para comparar.")

    fig, ax = plt.subplots(figsize=(10, 4.5))
    for i, anio in enumerate(anios):
        sub = (
            df[df["anio"] == anio]
              .groupby("mes")
              .size()
              .reindex(range(1, 13), fill_value=0)
        )
        MESES = ["Ene","Feb","Mar","Abr","May","Jun",
                 "Jul","Ago","Sep","Oct","Nov","Dic"]
        ax.plot(MESES[:len(sub)], sub.values,
                label=str(anio), color=PALETA[i % len(PALETA)],
                linewidth=2, marker="o", markersize=4)

    ax.set_title("Comparación de denuncias por mes y año")
    ax.set_ylabel("Denuncias")
    ax.legend(title="Año")
    plt.tight_layout()
    return _guardar(fig, carpeta, "comparacion_anual.png")


# ─── Generar todos de una vez ─────────────────────────────────────────────────

def generar_todos(df: pd.DataFrame, carpeta="salidas/graficos") -> dict:
    """Genera todos los gráficos y devuelve {nombre: ruta_png}."""
    # pyplot guarda estado global y los archivos tienen nombre fijo:
    # dos generaciones a la vez se pisarían entre sí.
    with _CANDADO:
        return _generar_todos(df, carpeta)


def _generar_todos(df: pd.DataFrame, carpeta) -> dict:
    rutas = {}
    if df.empty:
        return rutas
    funciones = [
        ("barras_tipo",         grafico_barras_tipo),
        ("serie_temporal",      grafico_serie_temporal),
        ("barras_jurisdiccion", grafico_barras_jurisdiccion),
        ("heatmap_horario",     grafico_heatmap_horario),
        ("donut",               grafico_donut),
        ("ranking_jurisdiccion",grafico_ranking_jurisdiccion),
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
