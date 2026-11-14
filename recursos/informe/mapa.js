// Mapa imprimible encuadrado en el grueso de los hechos: el calor o, si se
// pasan, los puntos con el color de su delito. No los dos: Robo es rojo y
// Hurto verde, los mismos tonos del calor. Sin animaciones: el navegador
// imprime apenas termina de cargar. Lo usan el informe y la hoja de mapa.
//   calor:   [[lat, lon, cantidad], ...] (un elemento por ubicación)
//   puntos:  [[lat, lon, color], ...] (opcional)
function dibujarMapa(elemento, calor, puntos) {
  const map = L.map(elemento, {
    zoomControl: false, zoomSnap: 0.25, fadeAnimation: false, zoomAnimation: false, markerZoomAnimation: false,
  }).setView([-31.52, -68.52], 11);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap' }).addTo(map);

  // Unos pocos puntos muy alejados (a menudo coordenadas mal cargadas)
  // achicarían todo el mapa: se encuadra entre el 2 % y el 98 %
  const cuantil = (valores, q) => valores[Math.min(valores.length - 1, Math.floor(q * valores.length))];
  const latitudes = calor.map(p => p[0]).sort((a, b) => a - b);
  const longitudes = calor.map(p => p[1]).sort((a, b) => a - b);
  map.fitBounds([
    [cuantil(latitudes, 0.02), cuantil(longitudes, 0.02)],
    [cuantil(latitudes, 0.98), cuantil(longitudes, 0.98)],
  ], { padding: [14, 14], maxZoom: 16 });

  if (puntos) {
    // Lienzo en lugar de SVG: miles de puntos se dibujan sin trabar la impresión
    const lienzo = L.canvas();
    for (const [lat, lon, color] of puntos) {
      L.circleMarker([lat, lon], {
        renderer: lienzo, radius: 2.6, weight: 0.6, color: '#ffffff', fillColor: color, fillOpacity: 0.9,
      }).addTo(map);
    }
    return;
  }

  // Escala del calor según lo que se ve: el rojo queda para lo más concentrado
  const RADIO = 18, DIFUSION = 16, celda = RADIO + DIFUSION;
  const porCelda = new Map();
  let maximo = 1;
  for (const [lat, lon, cantidad] of calor) {
    const pixel = map.project([lat, lon], map.getZoom());
    const clave = Math.floor(pixel.x / celda) + ':' + Math.floor(pixel.y / celda);
    const suma = (porCelda.get(clave) || 0) + cantidad;
    porCelda.set(clave, suma);
    maximo = Math.max(maximo, suma);
  }
  L.heatLayer(calor, {
    radius: RADIO, blur: DIFUSION, minOpacity: 0.12, maxZoom: 1, max: Math.max(1, maximo * 0.6),
    gradient: { 0.25: '#00A63E', 0.55: '#FFD000', 0.8: '#FF7A00', 1: '#E60000' },
  }).addTo(map);
}
