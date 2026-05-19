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
from pathlib import Path

# ─── Paleta corporativa ───────────────────────────────────────────────────────

PALETA = ["#534AB7", "#1D9E75", "#D85A30", "#BA7517", "#185FA5", "#993556"]
FUENTE = {"family": "sans-serif", "size": 10}

def _estilo():
    """Aplica estilo global limpio antes de cada gráfico."""
    sns.set_theme(style="whitegrid", palette=PALETA)
    plt.rcParams.update({
        "font.family":       "sans-serif",
        "axes.spines.top":   False,
        "axes.spines.right": False,
        "axes.titlesize":    13,
        "axes.titleweight":  "bold",
        "axes.titlepad":     12,
        "figure.dpi":        130,
    })

def _guardar(fig, carpeta: str, nombre: str) -> str:
    """Guarda la figura y devuelve la ruta."""
    Path(carpeta).mkdir(parents=True, exist_ok=True)
    ruta = str(Path(carpeta) / nombre)
    fig.savefig(ruta, bbox_inches="tight", dpi=150)
    return ruta


# ─── 1. Barras por tipo de delito ─────────────────────────────────────────────

def grafico_barras_tipo(df: pd.DataFrame,
                        carpeta="salidas/graficos") -> str:
    _estilo()
    conteo = df["tipo_delito"].value_counts().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.bar(conteo.index, conteo.values,
                  color=PALETA[:len(conteo)], edgecolor="white", linewidth=0.5)

    # Etiqueta de valor encima de cada barra
    for bar in bars:
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + conteo.max() * 0.01,
            str(int(bar.get_height())),
            ha="center", va="bottom", fontsize=9, color="#444"
        )

    ax.set_title("Denuncias por tipo de delito")
    ax.set_xlabel("Tipo de delito")
    ax.set_ylabel("Cantidad de denuncias")
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    plt.tight_layout()
    return _guardar(fig, carpeta, "barras_tipo_delito.png")


# ─── 2. Serie temporal mensual ────────────────────────────────────────────────

def grafico_serie_temporal(df: pd.DataFrame,
                           carpeta="salidas/graficos") -> str:
    _estilo()
    serie = (
        df.groupby(df["fecha"].dt.to_period("M"))
          .size()
          .reset_index(name="total")
    )
    serie["fecha_str"] = serie["fecha"].astype(str)

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(serie["fecha_str"], serie["total"],
            color=PALETA[0], linewidth=2, marker="o", markersize=4)
    ax.fill_between(range(len(serie)), serie["total"],
                    alpha=0.12, color=PALETA[0])

    # Marcar el pico
    idx_max = serie["total"].idxmax()
    ax.annotate(
        f"Pico: {int(serie.loc[idx_max,'total'])}",
        xy=(idx_max, serie.loc[idx_max, "total"]),
        xytext=(idx_max, serie.loc[idx_max, "total"] + serie["total"].max() * 0.06),
        fontsize=8, color=PALETA[2],
        arrowprops=dict(arrowstyle="->", color=PALETA[2], lw=1),
    )

    ax.set_title("Evolución mensual de denuncias")
    ax.set_xlabel("")
    ax.set_ylabel("Denuncias")
    tick_step = max(1, len(serie) // 12)
    ax.set_xticks(range(0, len(serie), tick_step))
    ax.set_xticklabels(serie["fecha_str"].iloc[::tick_step], rotation=45, ha="right", fontsize=8)
    plt.tight_layout()
    return _guardar(fig, carpeta, "serie_temporal.png")


# ─── 3. Barras apiladas por jurisdicción ─────────────────────────────────────

def grafico_barras_jurisdiccion(df: pd.DataFrame,
                                carpeta="salidas/graficos") -> str:
    _estilo()
    pivot = pd.crosstab(df["jurisdiccion"], df["tipo_delito"])

    fig, ax = plt.subplots(figsize=(10, 5))
    pivot.plot(kind="bar", stacked=True, ax=ax,
               color=PALETA[:len(pivot.columns)], edgecolor="white",
               linewidth=0.4, width=0.65)

    ax.set_title("Tipo de delito por jurisdicción")
    ax.set_xlabel("Jurisdicción")
    ax.set_ylabel("Denuncias")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=30, ha="right")
    ax.legend(title="Tipo de delito", bbox_to_anchor=(1.02, 1),
              loc="upper left", fontsize=8, title_fontsize=9)
    plt.tight_layout()
    return _guardar(fig, carpeta, "barras_jurisdiccion.png")


# ─── 4. Heatmap hora × día de la semana ──────────────────────────────────────

def grafico_heatmap_horario(df: pd.DataFrame,
                             carpeta="salidas/graficos") -> str:
    _estilo()
    if "hora_num" not in df.columns:
        raise ValueError("El DataFrame no tiene columna 'hora_num'. Ejecutar procesador primero.")

    ORDEN_DIAS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    NOMBRES_ES = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
    FRANJAS    = ["0–4 h","4–8 h","8–12 h","12–16 h","16–20 h","20–24 h"]

    df2 = df.copy()
    df2["franja_num"] = df2["hora_num"] // 4         # 0..5
    df2["dia_en"]     = df2["dia_semana"]

    pivot = (
        df2.groupby(["franja_num", "dia_en"])
           .size()
           .unstack(fill_value=0)
           .reindex(columns=[d for d in ORDEN_DIAS if d in df2["dia_en"].unique()])
    )
    pivot.index = FRANJAS[:len(pivot)]
    pivot.columns = [NOMBRES_ES[ORDEN_DIAS.index(d)] for d in pivot.columns]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    sns.heatmap(pivot, cmap="YlOrRd", annot=True, fmt="d",
                linewidths=0.4, linecolor="white",
                cbar_kws={"label": "N° denuncias"}, ax=ax)
    ax.set_title("Concentración de denuncias: franja horaria × día de la semana")
    ax.set_xlabel("")
    ax.set_ylabel("Franja horaria")
    plt.tight_layout()
    return _guardar(fig, carpeta, "heatmap_horario.png")


# ─── 5. Donut de proporción por tipo ─────────────────────────────────────────

def grafico_donut(df: pd.DataFrame,
                  carpeta="salidas/graficos") -> str:
    _estilo()
    conteo = df["tipo_delito"].value_counts()
    total  = conteo.sum()

    fig, ax = plt.subplots(figsize=(7, 5))
    wedges, texts, autotexts = ax.pie(
        conteo.values,
        labels=None,
        autopct="%1.1f%%",
        pctdistance=0.78,
        colors=PALETA[:len(conteo)],
        wedgeprops=dict(width=0.52, edgecolor="white", linewidth=1.5),
        startangle=90,
    )
    for at in autotexts:
        at.set_fontsize(8)
        at.set_color("white")
        at.set_fontweight("bold")

    ax.legend(
        wedges, [f"{k} ({v:,})" for k, v in conteo.items()],
        loc="center left", bbox_to_anchor=(1, 0.5),
        fontsize=9, frameon=False,
    )
    ax.text(0, 0, f"Total\n{total:,}", ha="center", va="center",
            fontsize=11, fontweight="bold", color="#333")
    ax.set_title("Distribución por tipo de delito")
    plt.tight_layout()
    return _guardar(fig, carpeta, "donut_tipos.png")


# ─── 6. Ranking de jurisdicciones ────────────────────────────────────────────

def grafico_ranking_jurisdiccion(df: pd.DataFrame,
                                  carpeta="salidas/graficos") -> str:
    _estilo()
    conteo = df["jurisdiccion"].value_counts().sort_values()

    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.barh(conteo.index, conteo.values,
                   color=PALETA[0], edgecolor="white")
    for bar in bars:
        ax.text(bar.get_width() + conteo.max() * 0.01,
                bar.get_y() + bar.get_height() / 2,
                str(int(bar.get_width())),
                va="center", fontsize=9, color="#444")

    ax.set_title("Denuncias por jurisdicción")
    ax.set_xlabel("Cantidad de denuncias")
    ax.set_xlim(0, conteo.max() * 1.12)
    plt.tight_layout()
    return _guardar(fig, carpeta, "ranking_jurisdiccion.png")


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
    """
    Genera los 7 gráficos y devuelve un dict {nombre: ruta}.
    """
    rutas = {}
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
            rutas[nombre] = fn(df, carpeta)
            print(f"  ✓  {nombre}")
        except Exception as e:
            print(f"  ✗  {nombre}: {e}")
    return rutas
