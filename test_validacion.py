"""
test_validacion.py
Script de prueba para la función validar_datos_completos()

Ejecutar con: python test_validacion.py
"""
import pandas as pd
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from modulos.procesador import cargar_excel, validar_datos_completos, _limpiar


def test_con_datos_reales():
    """Prueba 1: Validar datos reales cargados del Excel"""
    print("\n" + "="*70)
    print("PRUEBA 1: Validar datos reales del Excel")
    print("="*70)

    try:
        df = cargar_excel("datos/datos_denuncias.xlsx")
        print(f"\n[OK] Excel cargado: {len(df)} registros")

        # Llamar la función de validación
        resultado = validar_datos_completos(df)

        # Mostrar resultados
        print(f"\n{'Válido':.<30} {resultado['valido']}")

        if resultado["problemas"]:
            print(f"\n[!] PROBLEMAS ENCONTRADOS ({len(resultado['problemas'])}):")
            for i, problema in enumerate(resultado["problemas"], 1):
                print(f"   {i}. {problema}")
        else:
            print("\n[OK] No hay problemas - datos limpios")

        # Mostrar resumen
        print(f"\nRESUMEN ESTADÍSTICO:")
        for clave, valor in resultado["resumen"].items():
            print(f"  {clave}:{str(valor):.>35}")

    except FileNotFoundError:
        print("[!] No se encontro datos/datos_denuncias.xlsx")
        print("  Saltando Prueba 1...")


def test_con_datos_problematicos():
    """Prueba 2: Crear DataFrame CON ERRORES deliberados y validar"""
    print("\n" + "="*70)
    print("PRUEBA 2: DataFrame con errores deliberados")
    print("="*70)

    # Crear DataFrame con problemas
    df_problematico = pd.DataFrame({
        "nro_denuncia": ["D001", "D002", None, "D004", "D005"],
        "fecha": ["2024-01-15", "1999-12-01", "2024-01-16", None, "2026-12-25"],  # Antigua, futura, NULL
        "hora": ["14:30", "10:45", "22:10", "25:30", "23:59"],  # hora 25 es inválida
        "tipo_delito": ["Robo", "Hurto", "Robo", "Fraude", "Robo"],
        "jurisdiccion": ["Norte", "Sur", "Centro", "Este", "Oeste"],
    })

    # Procesar con _limpiar() para que cree la columna hora_num
    df_problematico["fecha"] = pd.to_datetime(df_problematico["fecha"], errors="coerce")
    df_problematico["hora_dt"] = pd.to_datetime(
        df_problematico["fecha"].dt.date.astype(str) + " " + df_problematico["hora"].astype(str),
        errors="coerce"
    )
    df_problematico["hora_num"] = df_problematico["hora_dt"].dt.hour

    print(f"\n{len(df_problematico)} registros creados deliberadamente con errores:\n")
    print(df_problematico[["nro_denuncia", "fecha", "hora_num", "tipo_delito"]])

    # Validar
    resultado = validar_datos_completos(df_problematico)

    print(f"\n{'Valido':.<30} {resultado['valido']}")

    if resultado["problemas"]:
        print(f"\n[!] PROBLEMAS ENCONTRADOS ({len(resultado['problemas'])}):")
        for i, problema in enumerate(resultado["problemas"], 1):
            print(f"   {i}. {problema}")

    print(f"\nRESUMEN:")
    for clave, valor in resultado["resumen"].items():
        print(f"  {clave}:{str(valor):.>35}")


def test_datos_limpios():
    """Prueba 3: DataFrame perfecto (sin errores)"""
    print("\n" + "="*70)
    print("PRUEBA 3: DataFrame perfecto (sin errores)")
    print("="*70)

    df_limpio = pd.DataFrame({
        "nro_denuncia": ["D001", "D002", "D003", "D004"],
        "fecha": ["2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18"],
        "hora": ["14:30", "10:45", "22:10", "08:00"],
        "tipo_delito": ["Robo", "Hurto", "Robo", "Fraude"],
        "jurisdiccion": ["Norte", "Sur", "Centro", "Este"],
    })

    df_limpio["fecha"] = pd.to_datetime(df_limpio["fecha"])
    df_limpio["hora_dt"] = pd.to_datetime(
        df_limpio["fecha"].dt.date.astype(str) + " " + df_limpio["hora"].astype(str)
    )
    df_limpio["hora_num"] = df_limpio["hora_dt"].dt.hour

    print(f"\n{len(df_limpio)} registros SIN errores\n")
    print(df_limpio[["nro_denuncia", "fecha", "hora_num", "tipo_delito"]])

    resultado = validar_datos_completos(df_limpio)

    print(f"\n{'Valido':.<30} {resultado['valido']}")

    if resultado["problemas"]:
        print(f"\n[!] PROBLEMAS ENCONTRADOS:")
        for problema in resultado["problemas"]:
            print(f"   - {problema}")
    else:
        print("\n[OK] PERFECTO - Sin problemas detectados")

    print(f"\nRESUMEN:")
    for clave, valor in resultado["resumen"].items():
        print(f"  {clave}:{str(valor):.>35}")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("  TEST: Funcion validar_datos_completos()")
    print("="*70)

    test_con_datos_reales()
    test_con_datos_problematicos()
    test_datos_limpios()

    print("\n" + "="*70)
    print("  [OK] Pruebas completadas")
    print("="*70 + "\n")
