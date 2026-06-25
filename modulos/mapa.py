# modulos/mapa.py
import os
import tempfile
import threading
import tkinter as tk
import folium
from folium.plugins import MarkerCluster

LAT_CENTRO = -31.5375
LON_CENTRO = -68.5364
ZOOM_INICIAL = 12


def crear_tab_mapa(parent, df):
    """Crea el mapa con clustering dentro del frame 'parent'."""

    # Frame contenedor con mensaje de carga
    frame = tk.Frame(parent, bg="#1e1e2e")
    frame.pack(fill="both", expand=True)

    lbl = tk.Label(
        frame,
        text="⏳ Generando mapa...",
        bg="#1e1e2e", fg="#cdd6f4",
        font=("Helvetica", 11)
    )
    lbl.pack(expand=True)

    # Generar el mapa en un hilo para no bloquear la GUI
    def _generar():
        ruta_html = _generar_html(df)
        parent.after(0, lambda: _mostrar_webview(frame, lbl, ruta_html))

    threading.Thread(target=_generar, daemon=True).start()


def _normalizar_coordenada(valor):
    try:
        f = float(valor)
    except (ValueError, TypeError):
        return None

    if abs(f) > 180:
        s = str(int(f))
        if s.startswith("-"):
            resultado = s[:3] + "." + s[3:]
        else:
            resultado = s[:2] + "." + s[2:]
        try:
            return float(resultado)
        except ValueError:
            return None

    return f


def _generar_html(df) -> str:
    """Genera el HTML de folium con MarkerCluster y retorna la ruta."""
    mapa = folium.Map(
        location=[LAT_CENTRO, LON_CENTRO],
        zoom_start=ZOOM_INICIAL,
        tiles="OpenStreetMap"
    )

    cluster = MarkerCluster().add_to(mapa)

    df_valido = df.dropna(subset=["latitud", "longitud"])
    cargados = 0

    for _, fila in df_valido.iterrows():
        lat = _normalizar_coordenada(fila["latitud"])
        lon = _normalizar_coordenada(fila["longitud"])

        if lat is None or lon is None:
            continue
        if not (-35 < lat < -28 and -72 < lon < -65):
            continue

        jurisdiccion = str(fila.get("jurisdiccion", "Sin jurisdicción"))
        tipo         = str(fila.get("tipo_delito",  "Sin tipo"))
        modalidad    = str(fila.get("modalidad",    ""))
        fecha        = str(fila.get("fecha",        ""))[:10]

        popup_html = f"""
        <div style="font-family: Arial; font-size: 13px; min-width: 180px;">
            <b>🏛️ {jurisdiccion}</b><br>
            <b>Delito:</b> {tipo}<br>
            <b>Modalidad:</b> {modalidad}<br>
            <b>Fecha:</b> {fecha}
        </div>
        """

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{tipo} — {jurisdiccion}",
        ).add_to(cluster)

        cargados += 1

    print(f"  🗺️  {cargados} marcadores cargados en el mapa.")

    # Guardar en archivo temporal
    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=".html", mode="w", encoding="utf-8"
    )
    mapa.save(tmp.name)
    tmp.close()
    return tmp.name



def _mostrar_webview(frame, lbl, ruta_html):
    print(f"  🗺️  Abriendo mapa en ventana separada...")
    """Abre el HTML en una ventana webview flotante."""
    lbl.config(text="🗺️ Mapa listo — se abrirá en ventana separada")

    btn = tk.Button(
        frame,
        text="  Abrir Mapa Interactivo  ",
        bg="#89b4fa", fg="#1e1e2e",
        font=("Helvetica", 11, "bold"),
        relief="flat", padx=16, pady=8,
        cursor="hand2",
        command=lambda: _abrir_ventana(ruta_html)
    )
    btn.pack(expand=True)


def _abrir_ventana(ruta_html):
    """Abre el HTML del mapa en el navegador predeterminado del sistema."""
    import webbrowser
    webbrowser.open(f"file://{ruta_html}")