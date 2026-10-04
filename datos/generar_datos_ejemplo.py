"""
Genera un archivo Excel de ejemplo con denuncias simuladas.
Ejecutar una sola vez para tener datos de prueba:
    python datos/generar_datos_ejemplo.py
"""
import pandas as pd
import numpy as np
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
import random

random.seed(42)
np.random.seed(42)

TIPOS_DELITO = ["Robo", "Hurto", "Ttva Robo", "Ttva Hurto", "Otros"]
JURISDICCIONES = ["Comisaria 1°", "Comisaria 2°", "Comisaria 3°", "Comisaria 4°", "Comisaria 5°", "Comisaria 6°"]
MODALIDADES = ["En vía pública", "En domicilio", "En comercio", "En transporte", "Online"]

PESOS_DELITO = [0.38, 0.40, 0.06, 0.04, 0.12]
PESOS_JURIS  = [0.20, 0.18, 0.22, 0.15, 0.14, 0.11]

fecha_inicio = datetime(2023, 1, 1)
fecha_fin    = datetime(2024, 12, 31)
total_dias   = (fecha_fin - fecha_inicio).days

n = 2847
registros = []
# Cada jurisdicción numera sus legajos desde 1 y vuelve a empezar cada año
legajos = Counter()

for _ in range(n):
    dias_offset = random.randint(0, total_dias)
    # pico en horario tarde-noche y fin de semana
    pesos_hora = np.array([
        0.01,0.01,0.01,0.01,0.02,0.02,0.03,0.04,
        0.05,0.05,0.05,0.05,0.05,0.05,0.05,0.07,
        0.07,0.07,0.07,0.06,0.05,0.04,0.03,0.02
    ])
    hora   = int(np.random.choice(range(24), p=pesos_hora / pesos_hora.sum()))
    minuto = random.randint(0, 59)
    fecha  = fecha_inicio + timedelta(days=dias_offset, hours=hora, minutes=minuto)

    tipo         = str(np.random.choice(TIPOS_DELITO, p=PESOS_DELITO))
    jurisdiccion = str(np.random.choice(JURISDICCIONES, p=PESOS_JURIS))
    legajos[(jurisdiccion, fecha.year)] += 1

    registros.append({
        "legajo":        legajos[(jurisdiccion, fecha.year)],
        "fecha":         fecha.strftime("%d/%m/%Y"),
        "hora":          fecha.strftime("%H:%M"),
        "tipo_delito":   tipo,
        "modalidad":     random.choice(MODALIDADES),
        "jurisdiccion":  jurisdiccion,
        "latitud":       round(-31.5375 + random.uniform(-0.04, 0.04), 6),
        "longitud":      round(-68.5364 + random.uniform(-0.05, 0.05), 6),
    })

df = pd.DataFrame(registros)
ruta = Path(__file__).resolve().parent / "denuncias_ejemplo.xlsx"
df.to_excel(ruta, index=False)
print(f"Archivo generado: {ruta} ({n} registros)")
print(df.head())
