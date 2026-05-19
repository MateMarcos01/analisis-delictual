"""
gui.py — Interfaz gráfica principal del Analizador Delictual.
Requiere tkinter (incluido en Python estándar de escritorio).

Ejecutar con:
    python gui.py
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading

# Importar módulos propios
import sys
sys.path.insert(0, str(Path(__file__).parent))
from modulos.procesador import cargar_excel, resumen_general, filtrar, tabla_pivot
from modulos.graficos   import generar_todos
from modulos.exportador import generar_reporte

# ─── Paleta de colores ────────────────────────────────────────────────────────
C = {
    "bg":       "#F1EFE8",
    "sidebar":  "#2C2C2A",
    "panel":    "#FFFFFF",
    "azul":     "#534AB7",
    "azul_lt":  "#EEEDFE",
    "teal":     "#1D9E75",
    "coral":    "#D85A30",
    "texto":    "#2C2C2A",
    "muted":    "#5F5E5A",
    "borde":    "#D3D1C7",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Analizador Delictual — Sistema de Análisis de Denuncias")
        self.geometry("1100x700")
        self.configure(bg=C["bg"])
        self.resizable(True, True)

        self.df_original = None
        self.df_filtrado  = None
        self.rutas_graficos = {}

        self._construir_ui()

    # ── Construcción de la UI ─────────────────────────────────────────────────

    def _construir_ui(self):
        # Barra lateral
        sidebar = tk.Frame(self, bg=C["sidebar"], width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="Analizador\nDelictual",
                 bg=C["sidebar"], fg="white",
                 font=("Helvetica", 14, "bold"), pady=20).pack()

        ttk.Separator(sidebar, orient="horizontal").pack(fill="x", padx=16, pady=4)

        self._btn_sidebar(sidebar, "Cargar archivo",    self._cargar_archivo)
        self._btn_sidebar(sidebar, "Aplicar filtros",   self._abrir_filtros)
        self._btn_sidebar(sidebar, "Generar gráficos",  self._generar_graficos)
        self._btn_sidebar(sidebar, "Exportar PDF",      self._exportar_pdf)
        self._btn_sidebar(sidebar, "Exportar Excel",    self._exportar_excel)

        ttk.Separator(sidebar, orient="horizontal").pack(fill="x", padx=16, pady=12)
        self._btn_sidebar(sidebar, "Acerca de", self._acerca_de, secundario=True)

        # Panel principal
        self.panel = tk.Frame(self, bg=C["bg"])
        self.panel.pack(side="right", fill="both", expand=True)

        # Header
        header = tk.Frame(self.panel, bg=C["azul"], height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Sistema de Análisis de Denuncias Delictuales",
                 bg=C["azul"], fg="white",
                 font=("Helvetica", 12, "bold")).pack(side="left", padx=20, pady=14)
        self.lbl_archivo = tk.Label(header, text="Sin archivo cargado",
                                    bg=C["azul"], fg="#AFA9EC",
                                    font=("Helvetica", 9))
        self.lbl_archivo.pack(side="right", padx=20)

        # Tarjetas de métricas
        self.frame_metricas = tk.Frame(self.panel, bg=C["bg"])
        self.frame_metricas.pack(fill="x", padx=16, pady=(12, 0))
        self.tarjetas = {}
        metricas = [
            ("total_denuncias", "Total denuncias"),
            ("delito_principal", "Delito principal"),
            ("jurisdiccion_top", "Jurisdicción top"),
            ("mes_pico", "Mes pico"),
        ]
        for clave, etiqueta in metricas:
            f = tk.Frame(self.frame_metricas, bg=C["panel"],
                         relief="flat", bd=0,
                         highlightbackground=C["borde"], highlightthickness=1)
            f.pack(side="left", expand=True, fill="both", padx=4)
            tk.Label(f, text=etiqueta, bg=C["panel"], fg=C["muted"],
                     font=("Helvetica", 8)).pack(anchor="w", padx=12, pady=(10,0))
            lbl = tk.Label(f, text="—", bg=C["panel"], fg=C["azul"],
                           font=("Helvetica", 15, "bold"))
            lbl.pack(anchor="w", padx=12, pady=(2, 10))
            self.tarjetas[clave] = lbl

        # Área de contenido / log
        self.notebook = ttk.Notebook(self.panel)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=12)

        # Tab: Log
        tab_log = tk.Frame(self.notebook, bg=C["panel"])
        self.notebook.add(tab_log, text="  Actividad  ")
        self.log = tk.Text(tab_log, bg=C["panel"], fg=C["texto"],
                           font=("Courier", 9), state="disabled",
                           relief="flat", padx=12, pady=12)
        scroll = ttk.Scrollbar(tab_log, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

        # Tab: Tabla resumen
        tab_tabla = tk.Frame(self.notebook, bg=C["panel"])
        self.notebook.add(tab_tabla, text="  Tabla resumen  ")
        self.tree = ttk.Treeview(tab_tabla, show="headings")
        vsb = ttk.Scrollbar(tab_tabla, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(tab_tabla, orient="horizontal",  command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right",  fill="y")
        self.tree.pack(fill="both", expand=True)

        # Barra de estado
        self.barra_estado = tk.Label(self.panel, text="Listo.",
                                     bg=C["borde"], fg=C["muted"],
                                     font=("Helvetica", 8), anchor="w", padx=10)
        self.barra_estado.pack(fill="x", side="bottom")

    def _btn_sidebar(self, parent, texto, comando, secundario=False):
        fg   = "#B4B2A9" if secundario else "white"
        font = ("Helvetica", 9) if secundario else ("Helvetica", 10, "bold")
        btn = tk.Label(parent, text=texto, bg=C["sidebar"], fg=fg,
                       font=font, cursor="hand2", pady=8)
        btn.pack(fill="x", padx=16, pady=1)
        btn.bind("<Button-1>", lambda e: comando())
        btn.bind("<Enter>",    lambda e: btn.config(bg="#444441"))
        btn.bind("<Leave>",    lambda e: btn.config(bg=C["sidebar"]))

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _cargar_archivo(self):
        ruta = filedialog.askopenfilename(
            title="Seleccionar archivo de denuncias",
            filetypes=[("Excel", "*.xlsx *.xls"), ("CSV", "*.csv"), ("Todos", "*.*")]
        )
        if not ruta:
            return
        self._estado(f"Cargando {Path(ruta).name}…")
        try:
            self.df_original = cargar_excel(ruta)
            self.df_filtrado  = self.df_original.copy()
            self.lbl_archivo.config(text=Path(ruta).name)
            self._actualizar_metricas(self.df_filtrado)
            self._poblar_tabla(self.df_filtrado)
            self._log(f"✓  Archivo cargado: {ruta}")
            self._log(f"   {len(self.df_filtrado):,} registros · {self.df_filtrado['tipo_delito'].nunique()} tipos · {self.df_filtrado['jurisdiccion'].nunique()} jurisdicciones")
            self._estado("Archivo cargado correctamente.")
        except Exception as e:
            messagebox.showerror("Error al cargar", str(e))
            self._estado("Error al cargar el archivo.")

    def _abrir_filtros(self):
        if self.df_original is None:
            messagebox.showwarning("Sin datos", "Primero cargá un archivo.")
            return
        VentanaFiltros(self)

    def _generar_graficos(self):
        if self.df_filtrado is None:
            messagebox.showwarning("Sin datos", "Primero cargá un archivo.")
            return
        self._estado("Generando gráficos…")
        self._log("Generando gráficos…")
        def tarea():
            try:
                self.rutas_graficos = generar_todos(self.df_filtrado)
                self._log(f"✓  {len(self.rutas_graficos)} gráficos guardados en salidas/graficos/")
                self._estado(f"{len(self.rutas_graficos)} gráficos generados.")
                messagebox.showinfo("Gráficos", f"Se generaron {len(self.rutas_graficos)} gráficos en salidas/graficos/")
            except Exception as e:
                self._log(f"✗  Error: {e}")
                messagebox.showerror("Error", str(e))
        threading.Thread(target=tarea, daemon=True).start()

    def _exportar_pdf(self):
        if not self.rutas_graficos:
            messagebox.showwarning("Sin gráficos", "Generá los gráficos primero.")
            return
        self._estado("Generando PDF…")
        def tarea():
            try:
                resumen  = resumen_general(self.df_filtrado)
                pivot    = tabla_pivot(self.df_filtrado)
                ruta_pdf = generar_reporte(resumen, self.rutas_graficos, pivot)
                self._log(f"✓  PDF generado: {ruta_pdf}")
                self._estado("PDF exportado correctamente.")
                messagebox.showinfo("PDF", f"Reporte guardado en:\n{ruta_pdf}")
            except Exception as e:
                self._log(f"✗  Error PDF: {e}")
                messagebox.showerror("Error PDF", str(e))
        threading.Thread(target=tarea, daemon=True).start()

    def _exportar_excel(self):
        if self.df_filtrado is None:
            messagebox.showwarning("Sin datos", "Primero cargá un archivo.")
            return
        ruta = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            title="Guardar datos filtrados como…"
        )
        if not ruta:
            return
        try:
            pivot = tabla_pivot(self.df_filtrado)
            with __import__("openpyxl").__class__.__module__ and \
                 __import__("pandas").ExcelWriter(ruta, engine="openpyxl") as writer:
                self.df_filtrado.drop(
                    columns=[c for c in ["hora_dt","franja"] if c in self.df_filtrado.columns],
                    errors="ignore"
                ).to_excel(writer, sheet_name="Denuncias", index=False)
                pivot.to_excel(writer, sheet_name="Pivot")
            self._log(f"✓  Excel exportado: {ruta}")
            messagebox.showinfo("Excel", f"Archivo guardado en:\n{ruta}")
        except Exception as e:
            messagebox.showerror("Error Excel", str(e))

    def _acerca_de(self):
        messagebox.showinfo(
            "Acerca de",
            "Analizador Delictual v1.0\n\n"
            "Sistema de análisis estadístico de denuncias.\n"
            "Desarrollado con Python · pandas · matplotlib · seaborn\n\n"
            "Proyecto anual — Prácticas Profesionalizantes"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _actualizar_metricas(self, df):
        r = resumen_general(df)
        self.tarjetas["total_denuncias"].config(text=f"{r['total_denuncias']:,}")
        self.tarjetas["delito_principal"].config(text=r["delito_principal"])
        self.tarjetas["jurisdiccion_top"].config(text=r["jurisdiccion_top"])
        self.tarjetas["mes_pico"].config(text=r["mes_pico"])

    def _poblar_tabla(self, df):
        pivot = tabla_pivot(df).reset_index()
        self.tree.delete(*self.tree.get_children())
        cols = list(pivot.columns)
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=90, anchor="center")
        for _, row in pivot.iterrows():
            self.tree.insert("", "end", values=list(row))

    def aplicar_filtros(self, kwargs: dict):
        """Llamado desde VentanaFiltros al confirmar."""
        self.df_filtrado = filtrar(self.df_original, **kwargs)
        self._actualizar_metricas(self.df_filtrado)
        self._poblar_tabla(self.df_filtrado)
        self._log(f"✓  Filtros aplicados — {len(self.df_filtrado):,} registros.")
        self._estado(f"Filtros activos · {len(self.df_filtrado):,} registros.")

    def _log(self, msg: str):
        self.log.config(state="normal")
        from datetime import datetime
        self.log.insert("end", f"[{datetime.now():%H:%M:%S}]  {msg}\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _estado(self, msg: str):
        self.barra_estado.config(text=f"  {msg}")


# ─── Ventana de filtros ───────────────────────────────────────────────────────

class VentanaFiltros(tk.Toplevel):
    def __init__(self, app: App):
        super().__init__(app)
        self.app = app
        self.title("Filtros")
        self.geometry("380x440")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self._construir()

    def _construir(self):
        df = self.app.df_original

        tk.Label(self, text="Filtrar denuncias", bg=C["bg"],
                 fg=C["azul"], font=("Helvetica", 13, "bold")).pack(pady=(16, 8))

        frame = tk.Frame(self, bg=C["bg"], padx=20)
        frame.pack(fill="both", expand=True)

        # Año
        tk.Label(frame, text="Año:", bg=C["bg"], fg=C["texto"],
                 font=("Helvetica", 9, "bold")).grid(row=0, column=0, sticky="w", pady=4)
        anios = ["(todos)"] + sorted(df["anio"].unique().tolist())
        self.var_anio = tk.StringVar(value="(todos)")
        ttk.Combobox(frame, textvariable=self.var_anio,
                     values=anios, state="readonly", width=18).grid(row=0, column=1, sticky="w")

        # Jurisdicción
        tk.Label(frame, text="Jurisdicciones:", bg=C["bg"], fg=C["texto"],
                 font=("Helvetica", 9, "bold")).grid(row=1, column=0, sticky="nw", pady=4)
        juris = sorted(df["jurisdiccion"].unique().tolist())
        self.lb_juris = tk.Listbox(frame, selectmode="multiple", height=6,
                                   exportselection=False, font=("Helvetica", 9))
        for j in juris:
            self.lb_juris.insert("end", j)
        self.lb_juris.grid(row=1, column=1, sticky="w")

        # Tipo de delito
        tk.Label(frame, text="Tipos de delito:", bg=C["bg"], fg=C["texto"],
                 font=("Helvetica", 9, "bold")).grid(row=2, column=0, sticky="nw", pady=4)
        tipos = sorted(df["tipo_delito"].unique().tolist())
        self.lb_tipos = tk.Listbox(frame, selectmode="multiple", height=6,
                                   exportselection=False, font=("Helvetica", 9))
        for t in tipos:
            self.lb_tipos.insert("end", t)
        self.lb_tipos.grid(row=2, column=1, sticky="w")

        # Botones
        btn_frame = tk.Frame(self, bg=C["bg"])
        btn_frame.pack(pady=12)
        tk.Button(btn_frame, text="Aplicar", bg=C["azul"], fg="white",
                  font=("Helvetica", 10, "bold"), relief="flat", padx=20, pady=6,
                  command=self._aplicar).pack(side="left", padx=6)
        tk.Button(btn_frame, text="Limpiar", bg=C["borde"], fg=C["texto"],
                  font=("Helvetica", 10), relief="flat", padx=20, pady=6,
                  command=self._limpiar).pack(side="left", padx=6)

    def _aplicar(self):
        kwargs = {}
        if self.var_anio.get() != "(todos)":
            kwargs["anio"] = int(self.var_anio.get())
        sel_juris = [self.lb_juris.get(i) for i in self.lb_juris.curselection()]
        if sel_juris:
            kwargs["jurisdicciones"] = sel_juris
        sel_tipos = [self.lb_tipos.get(i) for i in self.lb_tipos.curselection()]
        if sel_tipos:
            kwargs["tipos_delito"] = sel_tipos
        self.app.aplicar_filtros(kwargs)
        self.destroy()

    def _limpiar(self):
        self.app.aplicar_filtros({})
        self.destroy()


# ─── Punto de entrada ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
