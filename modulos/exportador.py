"""
modulos/exportador.py
Genera un reporte PDF con los gráficos y un resumen estadístico.
"""
from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Image, Table, TableStyle, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from modulos.marca import LEMA, LOGO, NOMBRE_VISIBLE

ANCHO, ALTO = A4
MARGEN      = 2 * cm
MARGEN_SUPERIOR = 2.8 * cm   # deja lugar al membrete
PRIMARIO    = colors.HexColor("#DC143C")
ACENTO      = colors.HexColor("#FF7F50")
GRIS_CLARO  = colors.HexColor("#F1EFE8")
GRIS_TEXTO  = colors.HexColor("#4A4A4A")


def _estilos():
    base = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "titulo", parent=base["Title"],
        fontSize=20, textColor=PRIMARIO,
        spaceAfter=6, alignment=TA_CENTER,
    )
    subtitulo = ParagraphStyle(
        "subtitulo", parent=base["Heading2"],
        fontSize=13, textColor=PRIMARIO,
        spaceBefore=14, spaceAfter=4,
    )
    normal = ParagraphStyle(
        "normal_custom", parent=base["Normal"],
        fontSize=9, textColor=GRIS_TEXTO,
        leading=14,
    )
    return titulo, subtitulo, normal


def _membrete(canvas, doc):
    """Encabezado de cada página: logo, nombre de la app y lema."""
    canvas.saveState()
    x_texto = MARGEN
    if LOGO.is_file():
        lado = 1.4 * cm
        canvas.drawImage(str(LOGO), MARGEN, ALTO - 2.0 * cm, width=lado, height=lado, mask="auto")
        x_texto += lado + 0.3 * cm
    canvas.setFillColor(PRIMARIO)
    canvas.setFont("Helvetica-Bold", 15)
    canvas.drawString(x_texto, ALTO - 1.25 * cm, NOMBRE_VISIBLE)
    canvas.setFillColor(GRIS_TEXTO)
    canvas.setFont("Helvetica", 9)
    canvas.drawString(x_texto, ALTO - 1.7 * cm, LEMA)
    canvas.setStrokeColor(ACENTO)
    canvas.setLineWidth(1)
    canvas.line(MARGEN, ALTO - 2.2 * cm, ANCHO - MARGEN, ALTO - 2.2 * cm)
    canvas.restoreState()


def nombre_reporte() -> str:
    """Nombre de archivo sugerido para un reporte nuevo."""
    return f"reporte_delictual_{datetime.now():%Y%m%d_%H%M%S}.pdf"


def generar_reporte(
    resumen: dict,
    rutas_graficos: dict,
    tabla_pivot=None,
    carpeta: str = "salidas/reportes",
    nombre: str = None,
) -> str:
    """
    Genera el PDF completo y devuelve su ruta.

    resumen        : dict de resumen_general()
    rutas_graficos : dict {nombre: ruta_imagen}
    tabla_pivot    : DataFrame opcional para incluir como tabla
    """
    carpeta = Path(carpeta).resolve()
    carpeta.mkdir(parents=True, exist_ok=True)
    if not nombre:
        nombre = nombre_reporte()
    ruta_pdf = str(carpeta / nombre)

    doc = SimpleDocTemplate(
        ruta_pdf,
        pagesize=A4,
        leftMargin=MARGEN, rightMargin=MARGEN,
        topMargin=MARGEN_SUPERIOR, bottomMargin=MARGEN,
    )

    est_titulo, est_sub, est_normal = _estilos()
    story = []

    # ── Portada ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph("Reporte Estadístico de Denuncias", est_titulo))
    story.append(Spacer(1, 0.4 * cm))
    fecha_gen = datetime.now().strftime("%d/%m/%Y %H:%M")
    story.append(Paragraph(f"Generado el {fecha_gen}", est_normal))
    story.append(Spacer(1, 0.8 * cm))

    # ── Resumen general ───────────────────────────────────────────────────────
    story.append(Paragraph("1. Resumen ejecutivo", est_sub))

    datos_tabla = [
        ["Indicador", "Valor"],
        ["Total de denuncias",   f"{resumen['total_denuncias']:,}"],
        ["Período analizado",    f"{resumen['periodo_desde']} → {resumen['periodo_hasta']}"],
        ["Tipos de delito",      str(resumen["tipos_delito"])],
        ["Jurisdicciones",       str(resumen["jurisdicciones"])],
        ["Delito principal",     resumen["delito_principal"]],
        ["Jurisdicción con más denuncias", resumen["jurisdiccion_top"]],
        ["Mes de mayor actividad", resumen["mes_pico"]],
    ]

    t = Table(datos_tabla, colWidths=[8 * cm, 8 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARIO),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 9),
        ("FONTSIZE",   (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_CLARO]),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.HexColor("#B4B2A9")),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.6 * cm))

    # ── Tabla pivot (opcional) ────────────────────────────────────────────────
    if tabla_pivot is not None:
        story.append(Paragraph("2. Denuncias por jurisdicción y tipo", est_sub))
        df_t = tabla_pivot.reset_index()
        encabezado = [str(c) for c in df_t.columns.tolist()]
        filas = [[str(v) for v in row] for row in df_t.values.tolist()]
        datos_p = [encabezado] + filas
        n_cols = len(encabezado)
        ancho_col = (ANCHO - 2 * MARGEN) / n_cols
        tp = Table(datos_p, colWidths=[ancho_col] * n_cols)
        tp.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARIO),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 7),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_CLARO]),
            ("GRID",       (0, 0), (-1, -1), 0.3, colors.HexColor("#B4B2A9")),
            ("LEFTPADDING",  (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING",   (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
            ("BACKGROUND", (-1, 0), (-1, -1), ACENTO),
            ("BACKGROUND", (0, -1), (-1, -1), ACENTO),
            ("FONTNAME",   (-1, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold"),
        ]))
        story.append(tp)
        story.append(Spacer(1, 0.4 * cm))

    # ── Gráficos ──────────────────────────────────────────────────────────────
    TITULOS = {
        "barras_tipo":          "3. Denuncias por tipo de delito",
        "serie_temporal":       "4. Evolución mensual",
        "barras_jurisdiccion":  "5. Distribución por jurisdicción",
        "heatmap_horario":      "6. Concentración horaria y día",
        "donut":                "7. Proporción por tipo de delito",
        "ranking_jurisdiccion": "8. Ranking de jurisdicciones",
        "comparacion_anual":    "9. Comparación interanual",
    }

    img_ancho = ANCHO - 2 * MARGEN
    for clave, ruta in rutas_graficos.items():
        if not Path(ruta).exists():
            continue
        story.append(PageBreak())
        titulo_grafico = TITULOS.get(clave, clave.replace("_", " ").title())
        story.append(Paragraph(titulo_grafico, est_sub))
        story.append(Spacer(1, 0.2 * cm))
        img = Image(ruta, width=img_ancho, height=img_ancho * 0.48)
        story.append(img)

    doc.build(story, onFirstPage=_membrete, onLaterPages=_membrete)
    return ruta_pdf

