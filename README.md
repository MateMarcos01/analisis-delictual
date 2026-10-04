# Analizador Delictual

Aplicación de escritorio para el análisis estadístico de denuncias delictuales, desarrollada en Python.
Proyecto anual — Prácticas Profesionalizantes.

---

## Características

- Carga de archivos **Excel (.xlsx)** y **CSV**
- Limpieza automática de datos (fechas, horas, duplicados, normalización), con aviso de lo que se descarta
- Gráficos estadísticos (barras, evolución mensual, donut, ranking, comparación anual)
- **Mapa de calor horario** por día de la semana
- **Mapa interactivo** de los puntos georreferenciados (se abre en el navegador)
- Filtros por año, jurisdicción y delito
- Exportación a **PDF** con reporte completo
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
- **Archivos de trabajo de la interfaz** (gráficos, mapa y registro de errores):
  `%LOCALAPPDATA%\AnalizadorDelictual`. Contienen datos de las denuncias cargadas.
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
| `matplotlib` + `seaborn` | Gráficos |
| `folium` | Mapa interactivo |
| `reportlab` | Generación de PDF |

---

## Autor

Proyecto desarrollado como trabajo anual de **Prácticas Profesionalizantes**.
