"""
modulos/graficos_app.py
Gráficos interactivos de la pestaña Gráficos (Flet).

Usan los mismos datos y colores que las imágenes del PDF (modulos/graficos.py).
Al pasar el mouse cada barra, celda o mes muestra su valor exacto.
"""
import flet as ft
import flet_charts as fch
import pandas as pd

from modulos.graficos import (
    ACENTO, CALOR_TEXTO_BLANCO, CONTEXTO, GRILLA, SUPERFICIE, TENUE, TINTA,
    _color_delito, color_calor, conteo_delitos, delitos_por_jurisdiccion,
    etiqueta_mes, matriz_horaria, mensual_por_anio, serie_mensual,
)
from modulos.procesador import MESES_ES

ALTO_LINEA = 240
ANCHO_ETIQUETA = 104   # columna de nombres a la izquierda de las barras
ANCHO_VALOR = 96       # columna del valor al final de cada barra


def tablero(df: pd.DataFrame) -> ft.Control:
    """Todos los gráficos de los datos, en tarjetas."""
    tarjetas = [
        (_evolucion(df), 12),
        (_delitos(df), 6),
        (_horario(df), 6),
        (_jurisdicciones(df), 12),
    ]
    if df["anio"].nunique() >= 2:
        tarjetas.append((_comparacion(df), 12))
    return ft.ResponsiveRow(
        controls=[ft.Container(content=t, col={"xs": 12, "lg": ancho}) for t, ancho in tarjetas],
        spacing=12, run_spacing=12,
    )


# ─── Piezas comunes ───────────────────────────────────────────────────────────

def _tarjeta(titulo: str, subtitulo: str, contenido: ft.Control, leyenda=None) -> ft.Control:
    controles = [
        ft.Text(titulo, size=15, weight=ft.FontWeight.W_600, color=TINTA),
        ft.Text(subtitulo, size=12, color=TENUE),
    ]
    if leyenda:
        controles.append(ft.Container(content=leyenda, padding=ft.Padding.only(top=6)))
    controles.append(ft.Container(content=contenido, padding=ft.Padding.only(top=12)))
    return ft.Container(
        bgcolor=SUPERFICIE,
        padding=20,
        border_radius=ft.BorderRadius.all(12),
        border=ft.Border.all(1, GRILLA),
        content=ft.Column(controls=controles, spacing=2),
    )


def _leyenda(items, linea=False) -> ft.Control:
    """Muestra de color + nombre. Barras: cuadrado; líneas: un trazo."""
    def muestra(color):
        if linea:
            return ft.Container(width=14, height=2, bgcolor=color, border_radius=ft.BorderRadius.all(1))
        return ft.Container(width=10, height=10, bgcolor=color, border_radius=ft.BorderRadius.all(2))
    return ft.Row(
        wrap=True, spacing=16, run_spacing=4,
        controls=[
            ft.Row([muestra(color), ft.Text(nombre, size=12, color=TENUE)], spacing=6, tight=True)
            for nombre, color in items
        ],
    )


def _resaltar(e):
    """La marca bajo el mouse se aclara un poco: se ve que responde."""
    e.control.opacity = 0.75 if e.data else 1
    e.control.update()


def _porcentaje(parte, total) -> str:
    return f"{parte / total * 100:.1f}".replace(".", ",") + "%"


def _fila_barra(etiqueta: str, valor: int, maximo: int, barra: ft.Control, texto_valor: str) -> ft.Control:
    """Nombre | barra proporcional | valor. El valor tiene ancho fijo para que las
    barras de todas las filas usen la misma escala."""
    controles = [
        ft.Text(etiqueta, width=ANCHO_ETIQUETA, size=12, color=TENUE, no_wrap=True,
                overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.RIGHT, tooltip=etiqueta),
        ft.Container(expand=valor, content=barra),
        ft.Text(texto_valor, width=ANCHO_VALOR, size=12, color=TINTA, no_wrap=True),
    ]
    if maximo > valor:
        controles.append(ft.Container(expand=maximo - valor))
    return ft.Row(controls=controles, spacing=8)


def _segmento(color: str, tooltip: str, ultimo: bool) -> ft.Control:
    """Tramo de barra. El área que responde al mouse (24 px) es más alta que el trazo."""
    radio = ft.BorderRadius.only(top_right=4, bottom_right=4) if ultimo else None
    return ft.Container(
        height=24,
        padding=ft.Padding.symmetric(vertical=5),
        tooltip=tooltip,
        on_hover=_resaltar,
        content=ft.Container(bgcolor=color, border_radius=radio),
    )


def _marcas_eje(maximo: float):
    """Valores redondos para el eje vertical (unas 4 marcas)."""
    paso = 1
    for base in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000):
        paso = base
        if maximo / base <= 4:
            break
    tope = paso * (int(maximo // paso) + 1)
    return paso, tope


def _eje_y(paso, tope) -> fch.ChartAxis:
    return fch.ChartAxis(
        label_size=44,
        labels=[
            fch.ChartAxisLabel(value=v, label=ft.Text(f"{v:,}", size=11, color=TENUE))
            for v in range(0, tope + 1, paso)
        ],
    )


def _eje_x(etiquetas: list, cada: int = 1) -> fch.ChartAxis:
    return fch.ChartAxis(
        label_size=28,
        labels=[
            fch.ChartAxisLabel(value=i, label=ft.Text(e, size=11, color=TENUE))
            for i, e in enumerate(etiquetas) if i % cada == 0
        ],
    )


def _grafico_lineas(series, etiquetas_x, maximo, cada=1) -> fch.LineChart:
    paso, tope = _marcas_eje(maximo)
    return fch.LineChart(
        data_series=series,
        min_y=0, max_y=tope,
        min_x=0, max_x=len(etiquetas_x) - 1,
        height=ALTO_LINEA,
        horizontal_grid_lines=fch.ChartGridLines(interval=paso, color=GRILLA, width=1),
        left_axis=_eje_y(paso, tope),
        bottom_axis=_eje_x(etiquetas_x, cada),
        tooltip=fch.LineChartTooltip(
            bgcolor=TINTA, border_radius=ft.BorderRadius.all(6),
            fit_inside_horizontally=True, fit_inside_vertically=True, max_width=200,
        ),
        interactive=True,
    )


def _punto_tooltip(texto: str) -> fch.LineChartDataPointTooltip:
    return fch.LineChartDataPointTooltip(
        text=texto, text_style=ft.TextStyle(color="white", size=12, weight=ft.FontWeight.W_500),
    )


# ─── 1. Evolución mensual ─────────────────────────────────────────────────────

def _evolucion(df) -> ft.Control:
    serie = serie_mensual(df)
    varios_anios = serie.index.year.nunique() > 1
    etiquetas = [etiqueta_mes(p, varios_anios) for p in serie.index]
    valores = [int(v) for v in serie.values]
    imax = valores.index(max(valores))

    # Solo el pico lleva punto; el resto se lee pasando el mouse
    punto_pico = fch.ChartCirclePoint(radius=4, color=ACENTO, stroke_color=SUPERFICIE, stroke_width=2)
    linea = fch.LineChartData(
        points=[
            fch.LineChartDataPoint(
                x=i, y=v,
                tooltip=_punto_tooltip(f"{etiqueta_mes(p, True)}\n{v:,} denuncias"),
                point=punto_pico if i == imax else False,
            )
            for i, (p, v) in enumerate(zip(serie.index, valores))
        ],
        color=ACENTO,
        stroke_width=2,
        rounded_stroke_cap=True,
        rounded_stroke_join=True,
        below_line_bgcolor=ft.Colors.with_opacity(0.08, ACENTO),
        selected_point=fch.ChartCirclePoint(radius=4, color=ACENTO, stroke_color=SUPERFICIE, stroke_width=2),
    )
    promedio = sum(valores) / len(valores)
    return _tarjeta(
        "Evolución mensual",
        f"Pico: {etiqueta_mes(serie.index[imax], True)}, {valores[imax]:,} denuncias"
        f"  ·  promedio {promedio:,.0f} por mes",
        _grafico_lineas([linea], etiquetas, max(valores), cada=max(1, len(valores) // 8)),
    )


# ─── 2. Denuncias por delito ──────────────────────────────────────────────────

def _delitos(df) -> ft.Control:
    conteo = conteo_delitos(df)
    total = int(conteo.sum())
    maximo = int(conteo.max())
    filas = [
        _fila_barra(
            str(nombre), int(v), maximo,
            _segmento(_color_delito(nombre), f"{nombre}\n{int(v):,} denuncias · {_porcentaje(v, total)}", True),
            f"{int(v):,}  ·  {_porcentaje(v, total)}",
        )
        for nombre, v in conteo.items()
    ]
    principal = conteo.idxmax()
    return _tarjeta(
        "Denuncias por delito",
        f"{principal}: {_porcentaje(maximo, total)} de {total:,} denuncias",
        ft.Column(filas, spacing=4),
    )


# ─── 3. Franja horaria × día ──────────────────────────────────────────────────

def _horario(df) -> ft.Control:
    tabla = matriz_horaria(df)
    vmin, vmax = int(tabla.values.min()), int(tabla.values.max())
    franja_pico, dia_pico = tabla.stack().idxmax()

    def celda(franja, dia, v):
        t = (v - vmin) / (vmax - vmin) if vmax > vmin else 0
        return ft.Container(
            expand=1, height=30,
            bgcolor=color_calor(t),
            border_radius=ft.BorderRadius.all(6),
            alignment=ft.Alignment.CENTER,
            tooltip=f"{dia}, {franja}\n{v:,} denuncias",
            on_hover=_resaltar,
            content=ft.Text(f"{v:,}", size=11, color="white" if t > CALOR_TEXTO_BLANCO else TINTA,
                            weight=ft.FontWeight.W_600 if v == vmax else None),
        )

    encabezado = ft.Row(
        spacing=4,
        controls=[ft.Container(width=88)] + [
            ft.Text(d[:3], expand=1, size=11, color=TENUE, text_align=ft.TextAlign.CENTER)
            for d in tabla.columns
        ],
    )
    filas = [
        ft.Row(
            spacing=4,
            controls=[ft.Text(franja, width=88, size=11, color=TENUE)] + [
                celda(franja, dia, int(tabla.loc[franja, dia])) for dia in tabla.columns
            ],
        )
        for franja in tabla.index
    ]
    escala = ft.Row(
        spacing=4, alignment=ft.MainAxisAlignment.END,
        controls=[ft.Text("Menos", size=11, color=TENUE)] + [
            ft.Container(width=16, height=10, bgcolor=color_calor(t), border_radius=ft.BorderRadius.all(2))
            for t in (0, 0.25, 0.5, 0.75, 1)
        ] + [ft.Text("Más", size=11, color=TENUE)],
    )
    return _tarjeta(
        "Por franja horaria y día",
        f"Pico: {dia_pico} de {franja_pico}, {vmax:,} denuncias",
        ft.Column([encabezado, *filas, ft.Container(height=4), escala], spacing=4),
    )


# ─── 4. Delitos por jurisdicción ──────────────────────────────────────────────

def _jurisdicciones(df) -> ft.Control:
    tabla = delitos_por_jurisdiccion(df)
    totales = tabla.sum(axis=1)
    maximo = int(totales.max())
    delitos = list(tabla.columns)

    filas = []
    for jurisdiccion, fila in tabla.iterrows():
        total = int(totales[jurisdiccion])
        presentes = [(d, int(fila[d])) for d in delitos if fila[d] > 0]
        tramos = [
            ft.Container(
                expand=n,
                content=_segmento(
                    _color_delito(d),
                    f"{jurisdiccion} · {d}\n{n:,} denuncias · {_porcentaje(n, total)} de la jurisdicción",
                    i == len(presentes) - 1,
                ),
            )
            for i, (d, n) in enumerate(presentes)
        ]
        # 2 px de fondo entre tramos: separan los delitos sin dibujar bordes
        barra = ft.Row(controls=tramos, spacing=2)
        filas.append(_fila_barra(str(jurisdiccion), total, maximo, barra, f"{total:,}"))

    return _tarjeta(
        "Delitos por jurisdicción",
        f"{tabla.index[0]} concentra {_porcentaje(totales.iloc[0], totales.sum())} de las denuncias",
        ft.Column(filas, spacing=4),
        leyenda=_leyenda([(str(d), _color_delito(d)) for d in delitos]),
    )


# ─── 5. Comparación entre años ────────────────────────────────────────────────

def _comparacion(df) -> ft.Control:
    tabla = mensual_por_anio(df)
    anios = list(tabla.columns)
    ultimo = anios[-1]

    # El último año es el que se lee (azul); los anteriores son contexto (gris)
    colores = {ultimo: ACENTO}
    for k, anio in enumerate(reversed(anios[:-1])):
        colores[anio] = CONTEXTO[min(k, len(CONTEXTO) - 1)]

    series = [
        fch.LineChartData(
            points=[
                fch.LineChartDataPoint(x=m - 1, y=int(tabla.loc[m, anio]),
                                       tooltip=_punto_tooltip(f"{anio}: {int(tabla.loc[m, anio]):,}"))
                for m in tabla.index
            ],
            color=colores[anio],
            stroke_width=2 if anio == ultimo else 1.5,
            rounded_stroke_cap=True,
            rounded_stroke_join=True,
            point=False,
            selected_point=fch.ChartCirclePoint(radius=4, color=colores[anio],
                                                stroke_color=SUPERFICIE, stroke_width=2),
        )
        # El último año se dibuja al final: queda por encima de los grises
        for anio in anios
    ]
    previo = int(tabla[anios[-2]].sum())
    actual = int(tabla[ultimo].sum())
    cambio = (actual - previo) / previo * 100 if previo else 0
    signo = "+" if cambio >= 0 else "−"
    return _tarjeta(
        "Comparación entre años",
        f"{ultimo}: {actual:,} denuncias, {signo}{abs(cambio):.0f}% frente a {anios[-2]}",
        _grafico_lineas(series, MESES_ES, int(tabla.values.max())),
        leyenda=_leyenda([(str(a), colores[a]) for a in reversed(anios)], linea=True),
    )
