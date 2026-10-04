# modulos/mapa.py
"""
Generación del mapa interactivo (folium + MarkerCluster).
Sin dependencias de interfaz gráfica: la GUI solo llama a generar_mapa_html().
"""
import html
import logging
import math
from pathlib import Path
import folium
from modulos.graficos import _color_delito
from folium.plugins import FeatureGroupSubGroup, HeatMap, MarkerCluster

logger = logging.getLogger(__name__)

LAT_CENTRO = -31.5375
LON_CENTRO = -68.5364
ZOOM_INICIAL = 15

# Ruta de salida: <raíz del proyecto>/salidas/mapa.html
RUTA_SALIDA = Path(__file__).resolve().parent.parent / "salidas" / "mapa.html"
# Degradado del calor: mismos tonos que la matriz de riesgo
GRADIENTE_CALOR = {
    0.25: "#97B955",   # verde
    0.50: "#EDB933",   # amarillo
    0.75: "#EB8035",   # naranja
    1.00: "#CF2B3B",   # rojo
}
# Burbuja blanca con aro del color del delito que predomina en el grupo.
# El tamaño crece con la cantidad; el número va centrado con flexbox.
ICONO_CLUSTER = """
function(cluster) {
    var hijos = cluster.getAllChildMarkers();
    var n = hijos.length;
    var cuenta = {}, dominante = '#334155', max = 0;
    hijos.forEach(function(m) {
        var c = (m.options && m.options.fillColor) || '#334155';
        cuenta[c] = (cuenta[c] || 0) + 1;
        if (cuenta[c] > max) { max = cuenta[c]; dominante = c; }
    });
    var t = Math.round(Math.min(64, 28 + 6 * Math.sqrt(n)));
    return L.divIcon({
        html: '<div style="box-sizing:border-box;display:flex;align-items:center;'
            + 'justify-content:center;width:' + t + 'px;height:' + t + 'px;'
            + 'border-radius:50%;background:rgba(255,255,255,0.92);'
            + 'border:5px solid ' + dominante + ';color:#1E293B;'
            + 'font:600 13px Arial;">' + n + '</div>',
        className: 'cluster-delito',
        iconSize: [t, t]
    });
}
"""

def _normalizar_coordenada(valor):
    """Convierte la coordenada a float. Si viene como entero sin punto
    (ej. -315375123), reinserta el punto decimal."""
    if isinstance(valor, str):
        valor = valor.strip().replace(",", ".")
    try:
        f = float(valor)
    except (ValueError, TypeError):
        return None

    if not math.isfinite(f):
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


def puntos_validos(df):
    """Devuelve una lista de dicts con los puntos que pasan la normalización
    y caen dentro del rango geográfico esperado."""
    if "latitud" not in df.columns or "longitud" not in df.columns:
        return []

    col_tipo = "tipo_delito" if "tipo_delito" in df.columns else "delito"
    puntos = []

    for _, fila in df.dropna(subset=["latitud", "longitud"]).iterrows():
        lat = _normalizar_coordenada(fila["latitud"])
        lon = _normalizar_coordenada(fila["longitud"])

        if lat is None or lon is None:
            continue
        if not (-35 < lat < -28 and -72 < lon < -65):
            continue

        puntos.append({
            "lat": lat,
            "lon": lon,
            "jurisdiccion": str(fila.get("jurisdiccion", "Sin jurisdicción")),
            "tipo": str(fila.get(col_tipo, "Sin tipo")),
            "modalidad": str(fila.get("modalidad", "")),
            "fecha": str(fila.get("fecha", ""))[:10],
        })

    return puntos

def tipos_disponibles(df):
    """Tipos de delito con al menos un punto válido (para armar los checkboxes)."""
    return sorted({p["tipo"] for p in puntos_validos(df)})


def _leyenda_html(tipos):
    filas = "".join(
        f'<div style="margin:3px 0;"><span style="display:inline-block;width:11px;'
        f'height:11px;border-radius:50%;background:{_color_delito(t)};'
        f'margin-right:6px;"></span>{html.escape(t)}</div>'
        for t in tipos
    )
    return f"""
    <div style="position:fixed;bottom:24px;left:12px;z-index:9999;background:white;
                padding:8px 12px;border-radius:8px;border:1px solid #E2E8F0;
                font-family:Arial;font-size:12px;color:#1E293B;">
        {filas}
    </div>"""


def generar_mapa_html(df, tipos=None, calor=False) -> Path:
    """Genera el HTML del mapa y devuelve la ruta (Path).

    tipos: lista de tipos de delito a dibujar. None = todos, [] = ninguno.
    calor: True agrega la capa de mapa de calor con los puntos mostrados.
    """
    todos = puntos_validos(df)
    if not todos:
        raise ValueError(
            "No se encontraron coordenadas válidas dentro del rango esperado."
        )
    puntos = todos if tipos is None else [p for p in todos if p["tipo"] in tipos]

    mapa = folium.Map(
        location=[LAT_CENTRO, LON_CENTRO],
        zoom_start=ZOOM_INICIAL,
        prefer_canvas=True,
        tiles="https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, Tiles style by <a href="https://www.hotosm.org/">Humanitarian OpenStreetMap Team</a>',
    )

    # El calor se agrega primero para que los círculos queden por encima
    if calor and puntos:
        HeatMap(
            [[p["lat"], p["lon"]] for p in puntos],
            name="Mapa de calor", radius=22, blur=16, min_opacity=0.35,
            gradient=GRADIENTE_CALOR,
        ).add_to(mapa)

    # Un único cluster; cada tipo de delito es un subgrupo adentro
    cluster = MarkerCluster(
        icon_create_function=ICONO_CLUSTER,
        control=False,
        options={"maxClusterRadius": 70},
    ).add_to(mapa)

    tipos_sel = sorted({p["tipo"] for p in puntos})
    for tipo in tipos_sel:
        grupo = FeatureGroupSubGroup(cluster, name=tipo)
        grupo.add_to(mapa)
        color = _color_delito(tipo)

        for p in (q for q in puntos if q["tipo"] == tipo):
            jur = html.escape(p["jurisdiccion"])
            t = html.escape(p["tipo"])
            mod = html.escape(p["modalidad"])
            fecha = html.escape(p["fecha"])

            popup_html = f"""
            <div style="font-family: Arial; font-size: 13px; min-width: 180px;">
                <b>🏛️ {jur}</b><br>
                <b>Delito:</b> {t}<br>
                <b>Modalidad:</b> {mod}<br>
                <b>Fecha:</b> {fecha}
            </div>
            """
            folium.CircleMarker(
                location=[p["lat"], p["lon"]],
                radius=8,
                color="white", weight=1.2,
                fill=True, fill_color=color, fill_opacity=0.85,
                popup=folium.Popup(popup_html, max_width=250),
                tooltip=f"{t} — {jur}",
            ).add_to(grupo)

    if tipos_sel:
        mapa.get_root().html.add_child(folium.Element(_leyenda_html(tipos_sel)))
        folium.LayerControl(collapsed=False).add_to(mapa)

    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    mapa.save(str(RUTA_SALIDA))
    logger.info("%d puntos cargados en el mapa.", len(puntos))
    return RUTA_SALIDA