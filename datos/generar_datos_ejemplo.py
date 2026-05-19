"""
Genera un archivo Excel de ejemplo con denuncias simuladas.
Ejecutar una sola vez para tener datos de prueba.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

random.seed(42)
np.random.seed(42)

TIPOS_DELITO = ["Robo", "Hurto", "Lesiones", "Amenazas", "Daño", "Fraude"]
JURISDICCIONES = ["Norte", "Sur", "Centro", "Este", "Oeste", "Puerto"]
ESTADOS = ["Activa", "En investigación", "Cerrada", "Archivada"]
MODALIDADES = ["En vía pública", "En domicilio", "En comercio", "En transporte", "Online"]

PESOS_DELITO = [0.30, 0.25, 0.18, 0.13, 0.08, 0.06]
PESOS_JURIS  = [0.20, 0.18, 0.22, 0.15, 0.14, 0.11]

fecha_inicio = datetime(2023, 1, 1)
fecha_fin    = datetime(2024, 12, 31)
total_dias   = (fecha_fin - fecha_inicio).days

n = 2847
registros = []

for i in range(1, n + 1):
    dias_offset = random.randint(0, total_dias)
    # pico en horario tarde-noche y fin de semana
    hora   = int(np.random.choice(range(24), p=[
        0.01,0.01,0.01,0.01,0.02,0.02,0.03,0.04,
        0.05,0.05,0.05,0.05,0.05,0.05,0.05,0.07,
        0.07,0.07,0.07,0.06,0.05,0.04,0.03,0.02
    ]))
    minuto = random.randint(0, 59)
    fecha  = fecha_inicio + timedelta(days=dias_offset, hours=hora, minutes=minuto)

    tipo        = np.random.choice(TIPOS_DELITO, p=PESOS_DELITO)
    jurisdiccion = np.random.choice(JURISDICCIONES, p=PESOS_JURIS)

    registros.append({
        "nro_denuncia":  f"DEN-{i:05d}",
        "fecha":         fecha.strftime("%Y-%m-%d"),
        "hora":          fecha.strftime("%H:%M"),
        "tipo_delito":   tipo,
        "modalidad":     random.choice(MODALIDADES),
        "jurisdiccion":  jurisdiccion,
        "estado":        np.random.choice(ESTADOS, p=[0.25, 0.35, 0.30, 0.10]),
        "latitud":       round(-34.60 + random.uniform(-0.15, 0.15), 6),
        "longitud":      round(-58.38 + random.uniform(-0.20, 0.20), 6),
        "descripcion":   f"Denuncia por {tipo.lower()} en zona {jurisdiccion}.",
    })

df = pd.DataFrame(registros)
df.to_excel("datos_denuncias.xlsx", index=False)
print(f"Archivo generado: datos_denuncias.xlsx ({n} registros)")
print(df.head())
