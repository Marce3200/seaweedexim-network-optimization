# -*- coding: utf-8 -*-
"""
cargar_datos.py
---------------
PASO 2: lee el archivo data/tablas_8_hojas.xlsx (8 hojas preparadas por el
grupo) y devuelve todos los parametros del modelo como diccionarios de
Python, listos para construir el modelo en Gurobi.

La funcion principal es cargar_datos(), que retorna un objeto Datos con:
  - plantas, mercados, productos        (listas / conjuntos)
  - demanda[mercado][producto]          (millones de kg)
  - capacidad[planta]                   (millones de kg)
  - cf_planta[planta]                   (millones US$)  -> costo fijo de planta
  - cf_producto[planta][producto]       (millones US$)  -> costo fijo por linea
  - cvar[planta][producto]              (US$/kg)        -> MP + produccion
  - transporte[planta][mercado]         (US$/kg)
  - arancel[mercado]                    (fraccion, p.ej. 0.556)
  - aplica_arancel[(planta, mercado)]   (1 = paga arancel, 0 = local/exento)

Diseno: separamos la carga de datos del modelo para que, si el Excel
cambia, solo se modifique este archivo y el modelo quede intacto.
"""

from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd


# Ruta al Excel: por defecto data/tablas_8_hojas.xlsx relativo a la raiz del repo.
RUTA_EXCEL_DEFECTO = Path(__file__).resolve().parent.parent / "data" / "tablas_8_hojas.xlsx"


@dataclass
class Datos:
    """Contenedor de todos los parametros del modelo."""
    plantas: list = field(default_factory=list)
    mercados: list = field(default_factory=list)
    productos: list = field(default_factory=list)

    demanda: dict = field(default_factory=dict)          # demanda[mercado][producto]
    capacidad: dict = field(default_factory=dict)        # capacidad[planta]
    cf_planta: dict = field(default_factory=dict)        # cf_planta[planta]
    cf_producto: dict = field(default_factory=dict)      # cf_producto[planta][producto]
    cvar: dict = field(default_factory=dict)             # cvar[planta][producto]
    transporte: dict = field(default_factory=dict)       # transporte[planta][mercado]
    arancel: dict = field(default_factory=dict)          # arancel[mercado]
    aplica_arancel: dict = field(default_factory=dict)   # aplica_arancel[(planta, mercado)]


def cargar_datos(ruta_excel: Path = RUTA_EXCEL_DEFECTO) -> Datos:
    """Lee las 8 hojas del Excel y devuelve un objeto Datos con diccionarios."""
    ruta_excel = Path(ruta_excel)
    if not ruta_excel.exists():
        raise FileNotFoundError(f"No se encontro el Excel en: {ruta_excel}")

    # Leemos todas las hojas de una vez. sheet_name=None -> dict {nombre_hoja: DataFrame}
    hojas = pd.read_excel(ruta_excel, sheet_name=None)

    d = Datos()

    # --- Hoja Demanda: columnas [Mercado, Producto, Demanda] ---
    dem = hojas["Demanda"]
    for _, fila in dem.iterrows():
        mercado, producto, valor = fila["Mercado"], fila["Producto"], float(fila["Demanda"])
        d.demanda.setdefault(mercado, {})[producto] = valor

    # --- Hoja Capacidad: columnas [Planta, Capacidad] ---
    cap = hojas["Capacidad"]
    for _, fila in cap.iterrows():
        d.capacidad[fila["Planta"]] = float(fila["Capacidad"])

    # --- Hoja CostosFijosPlanta: columnas [Planta, CostoFijo] ---
    cfp = hojas["CostosFijosPlanta"]
    for _, fila in cfp.iterrows():
        d.cf_planta[fila["Planta"]] = float(fila["CostoFijo"])

    # --- Hoja CostosFijosProducto: columnas [Planta, Producto, CostoFijoProducto] ---
    cfpr = hojas["CostosFijosProducto"]
    for _, fila in cfpr.iterrows():
        planta, producto, valor = fila["Planta"], fila["Producto"], float(fila["CostoFijoProducto"])
        d.cf_producto.setdefault(planta, {})[producto] = valor

    # --- Hoja CostosVariables: usamos la columna ya sumada CostoVariable (MP + Produccion) ---
    cv = hojas["CostosVariables"]
    for _, fila in cv.iterrows():
        planta, producto, valor = fila["Planta"], fila["Producto"], float(fila["CostoVariable"])
        d.cvar.setdefault(planta, {})[producto] = valor

    # --- Hoja Transporte: columnas [Planta, Mercado, Transporte] ---
    tr = hojas["Transporte"]
    for _, fila in tr.iterrows():
        planta, mercado, valor = fila["Planta"], fila["Mercado"], float(fila["Transporte"])
        d.transporte.setdefault(planta, {})[mercado] = valor

    # --- Hoja Aranceles: columnas [Mercado, Arancel] ---
    ar = hojas["Aranceles"]
    for _, fila in ar.iterrows():
        d.arancel[fila["Mercado"]] = float(fila["Arancel"])

    # --- Hoja PlantaMercado: columnas [Planta, MercadoPlanta, Mercado, AplicaArancel] ---
    #     AplicaArancel = 1 si el flujo paga arancel, 0 si es local (exento).
    pm = hojas["PlantaMercado"]
    for _, fila in pm.iterrows():
        planta, mercado, aplica = fila["Planta"], fila["Mercado"], int(fila["AplicaArancel"])
        d.aplica_arancel[(planta, mercado)] = aplica

    # --- Conjuntos: los derivamos de los datos para no escribirlos a mano ---
    d.plantas = sorted(d.capacidad.keys())
    d.mercados = sorted(d.demanda.keys())
    d.productos = sorted({p for m in d.demanda.values() for p in m.keys()})

    return d


# Bloque de prueba: ejecutar este archivo directamente imprime un resumen
# y valida que todo cargo correctamente, sin tocar aun el modelo.
if __name__ == "__main__":
    datos = cargar_datos()

    print("=" * 60)
    print("CARGA DE DATOS - RESUMEN")
    print("=" * 60)
    print(f"Plantas   ({len(datos.plantas)}): {datos.plantas}")
    print(f"Mercados  ({len(datos.mercados)}): {datos.mercados}")
    print(f"Productos ({len(datos.productos)}): {datos.productos}")
    print()

    # Validaciones de integridad
    print("VALIDACIONES:")
    errores = []

    # 1) Cada planta tiene capacidad, costo fijo y costos por producto
    for p in datos.plantas:
        if p not in datos.capacidad:  errores.append(f"Falta capacidad de {p}")
        if p not in datos.cf_planta:  errores.append(f"Falta costo fijo de {p}")
        for k in datos.productos:
            if k not in datos.cf_producto.get(p, {}): errores.append(f"Falta cf_producto[{p}][{k}]")
            if k not in datos.cvar.get(p, {}):        errores.append(f"Falta cvar[{p}][{k}]")

    # 2) Cada par (planta, mercado) tiene transporte y bandera de arancel
    for p in datos.plantas:
        for m in datos.mercados:
            if m not in datos.transporte.get(p, {}):   errores.append(f"Falta transporte[{p}][{m}]")
            if (p, m) not in datos.aplica_arancel:     errores.append(f"Falta aplica_arancel[{p},{m}]")

    # 3) Chequeo de factibilidad agregada (capacidad total vs demanda total)
    cap_total = sum(datos.capacidad.values())
    dem_total = sum(v for m in datos.demanda.values() for v in m.values())
    print(f"  Capacidad total red : {cap_total:.1f} millones kg")
    print(f"  Demanda total       : {dem_total:.1f} millones kg")
    print(f"  Factible (cap>=dem) : {cap_total >= dem_total}")

    # 4) Mostrar que pares son locales (exentos de arancel)
    locales = [(p, m) for (p, m), a in datos.aplica_arancel.items() if a == 0]
    print(f"  Pares locales (exentos de arancel): {locales}")

    print()
    if errores:
        print(f"  SE ENCONTRARON {len(errores)} PROBLEMAS:")
        for e in errores:
            print(f"    - {e}")
    else:
        print("  OK: Todos los datos estan completos y consistentes.")