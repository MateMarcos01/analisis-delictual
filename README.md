# Analizador Delictual 🔍

Sistema de análisis estadístico de denuncias delictuales desarrollado en Python.
Proyecto anual — Prácticas Profesionalizantes.

---

## Características

- Carga de archivos **Excel (.xlsx)** y **CSV**
- Limpieza automática de datos (fechas, duplicados, normalización)
- 7 tipos de **gráficos estadísticos** (barras, línea temporal, heatmap, donut, etc.)
- **Mapa de calor horario** por día de la semana
- Filtros por año, jurisdicción y tipo de delito
- Exportación a **PDF** con reporte completo
- Exportación a **Excel** con datos filtrados + tabla pivot
- Interfaz gráfica de escritorio (**Tkinter**)
- Modo terminal sin GUI

---

## Instalación

```bash
# 1. Clonar o descomprimir el proyecto
cd analizador_delictual

# 2. Instalar dependencias
pip install -r requirements.txt
```

---

## Uso

### Interfaz gráfica (recomendado)

```bash
python gui.py
```

### Modo terminal

```bash
# Análisis completo
python main.py --archivo datos/datos_denuncias.xlsx

# Con filtros
python main.py --archivo datos/datos_denuncias.xlsx --anio 2024
python main.py --archivo datos/datos_denuncias.xlsx --jurisdiccion Norte Sur
python main.py --archivo datos/datos_denuncias.xlsx --tipo_delito Robo Hurto

# Sin generar PDF
python main.py --archivo datos/datos_denuncias.xlsx --sin_pdf
```

### Generar datos de ejemplo

```bash
cd datos
python generar_datos_ejemplo.py
```

---

## Estructura del proyecto

```
analizador_delictual/
│
├── main.py                          # Punto de entrada (terminal)
├── gui.py                           # Interfaz gráfica (Tkinter)
├── requirements.txt                 # Dependencias
│
├── modulos/
│   ├── __init__.py
│   ├── procesador.py                # Carga, limpieza y filtros
│   ├── graficos.py                  # Todos los gráficos (matplotlib + seaborn)
│   └── exportador.py               # Generación de PDF (reportlab)
│
├── datos/
│   ├── generar_datos_ejemplo.py     # Script para crear datos de prueba
│   └── datos_denuncias.xlsx         # (se genera con el script anterior)
│
└── salidas/
    ├── graficos/                    # PNGs generados
    ├── reportes/                    # PDFs generados
    └── mapas/                       # (reservado para mapas folium)
```

---

## Formato del Excel de entrada

| Columna | Tipo | Requerida | Descripción |
|---|---|---|---|
| nro_denuncia | texto | ✓ | Identificador único |
| fecha | fecha | ✓ | YYYY-MM-DD |
| hora | texto | ✓ | HH:MM |
| tipo_delito | texto | ✓ | Categoría del delito |
| jurisdiccion | texto | ✓ | Zona / comisaría |
| modalidad | texto | — | Cómo ocurrió |
| estado | texto | — | Estado de la causa |
| latitud | número | — | Para mapas |
| longitud | número | — | Para mapas |
| descripcion | texto | — | Texto libre |

---

## Stack tecnológico

| Librería | Uso |
|---|---|
| `pandas` | Carga, limpieza y análisis de datos |
| `openpyxl` | Lectura/escritura de Excel |
| `matplotlib` | Motor de gráficos |
| `seaborn` | Gráficos estadísticos avanzados |
| `numpy` | Cálculos numéricos |
| `scipy` | Estadísticas |
| `reportlab` | Generación de PDF |
| `folium` | Mapas interactivos (próxima versión) |
| `tkinter` | Interfaz gráfica (incluido en Python) |

---

## Próximas funcionalidades

- [ ] Mapa interactivo con `folium`
- [ ] Predicción de tendencias con `scikit-learn`
- [ ] Dashboard web con `streamlit`
- [ ] Comparación entre períodos
- [ ] Alertas automáticas por umbral

---

## Autor

Proyecto desarrollado como trabajo anual de **Prácticas Profesionalizantes**.
