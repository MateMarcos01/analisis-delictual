"""
cli.py — Punto de entrada alternativo (sin GUI).
Útil para ejecutar el análisis completo desde la terminal
o en entornos sin pantalla (servidores, CI).

Uso:
    python cli.py --archivo datos/denuncias.xlsx
    python cli.py --archivo datos/denuncias.xlsx --anio 2025
    python cli.py --archivo datos/denuncias.xlsx --jurisdiccion "Comisaria 13°"
"""
import argparse
import logging
import sys
from pathlib import Path

from modulos.procesador import cargar_excel, resumen_general, filtrar, tabla_pivot
from modulos.graficos   import generar_todos
from modulos.exportador import generar_reporte


def main():
    # La consola de Windows (cp1252) no puede mostrar algunos símbolos:
    # se reemplazan en vez de abortar con UnicodeEncodeError.
    if sys.stdout is not None:
        sys.stdout.reconfigure(errors="replace")
    logging.basicConfig(level=logging.WARNING, format="   ! %(message)s")

    parser = argparse.ArgumentParser(
        description="Analizador Delictual — modo terminal"
    )
    parser.add_argument("--archivo",      required=True, help="Ruta al .xlsx o .csv")
    parser.add_argument("--anio",         type=int,      help="Filtrar por año")
    parser.add_argument("--jurisdiccion", nargs="+",     help="Una o más jurisdicciones")
    parser.add_argument("--tipo_delito",  nargs="+",     help="Uno o más tipos de delito")
    parser.add_argument("--sin_pdf",      action="store_true", help="No generar PDF")
    parser.add_argument("--salida",       default="salidas",   help="Carpeta de salida (por defecto: salidas)")
    args = parser.parse_args()

    print("\n══════════════════════════════════════════")
    print("   ANALIZADOR DELICTUAL  —  modo terminal  ")
    print("══════════════════════════════════════════\n")

    # 1. Carga
    print(f"▶  Cargando: {args.archivo}")
    try:
        df = cargar_excel(args.archivo)
    except (FileNotFoundError, ValueError) as e:
        print(f"✗  {e}\n")
        return 1
    print(f"   {len(df):,} registros cargados.\n")

    # 2. Filtros opcionales
    kwargs = {}
    if args.anio:
        kwargs["anio"] = args.anio
    if args.jurisdiccion:
        kwargs["jurisdicciones"] = args.jurisdiccion
    if args.tipo_delito:
        kwargs["tipos_delito"] = args.tipo_delito

    if kwargs:
        print("▶  Aplicando filtros…")
        df = filtrar(df, **kwargs)
        print(f"   {len(df):,} registros después del filtro.\n")

    if df.empty:
        print("✗  No hay registros para analizar.\n")
        return 1

    # 3. Resumen
    resumen = resumen_general(df)
    print("▶  Resumen general")
    print(f"   Total denuncias   : {resumen['total_denuncias']:,}")
    print(f"   Período           : {resumen['periodo_desde']} → {resumen['periodo_hasta']}")
    print(f"   Delito principal  : {resumen['delito_principal']}")
    print(f"   Jurisdicción top  : {resumen['jurisdiccion_top']}")
    print(f"   Mes pico          : {resumen['mes_pico']}\n")

    pivot = tabla_pivot(df)
    print("▶  Tabla cruzada (jurisdicción × tipo de delito)")
    print(pivot.to_string())
    print()

    # 4. Gráficos
    print("▶  Generando gráficos…")
    salida = Path(args.salida)
    rutas = generar_todos(df, carpeta=salida / "graficos")
    print(f"   {len(rutas)} gráficos guardados en {salida / 'graficos'}\n")

    # 5. PDF
    if not args.sin_pdf:
        print("▶  Generando reporte PDF…")
        ruta_pdf = generar_reporte(resumen, rutas, pivot, carpeta=salida / "reportes")
        print(f"   PDF: {ruta_pdf}\n")

    print("✓  Proceso completado.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
