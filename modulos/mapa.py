# modulos/mapa.py
"""
Generación del mapa interactivo (folium + MarkerCluster).
Sin dependencias de interfaz gráfica: la GUI solo llama a generar_mapa_html().
"""
import html
import json
import logging
import math
from pathlib import Path
import folium
from branca.element import MacroElement
from jinja2 import Template
from modulos.graficos import _col_delito, _color_delito
from modulos.rutas import ruta_mapa
from folium.plugins import FeatureGroupSubGroup, HeatMap, MarkerCluster

logger = logging.getLogger(__name__)

# Centro de respaldo; con puntos, el mapa se encuadra sobre ellos (ver _limites)
LAT_CENTRO = -31.5375
LON_CENTRO = -68.5364
ZOOM_INICIAL = 15   # zoom máximo al encuadrar

# Nombres de las casillas de las dos vistas del panel
CAPA_PUNTOS = "Mapa de puntos"
CAPA_CALOR = "Mapa de calor"

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

    # Las capas del mapa van por DELITO (la categoría normalizada). La carátula
    # (tipo_delito) es el detalle de cada causa y solo se muestra en el globo.
    col_tipo = _col_delito(df)
    con_caratula = col_tipo != "tipo_delito" and "tipo_delito" in df.columns
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
            "caratula": str(fila["tipo_delito"]) if con_caratula else "",
            "modalidad": str(fila.get("modalidad", "")),
            "fecha": str(fila.get("fecha", ""))[:10],
        })

    return puntos

def _orden_delito(nombre: str):
    """Mismo orden que los gráficos: Robo, Hurto, Ttva Robo, Ttva Hurto y el resto."""
    n = nombre.lower()
    tentativa = "tentativa" in n or "ttva" in n
    if "robo" in n:
        return (2 if tentativa else 0, n)
    if "hurto" in n:
        return (3 if tentativa else 1, n)
    return (4, n)


def tipos_disponibles(df):
    """Delitos con al menos un punto válido (para armar los checkboxes)."""
    return sorted({p["tipo"] for p in puntos_validos(df)}, key=_orden_delito)


ESTILO_PANEL = """
<style>
/* El calor va debajo de los puntos (Leaflet pone sus lienzos en z-index 100)
   y no les tapa los clics */
.leaflet-pane canvas.leaflet-heatmap-layer { z-index: 50; pointer-events: none; }
.panel-capas { background: white; padding: 10px 12px; border-radius: 8px;
               border: 1px solid #E2E8F0; font: 13px Arial; color: #1E293B;
               min-width: 170px; box-shadow: 0 1px 4px rgba(0,0,0,0.2); }
.panel-capas label { display: flex; align-items: center; gap: 6px;
                     margin: 4px 0; cursor: pointer; }
.panel-capas .vista { font-weight: 600; }
.panel-capas .titulo { display: flex; justify-content: space-between; cursor: pointer;
                       font-weight: 600; margin-top: 8px; padding-top: 8px;
                       border-top: 1px solid #E2E8F0; user-select: none; }
.panel-capas .lista { max-height: 220px; overflow-y: auto; }
.panel-capas .punto { width: 11px; height: 11px; border-radius: 50%; flex: none; }
.panel-capas .atajos { font-size: 11px; color: #64748B; margin: 4px 0; }
.panel-capas .atajos a { color: #DC143C; cursor: pointer; }
</style>
"""

# Panel propio en lugar del control de capas de Leaflet: las dos vistas (puntos
# y calor) comparten el filtro de delitos, y el calor se recalcula al cambiarlo.
JS_PANEL = """
(function() {
    var mapa = __MAPA__;
    var calor = __CALOR__;
    var delitos = __DELITOS__;

    function casilla(padre, texto, clase, marcada, color) {
        var etiqueta = L.DomUtil.create('label', clase, padre);
        var entrada = L.DomUtil.create('input', '', etiqueta);
        entrada.type = 'checkbox';
        entrada.checked = marcada;
        if (color) {
            L.DomUtil.create('span', 'punto', etiqueta).style.background = color;
        }
        L.DomUtil.create('span', '', etiqueta).textContent = texto;
        entrada.addEventListener('change', actualizar);
        return entrada;
    }

    function actualizar() {
        var verPuntos = chkPuntos.checked, verCalor = chkCalor.checked;
        var coordenadas = [];
        delitos.forEach(function(d) {
            var activo = d.casilla.checked;
            if (verPuntos && activo) {
                if (!mapa.hasLayer(d.capa)) { mapa.addLayer(d.capa); }
            } else if (mapa.hasLayer(d.capa)) {
                mapa.removeLayer(d.capa);
            }
            if (verCalor && activo) {
                d.capa.getLayers().forEach(function(m) { coordenadas.push(m.getLatLng()); });
            }
        });
        // El calor se rehace con los delitos tildados
        if (mapa.hasLayer(calor)) { mapa.removeLayer(calor); }
        if (verCalor && coordenadas.length) {
            calor = L.heatLayer(coordenadas, calor.options);
            mapa.addLayer(calor);
        }
    }

    function marcarTodos(valor) {
        delitos.forEach(function(d) { d.casilla.checked = valor; });
        actualizar();
    }

    var chkPuntos, chkCalor;
    var panel = L.control({position: 'topright'});
    panel.onAdd = function() {
        var div = L.DomUtil.create('div', 'panel-capas');
        chkPuntos = casilla(div, '__CAPA_PUNTOS__', 'vista', false);
        chkCalor = casilla(div, '__CAPA_CALOR__', 'vista', false);

        var titulo = L.DomUtil.create('div', 'titulo', div);
        L.DomUtil.create('span', '', titulo).textContent = 'Delitos';
        var flecha = L.DomUtil.create('span', '', titulo);
        flecha.textContent = '\\u25BE';
        var cuerpo = L.DomUtil.create('div', '', div);
        titulo.addEventListener('click', function() {
            var oculto = cuerpo.style.display === 'none';
            cuerpo.style.display = oculto ? '' : 'none';
            flecha.textContent = oculto ? '\\u25BE' : '\\u25B8';
        });

        var atajos = L.DomUtil.create('div', 'atajos', cuerpo);
        var todos = L.DomUtil.create('a', '', atajos);
        todos.textContent = 'Todos';
        todos.addEventListener('click', function() { marcarTodos(true); });
        atajos.appendChild(document.createTextNode(' \\u00B7 '));
        var ninguno = L.DomUtil.create('a', '', atajos);
        ninguno.textContent = 'Ninguno';
        ninguno.addEventListener('click', function() { marcarTodos(false); });

        var lista = L.DomUtil.create('div', 'lista', cuerpo);
        delitos.forEach(function(d) {
            d.casilla = casilla(lista, d.nombre, '', true, d.color);
        });

        L.DomEvent.disableClickPropagation(div);
        L.DomEvent.disableScrollPropagation(div);
        return div;
    };
    panel.addTo(mapa);
})();
"""


class _Panel(MacroElement):
    """Inserta el JavaScript del panel al final del script del mapa."""
    _template = Template("{% macro script(this, kwargs) %}{{ this.js }}{% endmacro %}")

    def __init__(self, js: str):
        super().__init__()
        self._name = "PanelCapas"
        self.js = js


def _js_panel(mapa, calor, grupos) -> str:
    """grupos: lista de (nombre del delito, color, subgrupo de folium)."""
    delitos = ", ".join(
        "{nombre: %s, color: %s, capa: %s}" % (
            json.dumps(nombre).replace("</", "<\\/"), json.dumps(color), grupo.get_name(),
        )
        for nombre, color, grupo in grupos
    )
    return (
        JS_PANEL
        .replace("__MAPA__", mapa.get_name())
        .replace("__CALOR__", calor.get_name())
        .replace("__DELITOS__", f"[{delitos}]")
        .replace("__CAPA_PUNTOS__", CAPA_PUNTOS)
        .replace("__CAPA_CALOR__", CAPA_CALOR)
    )


def _limites(puntos):
    """Rectángulo [[sur, oeste], [norte, este]] donde se concentran los puntos.
    Deja afuera el 5 % más alejado de cada lado: unos pocos puntos aislados
    no deben alejar el zoom de la zona donde está la mayoría."""
    if not puntos:
        return None

    def rango(valores):
        valores = sorted(valores)
        corte = int(len(valores) * 0.05)
        return valores[corte], valores[len(valores) - 1 - corte]

    sur, norte = rango(p["lat"] for p in puntos)
    oeste, este = rango(p["lon"] for p in puntos)
    return [[sur, oeste], [norte, este]]


def generar_mapa_html(df, tipos=None, ruta=None) -> Path:
    """Genera el HTML del mapa y devuelve la ruta (Path).
    Sin 'ruta', se guarda en la carpeta de trabajo de la aplicación.

    tipos: lista de tipos de delito a dibujar. None = todos, [] = ninguno.

    El mapa abre vacío. Un panel permite prender "Mapa de puntos" y "Mapa de
    calor", y elegir qué delitos entran en las dos vistas (todos al abrir).
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
        tiles=None,
    )
    # control=False: el mapa base no aparece como opción en la lista de capas
    folium.TileLayer(
        tiles="https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, Tiles style by <a href="https://www.hotosm.org/">Humanitarian OpenStreetMap Team</a>',
        control=False,
    ).add_to(mapa)

    limites = _limites(puntos)
    if limites:
        mapa.fit_bounds(limites, max_zoom=ZOOM_INICIAL)

    cluster = MarkerCluster(
        icon_create_function=ICONO_CLUSTER,
        control=False,
        options={"maxClusterRadius": 70},
    ).add_to(mapa)

    # Nada se dibuja al abrir (show=False): el mapa arranca liviano y el panel
    # prende lo que el usuario elige. Cada delito es un subgrupo del cluster.
    grupos = []
    tipos_sel = sorted({p["tipo"] for p in puntos}, key=_orden_delito)
    for tipo in tipos_sel:
        color = _color_delito(tipo)
        grupo = FeatureGroupSubGroup(cluster, name=tipo, control=False, show=False)
        grupo.add_to(mapa)
        grupos.append((tipo, color, grupo))

        for p in (q for q in puntos if q["tipo"] == tipo):
            jur = html.escape(p["jurisdiccion"])
            t = html.escape(p["tipo"])
            mod = html.escape(p["modalidad"])
            fecha = html.escape(p["fecha"])
            caratula = (
                f"<b>Carátula:</b> {html.escape(p['caratula'])}<br>" if p["caratula"] else ""
            )

            popup_html = f"""
            <div style="font-family: Arial; font-size: 13px; min-width: 180px;">
                <b>🏛️ {jur}</b><br>
                <b>Delito:</b> {t}<br>
                {caratula}
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

    if grupos:
        # Sin datos propios: el panel le pasa las coordenadas de los delitos tildados
        calor = HeatMap(
            [], name=CAPA_CALOR, radius=22, blur=16, min_opacity=0.35,
            gradient=GRADIENTE_CALOR, control=False, show=False,
        ).add_to(mapa)
        mapa.get_root().header.add_child(folium.Element(ESTILO_PANEL))
        _Panel(_js_panel(mapa, calor, grupos)).add_to(mapa)

    ruta = Path(ruta).resolve() if ruta else ruta_mapa()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    mapa.save(str(ruta))
    logger.info("%d puntos cargados en el mapa.", len(puntos))
    return ruta