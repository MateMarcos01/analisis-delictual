"""
modulos/informe.py
Informe de evaluación delictual en PDF, con el diseño del sistema web del
Departamento Planeamiento.

El informe es una página HTML (recursos/informe/) que Edge o Chrome, sin
ventana, imprimen a PDF: así sale igual que el del sistema web, que también
lo imprime el navegador. El texto se escribe con reglas fijas a partir de los
números: los mismos datos dan siempre las mismas frases, y cada cifra se puede
verificar contra las tablas.
"""
import os
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from modulos.graficos import COLOR_RESTO, DIAS_ES, _color_delito, matriz_horaria
from modulos.mapa import puntos_validos
from modulos.marca import NOMBRE_VISIBLE
from modulos.procesador import col_delito
from modulos.rutas import carpeta_app

CARPETA_PLANTILLA = Path(__file__).resolve().parent.parent / "recursos" / "informe"

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
# Los días terminados en «s» no cambian en plural
PLURAL_DIA = {"Sábado": "sábados", "Domingo": "domingos"}
MAX_DELITOS = 6
MAX_COMISARIAS = 10
RESTO = "Resto"
# Tiempo que el navegador espera a que cargue el fondo del mapa antes de imprimir
ESPERA_MS = 20000


class NavegadorNoEncontrado(RuntimeError):
    """No hay Edge ni Chrome para imprimir el informe."""


# ─── Formato ──────────────────────────────────────────────────────────────────

def _n(valor: float) -> str:
    """1835 → «1.835»"""
    return f"{valor:,.0f}".replace(",", ".")


def _p(parte: float, total: float) -> str:
    """Porcentaje con un decimal y coma: «54,2 %»"""
    if not total:
        return "0 %"
    return f"{parte * 100 / total:.1f}".replace(".", ",").removesuffix(",0") + " %"


def _hechos(cantidad: int) -> str:
    return f"{_n(cantidad)} {'hecho' if cantidad == 1 else 'hechos'}"


def _mes(clave: str) -> str:
    """«2025-07» → «julio de 2025»"""
    anio, mes = clave.split("-")
    return f"{MESES[int(mes) - 1]} de {anio}"


def _dias(dia: str) -> str:
    return PLURAL_DIA.get(dia, dia.lower())


def _lista(partes: list[str]) -> str:
    """«a, b y c»"""
    if len(partes) <= 1:
        return "".join(partes)
    return ", ".join(partes[:-1]) + " y " + partes[-1]


# ─── Datos ────────────────────────────────────────────────────────────────────

def _datos(df: pd.DataFrame) -> dict:
    """Las cifras del informe: delitos, comisarías, días y franjas, meses y mapa."""
    delito = df[col_delito(df)].fillna("Sin clasificar").astype(str)
    comisaria = df["jurisdiccion"].fillna("Sin comisaría").astype(str)
    conteo = delito.value_counts()

    # Los delitos principales y el resto agrupado
    principales = conteo.head(MAX_DELITOS)
    delitos = principales.index.tolist()
    cantidades = [int(v) for v in principales]
    if len(conteo) > MAX_DELITOS:
        delitos.append(RESTO)
        cantidades.append(int(conteo.iloc[MAX_DELITOS:].sum()))

    comisarias = comisaria.value_counts()
    cruce = pd.crosstab(comisaria, delito.where(delito.isin(principales.index), RESTO))
    cruce = cruce.reindex(index=comisarias.head(MAX_COMISARIAS).index, columns=delitos, fill_value=0)

    mensual = df.groupby(df["fecha"].dt.strftime("%Y-%m")).size().sort_index()

    tabla_horaria = matriz_horaria(df)
    matriz = tabla_horaria.to_numpy()
    horario = {
        "dias": DIAS_ES,
        "filas": [
            {"franja": franja, "valores": [int(v) for v in fila], "total": int(fila.sum())}
            for franja, fila in zip(tabla_horaria.index, matriz)
        ],
        "por_dia": [int(v) for v in matriz.sum(axis=0)],
        "total": int(matriz.sum()),
        "maximo": int(matriz.max()),
    }
    horario["sin_hora"] = len(df) - horario["total"]

    # Un punto por ubicación, con la cantidad de hechos que caen ahí
    puntos = pd.DataFrame(puntos_validos(df), columns=["lat", "lon"])
    por_lugar = puntos.round(5).value_counts().reset_index(name="cantidad")

    return {
        "delitos": delitos,
        "cantidades": cantidades,
        "colores": [COLOR_RESTO if d == RESTO else _color_delito(d) for d in delitos],
        "cruce": cruce,
        "comisarias_total": int(comisarias.size),
        "meses": mensual.index.tolist(),
        "mensual": [int(v) for v in mensual],
        "horario": horario,
        "puntos": por_lugar[["lat", "lon", "cantidad"]].values.tolist(),
        "con_coordenadas": len(puntos),
    }


# ─── Redacción por sección ────────────────────────────────────────────────────

def _texto_delitos(delitos: list, cantidades: list, total: int) -> str:
    principal, cantidad = delitos[0], cantidades[0]
    texto = f"El delito más frecuente fue {principal}, con {_hechos(cantidad)} ({_p(cantidad, total)} del total)"
    if len(delitos) > 1:
        segundo, cantidad_2 = delitos[1], cantidades[1]
        texto += f", seguido por {segundo} con {_n(cantidad_2)} ({_p(cantidad_2, total)})"
        texto += f". Entre ambos reúnen el {_p(cantidad + cantidad_2, total)} de los hechos"
    return texto + "."


def _texto_comisarias(tabla: list[dict], total: int, cantidad_comisarias: int) -> str:
    primera = tabla[0]
    texto = f"{primera['nombre']} registró {_hechos(primera['total'])}, el {_p(primera['total'], total)} del total"
    if len(tabla) >= 3 and cantidad_comisarias > 3:
        tres = sum(fila["total"] for fila in tabla[:3])
        nombres = _lista([fila["nombre"] for fila in tabla[:3]])
        texto += f". Las tres con más hechos ({nombres}) concentran el {_p(tres, total)}"
    elif len(tabla) == 2:
        texto += f"; {tabla[1]['nombre']}, el {_p(tabla[1]['total'], total)} restante"
    return texto + "."


def _texto_horario(horario: dict) -> str:
    if not horario["total"]:
        return "Ningún hecho tiene una hora válida, por lo que no se puede describir su distribución horaria."
    franja = max(horario["filas"], key=lambda fila: fila["total"])
    dia_franja = horario["dias"][franja["valores"].index(max(franja["valores"]))]
    texto = (
        f"La franja de {franja['franja']} reunió {_hechos(franja['total'])}, "
        f"el {_p(franja['total'], horario['total'])} de los que tienen hora registrada"
    )

    celdas = [
        (valor, fila["franja"], horario["dias"][i])
        for fila in horario["filas"]
        for i, valor in enumerate(fila["valores"])
    ]
    maximo, franja_pico, dia_pico = max(celdas)
    promedio = horario["total"] / len(celdas)
    texto += (
        f". El momento de mayor concentración fueron los {_dias(dia_pico)} de {franja_pico}, "
        f"con {_hechos(maximo)}"
    )
    if promedio >= 1 and maximo > promedio:
        veces = f"{maximo / promedio:.1f}".replace(".", ",")
        texto += f", {veces} veces el promedio por franja y día"
    if dia_franja != dia_pico or franja["franja"] != franja_pico:
        texto += f". Dentro de la franja más cargada, el día con más hechos fue el {dia_franja.lower()}"

    dia_mayor = horario["dias"][horario["por_dia"].index(max(horario["por_dia"]))]
    dia_menor = horario["dias"][horario["por_dia"].index(min(horario["por_dia"]))]
    if dia_mayor != dia_menor:
        texto += (
            f". Por día de la semana, el {dia_mayor.lower()} fue el de más hechos ({_n(max(horario['por_dia']))}) "
            f"y el {dia_menor.lower()} el de menos ({_n(min(horario['por_dia']))})"
        )
    return texto + "."


def _texto_mensual(meses: list, mensual: list) -> str:
    pares = list(zip(meses, mensual))
    if len(pares) < 2:
        return f"Todos los hechos corresponden a {_mes(pares[0][0])}."
    mayor = max(pares, key=lambda par: par[1])
    menor = min(pares, key=lambda par: par[1])
    promedio = sum(mensual) / len(pares)
    texto = (
        f"El período abarca {len(pares)} meses, con un promedio de {_n(promedio)} hechos por mes. "
        f"El mes con más hechos fue {_mes(mayor[0])} ({_n(mayor[1])}) y el de menos, {_mes(menor[0])} ({_n(menor[1])})"
    )
    (mes_previo, previo), (mes_ultimo, ultimo) = pares[-2], pares[-1]
    if previo:
        cambio = (ultimo - previo) * 100 / previo
        if abs(cambio) < 0.05:
            texto += f". En {_mes(mes_ultimo)} se registró la misma cantidad que en {_mes(mes_previo)}"
        else:
            sentido = "aumentó" if cambio > 0 else "disminuyó"
            variacion = f"{abs(cambio):.1f}".replace(".", ",").removesuffix(",0")
            texto += (
                f". En {_mes(mes_ultimo)}, último mes del período, la cantidad {sentido} un {variacion} % "
                f"respecto de {_mes(mes_previo)} ({_n(previo)} → {_n(ultimo)})"
            )
    return texto + "."


# ─── Informe completo ─────────────────────────────────────────────────────────

def construir_informe(df: pd.DataFrame, hoy: date | None = None) -> dict:
    """Cifras, tablas, textos y notas del informe de los datos ya filtrados."""
    total = len(df)
    informe = {"emitido": (hoy or date.today()).strftime("%d/%m/%Y"), "total": total, "pie": NOMBRE_VISIBLE}
    if not total:
        return informe

    datos = _datos(df)
    cruce, horario = datos["cruce"], datos["horario"]
    tabla = [
        {"nombre": nombre, "valores": [int(v) for v in fila], "total": int(fila.sum()),
         "porcentaje": _p(int(fila.sum()), total)}
        for nombre, fila in cruce.iterrows()
    ]
    desde, hasta = df["fecha"].min().strftime("%d/%m/%Y"), df["fecha"].max().strftime("%d/%m/%Y")
    franja = max(horario["filas"], key=lambda fila: fila["total"]) if horario["total"] else None

    informe.update({
        "delitos": [
            {"nombre": d, "cantidad": c, "porcentaje": _p(c, total), "color": color}
            for d, c, color in zip(datos["delitos"], datos["cantidades"], datos["colores"])
        ],
        "tabla_comisarias": tabla,
        "horario": horario,
        "graficos": {
            "delitos": datos["delitos"], "cantidades": datos["cantidades"], "colores": datos["colores"],
            "meses": datos["meses"], "mensual": datos["mensual"],
        },
        "puntos": datos["puntos"],
        "con_coordenadas": datos["con_coordenadas"],
        "indicadores": [
            {"etiqueta": "Hechos analizados", "valor": _n(total), "detalle": f"{desde} — {hasta}"},
            {"etiqueta": "Delito más frecuente", "valor": datos["delitos"][0],
             "detalle": f"{_p(datos['cantidades'][0], total)} del total"},
            {"etiqueta": "Comisaría con más hechos", "valor": tabla[0]["nombre"],
             "detalle": f"{tabla[0]['porcentaje']} del total"},
            {"etiqueta": "Franja con más hechos", "valor": franja["franja"] if franja else "—",
             "detalle": f"{_p(franja['total'], horario['total'])} de los hechos con hora" if franja else "Sin horas válidas"},
        ],
    })

    comisarias = datos["comisarias_total"]
    introduccion = (
        f"Entre el {desde} y el {hasta} se registraron {_hechos(total)} "
        f"en {comisarias} {'comisaría' if comisarias == 1 else 'comisarías'}."
    )
    textos = {
        "delitos": _texto_delitos(datos["delitos"], datos["cantidades"], total),
        "comisarias": _texto_comisarias(tabla, total, comisarias),
        "horario": _texto_horario(horario),
        "mensual": _texto_mensual(datos["meses"], datos["mensual"]),
    }
    # El resumen toma la primera oración de cada sección
    textos["resumen"] = " ".join([introduccion] + [
        textos[clave].split(". ")[0].rstrip(".") + "." for clave in ("delitos", "comisarias", "horario")
    ])
    informe["textos"] = textos

    notas = []
    descartes = df.attrs.get("descartes", {})
    if descartes.get("fechas_invalidas"):
        notas.append(f"Al cargar la planilla se omitieron {_n(descartes['fechas_invalidas'])} filas sin fecha válida.")
    if descartes.get("duplicados"):
        notas.append(f"Al cargar la planilla se omitieron {_n(descartes['duplicados'])} filas repetidas.")
    sin_coordenadas = total - datos["con_coordenadas"]
    if sin_coordenadas:
        notas.append(f"{_hechos(sin_coordenadas).capitalize()} no {'tiene' if sin_coordenadas == 1 else 'tienen'} "
                     "coordenadas válidas y no figuran en el mapa.")
    if horario["sin_hora"]:
        notas.append(f"{_hechos(horario['sin_hora']).capitalize()} no {'tiene' if horario['sin_hora'] == 1 else 'tienen'} "
                     "hora válida y no se incluyen en la distribución horaria.")
    omitidas = comisarias - len(tabla)
    if omitidas > 0:
        notas.append(f"La tabla de comisarías muestra las {len(tabla)} con más hechos; las {omitidas} restantes no se detallan.")
    notas.append("El texto de este informe se genera automáticamente a partir de los datos y es descriptivo.")
    informe["notas"] = notas
    return informe


def html_informe(informe: dict) -> str:
    """La página del informe, lista para imprimir."""
    entorno = Environment(
        loader=FileSystemLoader(CARPETA_PLANTILLA),
        autoescape=select_autoescape(["html"]),
    )
    entorno.filters["n"] = _n
    # Las bibliotecas y fuentes se cargan desde la carpeta de la plantilla
    base = CARPETA_PLANTILLA.as_uri() + "/"
    return entorno.get_template("informe.html").render(base=base, **informe)


# ─── PDF ──────────────────────────────────────────────────────────────────────

def buscar_navegadores() -> list[str]:
    """Edge (viene con Windows) y Chrome, los que estén instalados."""
    candidatos = []
    for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if base:
            candidatos += [Path(base) / "Microsoft/Edge/Application/msedge.exe",
                           Path(base) / "Google/Chrome/Application/chrome.exe"]
    encontrados = [str(c) for c in candidatos if c.is_file()]
    encontrados += [shutil.which(n) for n in ("msedge", "chrome", "google-chrome", "chromium") if shutil.which(n)]
    return list(dict.fromkeys(encontrados))


def exportar_informe(df: pd.DataFrame, ruta_pdf, navegadores: list[str] | None = None) -> Path:
    """
    Genera el PDF del informe con el primer navegador que lo logre (Edge puede
    fallar, por ejemplo, mientras se actualiza). Lanza NavegadorNoEncontrado si
    ninguno pudo.
    """
    navegadores = navegadores if navegadores is not None else buscar_navegadores()
    ruta_pdf = Path(ruta_pdf).resolve()
    ruta_pdf.parent.mkdir(parents=True, exist_ok=True)

    # La página tiene los datos de las denuncias: se escribe en una carpeta
    # temporal y se borra al terminar. Perfil propio del navegador: no toca
    # las pestañas ni la sesión que el usuario tenga abiertas. Un proceso del
    # navegador puede tardar en soltar su perfil (caché, sin datos de denuncias):
    # eso no debe hacer fallar la exportación.
    with tempfile.TemporaryDirectory(dir=carpeta_app(), prefix="informe_", ignore_cleanup_errors=True) as temporal:
        pagina = Path(temporal) / "informe.html"
        pagina.write_text(html_informe(construir_informe(df)), encoding="utf-8")
        destino = Path(temporal) / "informe.pdf"
        for i, navegador in enumerate(navegadores):
            try:
                subprocess.run(
                    [
                        navegador, "--headless", "--disable-gpu", "--no-first-run",
                        "--no-pdf-header-footer", f"--user-data-dir={Path(temporal) / f'perfil_{i}'}",
                        f"--virtual-time-budget={ESPERA_MS}", f"--print-to-pdf={destino}",
                        pagina.as_uri(),
                    ],
                    capture_output=True, timeout=120,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if destino.is_file() and destino.read_bytes().startswith(b"%PDF"):
                # Se escribe recién al final: un error no deja un PDF a medias en el destino
                shutil.move(str(destino), ruta_pdf)
                return ruta_pdf
    raise NavegadorNoEncontrado("Ni Microsoft Edge ni Google Chrome pudieron generar el informe.")
