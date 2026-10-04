"""
main.py — Interfaz gráfica de Vistana (Flet).
Es el punto de entrada de la aplicación de escritorio.
Ejecutar con:
    python main.py
"""
import asyncio
import logging
import threading
import webbrowser
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import flet as ft
import matplotlib
import pandas as pd

# Backend sin ventana: los gráficos se generan en un hilo secundario
# y ya no hay Tkinter, así que "Agg" es lo correcto.
matplotlib.use("Agg")

# Importar módulos propios (Lógica de negocio intacta)
from modulos.procesador import cargar_excel, resumen_general, filtrar, tabla_pivot
from modulos.graficos import generar_todos
from modulos.exportador import generar_reporte, nombre_reporte
from modulos.mapa import generar_mapa_html, puntos_validos
from modulos.marca import ICONO_VENTANA, LEMA, LOGO, NOMBRE_VISIBLE
from modulos.rutas import carpeta_documentos, carpeta_logs, ruta_mapa


class _LogEnPantalla(logging.Handler):
    """Lleva a la pestaña Actividad los errores que los módulos registran
    (por ejemplo, un gráfico que no se pudo generar)."""

    def __init__(self, escribir):
        super().__init__(level=logging.ERROR)
        self._escribir = escribir

    def emit(self, record):
        try:
            detalle = f": {record.exc_info[1]}" if record.exc_info else ""
            self._escribir(f"✗ {record.getMessage()}{detalle}")
        except Exception:
            self.handleError(record)


def configurar_registro():
    """Guarda avisos y errores en un archivo: la app instalada no tiene consola."""
    try:
        archivo = RotatingFileHandler(
            carpeta_logs() / "analizador.log",
            maxBytes=1_000_000, backupCount=3, encoding="utf-8",
        )
    except OSError:
        # Sin registro en archivo la app tiene que abrir igual
        logging.basicConfig(level=logging.INFO, handlers=[logging.NullHandler()])
        return
    archivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[archivo])

# ─── Paleta de colores moderna ────────────────────────────────────────────────
C = {
    "bg": "#F8FAFC",          # Fondo principal gris frío muy claro
    "sidebar": "#4A4A4A",     # Lateral gris oscuro (color de marca)
    "panel": "#FFFFFF",       # Tarjetas y paneles blancos
    "primary": "#DC143C",     # Color primario (carmesí de marca): fondos con texto blanco
    "primary_light": "#FFD9CC",
    "coral": "#FF7F50",       # Acento (coral de marca): no usar de fondo con texto blanco
    "texto": "#1E293B",
    "muted": "#64748B",
    "borde": "#E2E8F0",
}


def _logo(tamano: int):
    """Logo de la app sobre fondo blanco; si falta el archivo, un ícono genérico."""
    try:
        contenido = ft.Image(src=LOGO.read_bytes(), width=tamano, height=tamano, fit=ft.BoxFit.CONTAIN)
    except OSError:
        return ft.Icon(ft.Icons.SHIELD_OUTLINED, color=C["coral"], size=tamano)
    # El logo tiene trazos grises que se pierden sobre el lateral oscuro
    return ft.Container(
        content=contenido,
        bgcolor="white",
        padding=4,
        border_radius=ft.BorderRadius.all(12),
    )


class AnalizadorApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = f"{NOMBRE_VISIBLE} — {LEMA}"
        if ICONO_VENTANA.is_file():
            self.page.window.icon = str(ICONO_VENTANA)
        self.page.window.width = 1150
        self.page.window.height = 750
        self.page.bgcolor = C["bg"]
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.LIGHT  # evita texto claro sobre fondo blanco

        # Estado de los datos
        self.df_original = None
        self.df_filtrado = None
        self.rutas_graficos = {}
        self.filtros_activos = {}
        self._generando = False

        self._construir_ui()
        logging.getLogger("modulos").addHandler(_LogEnPantalla(self._log))

    # ─── Construcción de la UI ────────────────────────────────────────────────
    def _construir_ui(self):
        # 1. BARRA LATERAL (SIDEBAR)
        sidebar = ft.Container(
            width=230,
            bgcolor=C["sidebar"],
            padding=ft.Padding.all(16),
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                _logo(72),
                                ft.Text(NOMBRE_VISIBLE, color="white", size=20, weight=ft.FontWeight.BOLD),
                            ],
                            spacing=6,
                        ),
                        margin=ft.Margin.only(bottom=10, top=10),
                    ),
                    ft.Divider(color="#636363"),
                    self._btn_sidebar(ft.Icons.FOLDER_OPEN_ROUNDED, "Cargar archivo", self._cargar_archivo),
                    self._btn_sidebar(ft.Icons.FILTER_ALT_ROUNDED, "Aplicar filtros", self._abrir_filtros),
                    self._btn_sidebar(ft.Icons.BAR_CHART_ROUNDED, "Generar gráficos", self._generar_graficos),
                    self._btn_sidebar(ft.Icons.PICTURE_AS_PDF_ROUNDED, "Exportar PDF", self._exportar_pdf),
                    self._btn_sidebar(ft.Icons.TABLE_VIEW_ROUNDED, "Exportar Excel", self._exportar_excel),
                    self._btn_sidebar(ft.Icons.DELETE_SWEEP_ROUNDED, "Limpiar datos", self._limpiar_datos),
                    ft.Divider(color="#636363"),
                    self._btn_sidebar(ft.Icons.INFO_OUTLINED, "Acerca de", self._acerca_de, secundario=True),
                ],
                spacing=8,
            ),
        )

        # 2. HEADER
        self.lbl_archivo = ft.Text("Sin archivo cargado", color=C["primary_light"], size=12)
        header = ft.Container(
            height=55,
            bgcolor=C["primary"],
            padding=ft.Padding.symmetric(horizontal=20),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Text(LEMA, color="white", size=15, weight=ft.FontWeight.BOLD),
                    self.lbl_archivo,
                ],
            ),
        )

        # 3. TARJETAS DE MÉTRICAS (KPIs)
        self.tarjetas = {}
        metricas_def = [
            ("total_denuncias", "Total denuncias"),
            ("delito_principal", "Delito principal"),
            ("jurisdiccion_top", "Jurisdicción top"),
            ("mes_pico", "Mes pico"),
        ]

        tarjetas_widgets = []
        for clave, etiqueta in metricas_def:
            val_text = ft.Text("—", size=18, weight=ft.FontWeight.BOLD, color=C["primary"])
            self.tarjetas[clave] = val_text

            card = ft.Container(
                expand=True,
                bgcolor=C["panel"],
                padding=12,
                border_radius=ft.BorderRadius.all(8),
                border=ft.Border.all(1, C["borde"]),
                content=ft.Column(
                    controls=[
                        ft.Text(etiqueta.upper(), size=10, weight=ft.FontWeight.W_600, color=C["muted"]),
                        val_text,
                    ],
                    spacing=4,
                ),
            )
            tarjetas_widgets.append(card)

        row_metricas = ft.Row(controls=tarjetas_widgets, spacing=12)

        # 4. PESTAÑAS (TABS DE CONTENIDO)
        # Tab 1: Log de Actividad
        self.txt_log = ft.TextField(
            multiline=True,
            read_only=True,
            border=ft.NoInputBorder(),
            text_size=12,
            bgcolor=C["panel"],
            color=C["texto"],
            expand=True,
        )

        # Tab 2: Tabla Resumen
        self.container_tabla = ft.Column(scroll=ft.ScrollMode.ALWAYS, expand=True)

        # Tab 3: Gráficos
        self.col_graficos = ft.Column(
            scroll=ft.ScrollMode.ALWAYS,
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        # Tab 4: Mapa
        self.container_mapa = ft.Container(alignment=ft.Alignment.CENTER, expand=True)
        self._vaciar_pestanas()

        # En Flet nuevo: Tabs = TabBar (las pestañas) + TabBarView (los contenidos)
        tabs = ft.Tabs(
            length=4,
            selected_index=0,
            animation_duration=200,
            expand=True,
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label="Actividad", icon=ft.Icons.LIST_ALT),
                            ft.Tab(label="Tabla resumen", icon=ft.Icons.TABLE_CHART),
                            ft.Tab(label="Gráficos", icon=ft.Icons.INSERT_CHART),
                            ft.Tab(label="Mapa", icon=ft.Icons.MAP),
                        ],
                    ),
                    ft.TabBarView(
                        expand=True,
                        controls=[
                            ft.Container(content=self.txt_log, padding=10),
                            ft.Container(content=self.container_tabla, padding=10),
                            ft.Container(content=self.col_graficos, padding=10),
                            self.container_mapa,
                        ],
                    ),
                ],
            ),
        )

        # 5. BARRA DE ESTADO
        self.lbl_estado = ft.Text("Listo.", color=C["muted"], size=11)
        status_bar = ft.Container(
            height=28,
            bgcolor=C["borde"],
            padding=ft.Padding.symmetric(horizontal=12),
            alignment=ft.Alignment.CENTER_LEFT,
            content=self.lbl_estado,
        )

        # ENSAMBLE DEL PANEL PRINCIPAL
        panel_principal = ft.Column(
            expand=True,
            controls=[
                header,
                ft.Container(
                    padding=ft.Padding.only(left=16, right=16, top=12, bottom=0),
                    content=row_metricas,
                ),
                ft.Container(
                    expand=True,
                    padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                    content=tabs,
                ),
                status_bar,
            ],
            spacing=0,
        )

        # VISTA GLOBAL (Sidebar + Panel)
        self.page.add(
            ft.Row(
                controls=[sidebar, panel_principal],
                expand=True,
                spacing=0,
            )
        )

    def _btn_sidebar(self, icon, texto, comando, secundario=False):
        color = "#B4B2A9" if secundario else "white"
        return ft.TextButton(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, color=color, size=18),
                    ft.Text(texto, color=color, size=13, weight=ft.FontWeight.W_500),
                ],
                spacing=10,
            ),
            # "comando" puede ser función normal o async: Flet maneja ambas
            on_click=comando,
            style=ft.ButtonStyle(
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
        )

    # ─── ACCIONES Y LÓGICA DE EVENTOS ─────────────────────────────────────────

    async def _cargar_archivo(self, e=None):
        # En Flet nuevo el FilePicker es un "servicio": se crea y se espera el resultado
        archivos = await ft.FilePicker().pick_files(
            dialog_title="Seleccionar archivo de denuncias",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx", "xls", "csv"],
        )
        if not archivos:
            return

        ruta = archivos[0].path
        self._estado(f"Cargando {Path(ruta).name}…")

        try:
            # Se carga en un hilo para no congelar la ventana
            df = await asyncio.to_thread(cargar_excel, ruta)
            if df.empty:
                self._mostrar_alerta(
                    "Archivo sin registros",
                    "El archivo no tiene ningún registro con fecha válida.",
                )
                self._estado("El archivo no tiene registros válidos.")
                return

            self.df_original = df
            self.df_filtrado = df.copy()
            self.filtros_activos = {}
            # Antes de refrescar la pantalla: si el refresco falla, igual no deben
            # quedar gráficos del archivo anterior.
            self._invalidar_graficos()
            self.lbl_archivo.value = Path(ruta).name

            self._actualizar_metricas(self.df_filtrado)
            self._poblar_tabla(self.df_filtrado)

            self._log(f"✓ Archivo cargado: {ruta}")
            self._log(
                f"   {len(self.df_filtrado):,} registros · "
                f"{self.df_filtrado['tipo_delito'].nunique()} tipos · "
                f"{self.df_filtrado['jurisdiccion'].nunique()} jurisdicciones"
            )
            descartes = df.attrs.get("descartes", {})
            if descartes.get("fechas_invalidas"):
                self._log(f"⚠ {descartes['fechas_invalidas']:,} registros descartados por fecha inválida.")
            if descartes.get("duplicados"):
                self._log(f"⚠ {descartes['duplicados']:,} registros duplicados descartados.")
            if descartes.get("horas_invalidas"):
                self._log(f"⚠ {descartes['horas_invalidas']:,} registros sin hora interpretable (no entran en el mapa horario).")
            self._estado("Archivo cargado correctamente.")
            self.page.update()
        except Exception as ex:
            self._mostrar_alerta("Error al cargar", str(ex))
            self._estado("Error al cargar el archivo.")

    def _abrir_filtros(self, e=None):
        if self.df_original is None:
            self._mostrar_alerta("Sin datos", "Primero cargá un archivo.")
            return

        df = self.df_original
        col_delito = "delito" if "delito" in df.columns else "tipo_delito"

        # Opciones
        anios = ["(todos)"] + [str(a) for a in sorted(df["anio"].unique().tolist())]
        juris = sorted(df["jurisdiccion"].unique().tolist())
        tipos = sorted(df[col_delito].unique().tolist())

        dd_anio = ft.Dropdown(
            options=[ft.DropdownOption(key=a, text=a) for a in anios],
            value="(todos)",
            label="Año",
            width=300,
        )

        # Checkboxes para multi-selección limpia
        chk_juris = [ft.Checkbox(label=j, value=False) for j in juris]
        chk_tipos = [ft.Checkbox(label=t, value=False) for t in tipos]

        def aplicar_and_close(ev):
            kwargs = {}
            if dd_anio.value != "(todos)":
                kwargs["anio"] = int(dd_anio.value)

            sel_j = [c.label for c in chk_juris if c.value]
            if sel_j:
                kwargs["jurisdicciones"] = sel_j

            sel_t = [c.label for c in chk_tipos if c.value]
            if sel_t:
                kwargs["tipos_delito"] = sel_t

            self.page.pop_dialog()
            self.aplicar_filtros(kwargs)

        def limpiar_and_close(ev):
            self.page.pop_dialog()
            self.aplicar_filtros({})

        dlg_filtros = ft.AlertDialog(
            title=ft.Text("Filtrar denuncias", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=350,
                height=400,
                content=ft.Column(
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        dd_anio,
                        ft.Text("Jurisdicciones:", weight=ft.FontWeight.BOLD, size=12),
                        ft.Column(controls=chk_juris, spacing=0),
                        ft.Text("Delito:", weight=ft.FontWeight.BOLD, size=12),
                        ft.Column(controls=chk_tipos, spacing=0),
                    ],
                    spacing=10,
                ),
            ),
            actions=[
                ft.Button(
                    content="Aplicar",
                    style=ft.ButtonStyle(bgcolor=C["primary"], color="white"),
                    on_click=aplicar_and_close,
                ),
                ft.OutlinedButton(content="Limpiar", on_click=limpiar_and_close),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        self.page.show_dialog(dlg_filtros)

    def _generar_graficos(self, e=None):
        if self.df_filtrado is None:
            self._mostrar_alerta("Sin datos", "Primero cargá un archivo.")
            return

        if self._generando:
            self._mostrar_alerta("Gráficos", "Ya se están generando los gráficos. Esperá a que terminen.")
            return

        self._generando = True
        self._estado("Generando gráficos…")
        self._log("Generando gráficos…")
        df = self.df_filtrado

        def tarea():
            try:
                rutas = generar_todos(df)
                # Si mientras tanto cambió el filtro o el archivo, estos gráficos ya no sirven
                if df is not self.df_filtrado:
                    self._log("Los datos cambiaron mientras se generaban los gráficos; se descartaron.")
                    self._estado("Los datos cambiaron. Generá los gráficos de nuevo.")
                    return
                self.rutas_graficos = rutas

                self._log(f"✓ {len(self.rutas_graficos)} gráficos generados.")
                self._estado(f"{len(self.rutas_graficos)} gráficos generados.")
                self._mostrar_graficos_en_ui()
                self._mostrar_alerta("Gráficos", f"Se generaron {len(self.rutas_graficos)} gráficos. Están en la pestaña Gráficos.")
            except Exception as ex:
                self._log(f"✗ Error: {ex}")
                self._mostrar_alerta("Error", str(ex))
            finally:
                self._generando = False

        threading.Thread(target=tarea, daemon=True).start()

    async def _exportar_pdf(self, e=None):
        if self._generando:
            self._mostrar_alerta("Gráficos en curso", "Esperá a que terminen de generarse los gráficos.")
            return
        if not self.rutas_graficos:
            self._mostrar_alerta("Sin gráficos", "Generá los gráficos primero.")
            return

        # Se toman juntos para que el resumen y los gráficos sean de los mismos datos
        df = self.df_filtrado
        rutas = dict(self.rutas_graficos)

        ruta = await ft.FilePicker().save_file(
            dialog_title="Guardar reporte PDF como…",
            file_name=nombre_reporte(),
            initial_directory=str(carpeta_documentos()),
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pdf"],
        )
        if not ruta:
            return
        elegida = Path(ruta)
        ruta = elegida
        if ruta.suffix.lower() != ".pdf":
            # Se agrega la extensión sin tocar el nombre ("informe v1.2" → "informe v1.2.pdf")
            ruta = ruta.with_name(ruta.name + ".pdf")
            if ruta.exists():
                # El diálogo confirmó sobrescribir "elegida", no este otro archivo
                self._mostrar_alerta("El archivo ya existe", f"Ya existe {ruta.name} en esa carpeta. Elegí otro nombre.")
                return

        # Mientras el diálogo estuvo abierto pudieron cambiar los datos o los gráficos
        if self._generando or df is not self.df_filtrado or rutas != self.rutas_graficos:
            self._mostrar_alerta("Los datos cambiaron", "Generá los gráficos de nuevo antes de exportar.")
            return

        self._estado("Generando PDF…")
        try:
            ruta_pdf = await asyncio.to_thread(
                lambda: generar_reporte(
                    resumen_general(df), rutas, tabla_pivot(df),
                    carpeta=ruta.parent, nombre=ruta.name,
                )
            )
            self._log(f"✓ PDF generado: {ruta_pdf}")
            self._estado("PDF exportado correctamente.")
            self._mostrar_alerta("PDF Exportado", f"Reporte guardado en:\n{ruta_pdf}")
        except Exception as ex:
            self._log(f"✗ Error PDF: {ex}")
            self._estado("Error al exportar el PDF.")
            self._mostrar_alerta("Error PDF", str(ex))

    async def _exportar_excel(self, e=None):
        if self.df_filtrado is None:
            self._mostrar_alerta("Sin datos", "Primero cargá un archivo.")
            return

        ruta = await ft.FilePicker().save_file(
            dialog_title="Guardar datos filtrados como…",
            file_name="reporte_denuncias.xlsx",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx"],
        )
        if not ruta:
            return

        try:
            pivot = tabla_pivot(self.df_filtrado)
            with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
                self.df_filtrado.drop(
                    columns=[c for c in ["hora_dt", "franja"] if c in self.df_filtrado.columns],
                    errors="ignore",
                ).to_excel(writer, sheet_name="Denuncias", index=False)
                pivot.to_excel(writer, sheet_name="Pivot")

            self._log(f"✓ Excel exportado: {ruta}")
            self._mostrar_alerta("Excel", f"Archivo guardado en:\n{ruta}")
        except Exception as ex:
            self._mostrar_alerta("Error Excel", str(ex))

    def _limpiar_datos(self, e=None):
        if self.df_original is None:
            self._mostrar_alerta("Sin datos", "No hay ningún archivo cargado.")
            return
        if self._generando:
            self._mostrar_alerta("Gráficos en curso", "Esperá a que terminen de generarse los gráficos.")
            return

        def confirmar(ev):
            self.page.pop_dialog()
            self.limpiar_datos()

        dlg = ft.AlertDialog(
            title=ft.Text("Limpiar datos", weight=ft.FontWeight.BOLD),
            content=ft.Text(
                f"Se va a quitar {self.lbl_archivo.value} junto con sus filtros, gráficos y mapa.\n"
                "Los PDF y Excel que ya exportaste no se tocan."
            ),
            actions=[
                ft.Button(
                    content="Limpiar",
                    style=ft.ButtonStyle(bgcolor=C["primary"], color="white"),
                    on_click=confirmar,
                ),
                ft.OutlinedButton(content="Cancelar", on_click=lambda ev: self.page.pop_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def limpiar_datos(self):
        """Deja la aplicación como recién abierta, lista para cargar otro archivo."""
        # Los archivos de trabajo contienen datos de las denuncias: no deben quedar en disco
        for ruta in [*self.rutas_graficos.values(), ruta_mapa()]:
            try:
                Path(ruta).unlink(missing_ok=True)
            except OSError as ex:
                logging.getLogger(__name__).warning("No se pudo borrar %s: %s", ruta, ex)

        self.df_original = None
        self.df_filtrado = None
        self.filtros_activos = {}
        self.rutas_graficos = {}

        self.lbl_archivo.value = "Sin archivo cargado"
        for tarjeta in self.tarjetas.values():
            tarjeta.value = "—"
        self._vaciar_pestanas()

        self._log("✓ Datos limpiados. Podés cargar otro archivo.")
        self._estado("Listo.")

    def _acerca_de(self, e=None):
        self._mostrar_alerta(
            "Acerca de",
            f"{NOMBRE_VISIBLE} v1.1 — {LEMA}\n\n"
            "Sistema de análisis estadístico de denuncias.\n"
            "Desarrollado con Python · Flet · pandas · matplotlib · seaborn\n\n"
            "Proyecto anual — Prácticas Profesionalizantes",
        )

    # ─── HELPERS DE UI Y ACTUALIZACIÓN ────────────────────────────────────────

    def _vaciar_pestanas(self):
        """Tabla, gráficos y mapa como cuando todavía no hay archivo cargado."""
        self.container_tabla.controls = []
        self.col_graficos.controls = [
            ft.Text("Generá los gráficos para visualizarlos aquí.", color=C["muted"], size=13)
        ]
        self.container_mapa.content = ft.Text(
            "Carga un archivo con coordenadas para ver el mapa.", color=C["muted"], size=13
        )

    def _actualizar_metricas(self, df):
        r = resumen_general(df)
        self.tarjetas["total_denuncias"].value = f"{r['total_denuncias']:,}"
        self.tarjetas["delito_principal"].value = str(r["delito_principal"])
        self.tarjetas["jurisdiccion_top"].value = str(r["jurisdiccion_top"])
        self.tarjetas["mes_pico"].value = str(r["mes_pico"])

    def _poblar_tabla(self, df):
        pivot = tabla_pivot(df).reset_index()
        cols = [ft.DataColumn(ft.Text(str(c), weight=ft.FontWeight.BOLD, size=11, color=C["texto"])) for c in pivot.columns]

        rows = []
        for _, row in pivot.iterrows():
            cells = [ft.DataCell(ft.Text(str(val), size=11, color=C["texto"])) for val in row]
            rows.append(ft.DataRow(cells=cells))

        dt = ft.DataTable(
            columns=cols,
            rows=rows,
            border_radius=ft.BorderRadius.all(6),
            border=ft.Border.all(1, C["borde"]),
        )

        # Envolver en scroll horizontal y vertical
        self.container_tabla.controls = [
            ft.Row(controls=[dt], scroll=ft.ScrollMode.ALWAYS)
        ]

        self._cargar_mapa(df)

    def _cargar_mapa(self, df):
        if "latitud" in df.columns and "longitud" in df.columns:
            n = len(puntos_validos(df))
            self.container_mapa.content = ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
                controls=[
                    ft.Icon(ft.Icons.MAP, size=48, color=C["coral"]),
                    ft.Text(
                        f"Mapa listo con {n:,} puntos georreferenciados.",
                        color=C["coral"],
                        size=14,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Button(
                        content="Abrir mapa en el navegador",
                        icon=ft.Icons.OPEN_IN_BROWSER,
                        style=ft.ButtonStyle(bgcolor=C["primary"], color="white"),
                        on_click=self._abrir_mapa,
                    ),
                ],
            )
        else:
            self.container_mapa.content = ft.Text(
                "El archivo no contiene columnas 'latitud' y 'longitud'.",
                color=C["muted"],
                size=13,
            )

    async def _abrir_mapa(self, e=None):
        if self.df_filtrado is None:
            self._mostrar_alerta("Sin datos", "Primero cargá un archivo.")
            return
        try:
            self._estado("Generando mapa…")
            ruta = await asyncio.to_thread(generar_mapa_html, self.df_filtrado)
            webbrowser.open(ruta.as_uri())
            self._log(f"✓ Mapa generado y abierto: {ruta}")
            self._estado("Mapa abierto en el navegador.")
        except Exception as ex:
            self._log(f"✗ Error mapa: {ex}")
            self._mostrar_alerta("Error al generar el mapa", str(ex))

    def _mostrar_graficos_en_ui(self):
        ORDEN = [
                "donut", "serie_temporal", "barras_tipo",
                "barras_jurisdiccion", "heatmap_horario",
                "ranking_jurisdiccion", "comparacion_anual",
        ]

        elementos = []
        for nombre in ORDEN:
            if nombre in self.rutas_graficos:
                # Se lee el archivo y se pasan los bytes: así no depende de rutas/assets de Flet
                with open(self.rutas_graficos[nombre], "rb") as f:
                    datos_img = f.read()
                img = ft.Image(
                    src=datos_img,
                    fit=ft.BoxFit.CONTAIN,
                    border_radius=ft.BorderRadius.all(8),
                )
                card_img = ft.Container(
                    content=img,
                    bgcolor=C["panel"],
                    padding=16,
                    border_radius=ft.BorderRadius.all(8),
                    border=ft.Border.all(1, C["borde"]),
                    margin=ft.Margin.only(bottom=12),
                )
                elementos.append(card_img)

        self.col_graficos.controls = elementos
        self.page.update()

    def aplicar_filtros(self, kwargs: dict):
        if kwargs == self.filtros_activos:
            return  # mismo filtro que ya está aplicado: no hay nada que cambiar
        try:
            df = filtrar(self.df_original, **kwargs)
            if df.empty:
                # No se toca el estado: la pantalla sigue mostrando el filtro anterior
                self._mostrar_alerta(
                    "Sin resultados",
                    "Ningún registro coincide con esos filtros. Se mantienen los datos anteriores.",
                )
                return
            self.df_filtrado = df
            self.filtros_activos = dict(kwargs)
            self._invalidar_graficos()
            self._actualizar_metricas(df)
            self._poblar_tabla(df)
            self._log(f"✓ Filtros aplicados — {len(df):,} registros.")
            self._estado(f"Filtros activos · {len(df):,} registros.")
            self.page.update()
        except Exception as ex:
            self._log(f"✗ Error al filtrar: {ex}")
            self._mostrar_alerta("Error al filtrar", str(ex))

    def _invalidar_graficos(self):
        """Los gráficos generados corresponden a datos anteriores: se descartan
        para que el PDF no mezcle un resumen nuevo con gráficos viejos."""
        if not self.rutas_graficos:
            return
        self.rutas_graficos = {}
        self.col_graficos.controls = [
            ft.Text("Los datos cambiaron. Generá los gráficos de nuevo.", color=C["muted"], size=13)
        ]
        self._log("Los gráficos anteriores se descartaron porque cambiaron los datos.")

    def _log(self, msg: str):
        hora = datetime.now().strftime("%H:%M:%S")
        self.txt_log.value = (self.txt_log.value or "") + f"[{hora}]  {msg}\n"
        self.page.update()

    def _estado(self, msg: str):
        self.lbl_estado.value = f"  {msg}"
        self.page.update()

    def _mostrar_alerta(self, titulo: str, mensaje: str):
        dlg = ft.AlertDialog(
            title=ft.Text(titulo, weight=ft.FontWeight.BOLD),
            content=ft.Text(mensaje),
            actions=[ft.TextButton(content="Entendido", on_click=lambda ev: self.page.pop_dialog())],
        )
        self.page.show_dialog(dlg)


# ─── PUNTO DE ENTRADA DE LA APLICACIÓN ────────────────────────────────────────
if __name__ == "__main__":
    configurar_registro()
    ft.run(AnalizadorApp)
