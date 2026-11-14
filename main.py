"""
main.py — Interfaz gráfica de Vistana (Flet).
Es el punto de entrada de la aplicación de escritorio.
Ejecutar con:
    python main.py
"""
import asyncio
import atexit
import logging
import shutil
import webbrowser
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import flet as ft
import matplotlib

# Backend sin ventana: el reporte simple (sin navegador) dibuja sus gráficos
# con matplotlib en un hilo secundario.
matplotlib.use("Agg")

# Importar módulos propios (Lógica de negocio intacta)
from modulos.procesador import cargar_excel, col_delito, resumen_general, filtrar, tabla_pivot
from modulos.graficos_app import tablero
from modulos.exportador import exportar_excel, exportar_pdf, nombre_reporte
from modulos.informe import NavegadorNoEncontrado, _n, exportar_mapa
from modulos.mapa import generar_mapa_html, puntos_validos
from modulos.marca import ICONO_VENTANA, LEMA, LOGO, NOMBRE_VISIBLE, VERSION
from modulos.rutas import carpeta_app, carpeta_documentos, carpeta_logs, ruta_mapa


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


def _borrar(rutas):
    for ruta in rutas:
        try:
            if ruta.is_dir():
                shutil.rmtree(ruta)
            else:
                ruta.unlink(missing_ok=True)
        except OSError as ex:
            logging.getLogger(__name__).warning("No se pudo borrar %s: %s", ruta, ex)


def borrar_archivos_de_trabajo():
    """Los archivos de trabajo contienen datos de las denuncias: no deben quedar en disco.
    Incluye los gráficos PNG de versiones anteriores y las carpetas temporales del PDF
    que el navegador no dejó borrar."""
    # shortcut: con dos ventanas abiertas a la vez, una borra el mapa o el PDF en curso
    # de la otra; si eso pasa a ser un caso real, usar una carpeta de trabajo por proceso.
    carpeta = carpeta_app()
    _borrar([ruta_mapa(), carpeta / "graficos", *carpeta.glob("informe_*"), *carpeta.glob("reporte_*")])

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
        self.graficos_visibles = False
        self.filtros_activos = {}

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
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
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
            self._cargar_mapa(self.df_filtrado)

            self._log(f"✓ Archivo cargado: {ruta}")
            self._log(
                f"   {_n(len(self.df_filtrado))} registros · "
                f"{self.df_filtrado['tipo_delito'].nunique()} tipos · "
                f"{self.df_filtrado['jurisdiccion'].nunique()} jurisdicciones"
            )
            descartes = df.attrs.get("descartes", {})
            if descartes.get("fechas_invalidas"):
                self._log(f"⚠ {_n(descartes['fechas_invalidas'])} registros descartados por fecha inválida.")
            if descartes.get("duplicados"):
                self._log(f"⚠ {_n(descartes['duplicados'])} registros duplicados descartados.")
            self._informar_columnas(df.attrs.get("columnas", {}))
            if descartes.get("horas_invalidas"):
                self._log(f"⚠ {_n(descartes['horas_invalidas'])} registros sin hora interpretable (no entran en el mapa horario).")
            self._estado("Archivo cargado correctamente.")
            self.page.update()
        except Exception as ex:
            self._mostrar_alerta("Error al cargar", str(ex))
            self._estado("Error al cargar el archivo.")

    def _informar_columnas(self, columnas: dict):
        """Qué columnas de la planilla se usaron y qué datos no trae."""
        otras = [f"{campo} = «{original}»" for campo, original in columnas.items()
                 if original.strip().lower() != campo]
        if otras:
            self._log("   Columnas reconocidas: " + ", ".join(otras))
        tiene = set(columnas)
        if "delito" in tiene:
            tiene.add("tipo_delito")
        if "coordenadas" in tiene:
            tiene.add("latitud")
        faltan = [nombre for campo, nombre in [
            ("hora", "hora"), ("jurisdiccion", "comisaría"), ("tipo_delito", "delito"), ("latitud", "coordenadas"),
        ] if campo not in tiene]
        if faltan:
            self._log(f"⚠ La planilla no tiene columna de {', '.join(faltan)}: esos datos no se van a poder analizar.")

    def _abrir_filtros(self, e=None):
        if self.df_original is None:
            self._mostrar_alerta("Sin datos", "Primero cargá un archivo.")
            return

        df = self.df_original
        # El diálogo abre con los filtros que ya están aplicados
        activos = self.filtros_activos

        # Opciones
        anios = ["(todos)"] + [str(a) for a in sorted(df["anio"].unique().tolist())]
        juris = sorted(df["jurisdiccion"].unique().tolist())
        tipos = sorted(df[col_delito(df)].unique().tolist())

        dd_anio = ft.Dropdown(
            options=[ft.DropdownOption(key=a, text=a) for a in anios],
            value=str(activos.get("anio", "(todos)")),
            label="Año",
            width=300,
        )

        def campo_fecha(clave, etiqueta):
            valor = activos.get(clave)
            return ft.TextField(
                label=etiqueta, hint_text="DD/MM/AAAA", width=145,
                value=valor.strftime("%d/%m/%Y") if valor else "",
            )

        txt_desde = campo_fecha("fecha_desde", "Desde")
        txt_hasta = campo_fecha("fecha_hasta", "Hasta")

        # Checkboxes para multi-selección limpia
        chk_juris = [ft.Checkbox(label=j, value=j in activos.get("jurisdicciones", [])) for j in juris]
        chk_tipos = [ft.Checkbox(label=t, value=t in activos.get("tipos_delito", [])) for t in tipos]

        def aplicar_and_close(ev):
            kwargs = {}
            if dd_anio.value != "(todos)":
                kwargs["anio"] = int(dd_anio.value)

            for clave, campo in (("fecha_desde", txt_desde), ("fecha_hasta", txt_hasta)):
                texto = (campo.value or "").strip()
                campo.error = None   # el error de un intento anterior ya no corresponde
                if not texto:
                    continue
                try:
                    # Formato explícito: pandas leería «04/01/2025» como 1 de abril
                    kwargs[clave] = datetime.strptime(texto, "%d/%m/%Y")
                except ValueError:
                    campo.error = "Usar DD/MM/AAAA"
                    self.page.update()
                    return

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
                        ft.Row(controls=[txt_desde, txt_hasta], spacing=10),
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

        # El tablero se dibuja con Flet a partir de los datos: no escribe nada en disco
        try:
            self.col_graficos.controls = [tablero(self.df_filtrado)]
        except Exception as ex:
            self._log(f"✗ Error: {ex}")
            self._mostrar_alerta("Error", str(ex))
            return
        self.graficos_visibles = True
        self._log("✓ Gráficos generados.")
        self._estado("Gráficos generados.")
        self._mostrar_alerta("Gráficos", "Los gráficos están en la pestaña Gráficos.")

    async def _exportar_pdf(self, e=None):
        if self.df_filtrado is None:
            self._mostrar_alerta("Sin datos", "Primero cargá un archivo.")
            return

        df = self.df_filtrado
        ruta = await ft.FilePicker().save_file(
            dialog_title="Guardar informe PDF como…",
            file_name=nombre_reporte(),
            initial_directory=str(carpeta_documentos()),
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pdf"],
        )
        ruta = self._con_extension(ruta, ".pdf")
        if not ruta:
            return

        # Mientras el diálogo estuvo abierto pudieron cambiar el archivo o los filtros
        if df is not self.df_filtrado:
            self._mostrar_alerta("Los datos cambiaron", "Cambiaron los datos mientras elegías dónde guardar. Exportá de nuevo.")
            return

        self._estado("Generando PDF…")
        try:
            ruta_pdf = await asyncio.to_thread(self._generar_pdf, df, ruta)
            self._log(f"✓ PDF generado: {ruta_pdf}")
            self._estado("PDF exportado correctamente.")
            self._mostrar_alerta("PDF Exportado", f"Informe guardado en:\n{ruta_pdf}")
        except Exception as ex:
            self._log(f"✗ Error PDF: {ex}")
            self._estado("Error al exportar el PDF.")
            self._mostrar_alerta("Error PDF", str(ex))

    async def _exportar_mapa(self, e=None):
        if self.df_filtrado is None:
            self._mostrar_alerta("Sin datos", "Primero cargá un archivo.")
            return

        df = self.df_filtrado
        ruta = await ft.FilePicker().save_file(
            dialog_title="Guardar mapa PDF como…",
            file_name=nombre_reporte("mapa_delictual"),
            initial_directory=str(carpeta_documentos()),
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pdf"],
        )
        ruta = self._con_extension(ruta, ".pdf")
        if not ruta:
            return
        if df is not self.df_filtrado:
            self._mostrar_alerta("Los datos cambiaron", "Cambiaron los datos mientras elegías dónde guardar. Exportá de nuevo.")
            return

        self._estado("Generando mapa PDF…")
        try:
            ruta_pdf = await asyncio.to_thread(exportar_mapa, df, ruta)
            self._log(f"✓ Mapa PDF generado: {ruta_pdf}")
            self._estado("Mapa PDF exportado correctamente.")
            self._mostrar_alerta("Mapa exportado", f"Mapa guardado en:\n{ruta_pdf}")
        except NavegadorNoEncontrado:
            # El mapa lo imprime el navegador: no hay versión simple como con el informe
            self._estado("Error al exportar el mapa.")
            self._mostrar_alerta("Error al exportar el mapa", "Hace falta Microsoft Edge o Google Chrome para imprimir el mapa.")
        except Exception as ex:
            self._log(f"✗ Error mapa PDF: {ex}")
            self._estado("Error al exportar el mapa.")
            self._mostrar_alerta("Error al exportar el mapa", str(ex))

    def _generar_pdf(self, df, ruta: Path) -> Path:
        ruta_pdf, simple = exportar_pdf(df, ruta)
        if simple:
            self._log("⚠ No se encontró Edge ni Chrome: se generó el reporte simple.")
        return ruta_pdf

    async def _exportar_excel(self, e=None):
        if self.df_filtrado is None:
            self._mostrar_alerta("Sin datos", "Primero cargá un archivo.")
            return

        df = self.df_filtrado
        ruta = await ft.FilePicker().save_file(
            dialog_title="Guardar datos filtrados como…",
            file_name="reporte_denuncias.xlsx",
            initial_directory=str(carpeta_documentos()),
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["xlsx"],
        )
        ruta = self._con_extension(ruta, ".xlsx")
        if not ruta:
            return

        self._estado("Exportando Excel…")
        try:
            # En un hilo: con archivos grandes escribir el Excel congelaría la ventana
            await asyncio.to_thread(exportar_excel, df, ruta)
            self._log(f"✓ Excel exportado: {ruta}")
            self._estado("Excel exportado correctamente.")
            self._mostrar_alerta("Excel", f"Archivo guardado en:\n{ruta}")
        except Exception as ex:
            self._log(f"✗ Error Excel: {ex}")
            self._estado("Error al exportar el Excel.")
            self._mostrar_alerta("Error Excel", str(ex))

    def _con_extension(self, ruta, extension: str):
        """Ruta elegida en el diálogo con su extensión, o None si se canceló o no se puede usar.
        La extensión se agrega sin tocar el nombre ("informe v1.2" → "informe v1.2.pdf")."""
        if not ruta:
            return None
        ruta = Path(ruta)
        if ruta.suffix.lower() == extension:
            return ruta
        ruta = ruta.with_name(ruta.name + extension)
        if ruta.exists():
            # El diálogo confirmó sobrescribir el archivo elegido, no este otro
            self._mostrar_alerta("El archivo ya existe", f"Ya existe {ruta.name} en esa carpeta. Elegí otro nombre.")
            return None
        return ruta

    def _limpiar_datos(self, e=None):
        if self.df_original is None:
            self._mostrar_alerta("Sin datos", "No hay ningún archivo cargado.")
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
        _borrar([ruta_mapa()])

        self.df_original = None
        self.df_filtrado = None
        self.filtros_activos = {}
        self.graficos_visibles = False

        self.lbl_archivo.value = "Sin archivo cargado"
        for tarjeta in self.tarjetas.values():
            tarjeta.value = "—"
        self._vaciar_pestanas()

        self._log("✓ Datos limpiados. Podés cargar otro archivo.")
        self._estado("Listo.")

    def _acerca_de(self, e=None):
        self._mostrar_alerta(
            "Acerca de",
            f"{NOMBRE_VISIBLE} v{VERSION} — {LEMA}\n\n"
            "Sistema de análisis estadístico de denuncias.\n"
            "Desarrollado con Python · Flet · pandas · matplotlib\n\n"
            "El fondo del mapa se descarga de OpenStreetMap: sus servidores ven qué zonas "
            "se consultan, no las denuncias.\n\n"
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
        self.tarjetas["total_denuncias"].value = _n(r["total_denuncias"])
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
                        f"Mapa listo con {_n(n)} puntos georreferenciados."
                        + ("" if n == len(df) else f" {_n(len(df) - n)} no tienen coordenadas dentro de San Juan."),
                        color=C["coral"],
                        size=14,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Row(
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=12,
                        controls=[
                            ft.Button(
                                content="Abrir mapa en el navegador",
                                icon=ft.Icons.OPEN_IN_BROWSER,
                                style=ft.ButtonStyle(bgcolor=C["primary"], color="white"),
                                on_click=self._abrir_mapa,
                            ),
                            ft.OutlinedButton(
                                content="Exportar mapa en PDF",
                                icon=ft.Icons.PICTURE_AS_PDF,
                                on_click=self._exportar_mapa,
                            ),
                        ],
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
            self._cargar_mapa(df)
            self._log(f"✓ Filtros aplicados — {_n(len(df))} registros.")
            self._estado(f"Filtros activos · {_n(len(df))} registros.")
            self.page.update()
        except Exception as ex:
            self._log(f"✗ Error al filtrar: {ex}")
            self._mostrar_alerta("Error al filtrar", str(ex))

    def _invalidar_graficos(self):
        """Los gráficos en pantalla corresponden a datos anteriores: se descartan."""
        if not self.graficos_visibles:
            return
        self.graficos_visibles = False
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
    # También al abrir: si la app se cerró de golpe, lo de la vez anterior quedó en disco
    borrar_archivos_de_trabajo()
    atexit.register(borrar_archivos_de_trabajo)
    ft.run(AnalizadorApp)
