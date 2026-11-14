# Vistana

*De Excel a reportes PDF.*

Aplicación de escritorio para el análisis estadístico de denuncias delictuales, desarrollada en Python.
Proyecto anual — Prácticas Profesionalizantes.

---

## Características

- Carga de archivos **Excel (.xlsx)** y **CSV**
- Limpieza automática de datos (fechas, horas, duplicados, normalización), con aviso de lo que se descarta
- Gráficos estadísticos (barras, evolución mensual, donut, ranking, comparación anual)
- **Mapa de calor horario** por día de la semana
- **Mapa interactivo** de los puntos georreferenciados (se abre en el navegador)
- Filtros por año, rango de fechas, jurisdicción y delito
- Exportación a **PDF** con reporte completo (textos, mapa de calor, tablas y gráficos)
- Exportación del **mapa en una hoja A4 apaisada**, con los puntos coloreados por delito
- Exportación a **Excel** con datos filtrados + tabla pivot
- Botón **Limpiar datos** para quitar el archivo cargado y empezar con otro
- Interfaz gráfica de escritorio (**Flet**)
- Modo terminal sin interfaz

---

## Instalación (Windows)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Para desarrollar (tests y herramientas de empaquetado):

```powershell
pip install -r requirements-dev.txt
```

Si falla compilando PyYAML (no tiene versión precompilada para Python 3.15 y pide Visual Studio),
instalarlo antes sin su extensión en C:

```powershell
$env:PYYAML_FORCE_LIBYAML = "0"; pip install --no-binary pyyaml pyyaml
```

---

## Uso

### Interfaz gráfica

```powershell
python main.py
```

### Modo terminal

```powershell
# Análisis completo
python cli.py --archivo datos\denuncias_ejemplo.xlsx

# Con filtros
python cli.py --archivo datos\denuncias_ejemplo.xlsx --anio 2024
python cli.py --archivo datos\denuncias_ejemplo.xlsx --jurisdiccion "Comisaria 1°" "Comisaria 2°"
python cli.py --archivo datos\denuncias_ejemplo.xlsx --tipo_delito Robo Hurto

# Sin generar PDF
python cli.py --archivo datos\denuncias_ejemplo.xlsx --sin_pdf
```

### Generar datos de ejemplo

```powershell
python datos\generar_datos_ejemplo.py
```

Crea `datos\denuncias_ejemplo.xlsx` con denuncias simuladas. Los archivos de denuncias reales
no se versionan (ver `.gitignore`).

### Tests

```powershell
python -m pytest
```

### Generar el instalador

Requiere [Inno Setup 6](https://jrsoftware.org/isdl.php) y las dependencias de desarrollo.

```powershell
powershell -ExecutionPolicy Bypass -File instalador\construir.ps1
```

Empaqueta la app con `flet pack` en `dist\AnalizadorDelictual\` y genera
`instalador\salida\Vistana-<versión>-instalador.exe`, que es lo único que hay que llevar a
otra PC. La versión sale de `VERSION` en `modulos\marca.py`: subila antes de generar una
versión nueva para que el instalador reemplace a la anterior.

El instalador no pide permisos de administrador: instala para el usuario actual en
`%LOCALAPPDATA%\Programs\Vistana` (con permisos de administrador ofrece instalar para todos),
crea el acceso en el menú Inicio y, si se elige, en el escritorio. Se desinstala desde
Configuración → Aplicaciones; eso borra también la carpeta de trabajo, pero no los PDF y
Excel exportados.

El informe PDF lo imprime Microsoft Edge (viene con Windows 10 y 11) o Google Chrome, sin
abrir ninguna ventana. Si la computadora no tiene ninguno de los dos, se genera un reporte
más simple.

**Privacidad del mapa.** El fondo del mapa (calles) del mapa interactivo y del informe PDF se
descarga de los servidores de OpenStreetMap. Esos servidores no reciben las denuncias, pero sí
ven qué zonas y a qué zoom se piden, es decir, aproximadamente dónde se concentran los hechos.
Sin conexión, los puntos se dibujan igual sobre un fondo gris.

---

## Estructura del proyecto

```
analizador-delictual/
│
├── main.py                          # Punto de entrada: interfaz gráfica (Flet)
├── cli.py                           # Modo terminal
├── requirements.txt                 # Dependencias de la aplicación
├── requirements-dev.txt             # Dependencias de desarrollo
│
├── modulos/
│   ├── procesador.py                # Carga, limpieza, filtros y resúmenes
│   ├── graficos.py                  # Gráficos (matplotlib)
│   ├── mapa.py                      # Mapa interactivo (folium)
│   ├── rutas.py                     # Carpetas donde escribe la aplicación
│   └── exportador.py                # Generación de PDF (reportlab)
│
├── datos/
│   └── generar_datos_ejemplo.py     # Script para crear datos de prueba
│
└── tests/                           # Tests automáticos (pytest)
```

### Dónde se guardan los archivos

- **PDF y Excel exportados**: donde el usuario elige en el diálogo "Guardar como".
- **Archivos de trabajo de la interfaz** (mapa y registro de errores):
  `%LOCALAPPDATA%\AnalizadorDelictual`. El mapa contiene datos de las denuncias: se borra con
  "Limpiar datos" y al abrir y cerrar la aplicación. El registro de errores se conserva.
- **Modo terminal**: carpeta `salidas\` del directorio actual, o la indicada con `--salida`.

---

## Formato del archivo de entrada

| Columna | Tipo | Requerida | Descripción |
|---|---|---|---|
| legajo | número o texto | ✓ | Número de legajo. Es único por jurisdicción y año |
| fecha | fecha | ✓ | Celda de fecha, o texto `DD/MM/AAAA` o `AAAA-MM-DD` |
| hora | hora | ✓ | Celda de hora, o texto `HH:MM` |
| tipo_delito | texto | ✓ | Tipo de delito detallado |
| jurisdiccion | texto | ✓ | Comisaría / zona |
| delito | texto | — | Categoría agrupada. Si está, es la que usan filtros, tabla y gráficos |
| modalidad | texto | — | Cómo ocurrió |
| estado | texto | — | Estado de la causa |
| latitud | número | — | Para el mapa |
| longitud | número | — | Para el mapa |
| descripcion | texto | — | Texto libre |

Los registros con fecha que no se puede interpretar se descartan y la aplicación informa cuántos fueron.

---

## Stack tecnológico

| Librería | Uso |
|---|---|
| `flet` | Interfaz gráfica de escritorio |
| `pandas` | Carga, limpieza y análisis de datos |
| `openpyxl` | Lectura/escritura de Excel |
| `flet-charts` | Gráficos interactivos de la app |
| `matplotlib` | Gráficos del reporte PDF |
| `folium` | Mapa interactivo |
| `reportlab` | Generación de PDF |

---

## Autor

Proyecto desarrollado como trabajo anual de **Prácticas Profesionalizantes**.
