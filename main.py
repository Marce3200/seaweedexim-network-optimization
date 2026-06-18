# -*- coding: utf-8 -*-
"""
main.py
-------
PASO 4: punto de entrada del proyecto. Orquesta el flujo completo:
 
  1. Carga los datos del Excel.
  2. Resuelve el ESCENARIO BASE (con aranceles).
  3. Resuelve el ESCENARIO SIN ARANCELES (pregunta c).
  4. Reporta para cada escenario: costo total y su desglose, plantas y
     lineas abiertas/cerradas, produccion por planta y flujos por mercado.
  5. Compara ambos escenarios.
  6. Exporta todos los resultados a resultados/resultados_seaweedexim.xlsx.
 
Ejecutar desde la raiz del repo:   python3 main.py
"""
 
from pathlib import Path
import sys
 
# Permitir importar desde src/ sin importar desde donde se ejecute.
RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))
 
import pandas as pd
from gurobipy import GRB
 
from cargar_datos import cargar_datos
from modelo import construir_modelo, resolver
from reportes import generar_graficos, generar_word_respuestas
 
 
# Parametros de cierre (del enunciado, Tabla 5):
ALPHA = 0.40   # ahorro al cerrar una planta completa
BETA  = 0.20   # ahorro al cerrar la linea de un producto
 
RUTA_RESULTADOS = RAIZ / "resultados" / "resultados_seaweedexim.xlsx"
 
 
# ======================================================================
# Funciones de extraccion de resultados
# ======================================================================
def desglose_costos(datos, x, y, z, aplicar_aranceles, alpha, beta):
    """Calcula el costo total separado en sus cinco componentes (millones US$)."""
    P, M, K = datos.plantas, datos.mercados, datos.productos
 
    c_fijo_planta = sum(
        datos.cf_planta[p] * ((1 - alpha) + alpha * y[p].X) for p in P
    )
    c_fijo_producto = sum(
        datos.cf_producto[p][k] * ((1 - beta) + beta * z[p, k].X)
        for p in P for k in K
    )
    c_variable = sum(
        datos.cvar[p][k] * x[p, k, mk].X
        for p in P for k in K for mk in M
    )
    c_transporte = sum(
        datos.transporte[p][mk] * x[p, k, mk].X
        for p in P for k in K for mk in M
    )
    if aplicar_aranceles:
        c_arancel = sum(
            datos.arancel[mk] * (datos.cvar[p][k] + datos.transporte[p][mk]) * x[p, k, mk].X
            for p in P for k in K for mk in M
            if datos.aplica_arancel[(p, mk)] == 1
        )
    else:
        c_arancel = 0.0
 
    return {
        "Costo fijo plantas":   c_fijo_planta,
        "Costo fijo productos": c_fijo_producto,
        "Costo variable":       c_variable,
        "Costo transporte":     c_transporte,
        "Aranceles":            c_arancel,
        "TOTAL":                c_fijo_planta + c_fijo_producto + c_variable + c_transporte + c_arancel,
    }
 
 
def tabla_flujos(datos, x):
    """DataFrame con los flujos activos planta->mercado por producto."""
    filas = []
    for p in datos.plantas:
        for k in datos.productos:
            for mk in datos.mercados:
                v = x[p, k, mk].X
                if v > 1e-6:
                    filas.append({"Planta": p, "Producto": k, "Mercado": mk,
                                  "MillKg": round(v, 4)})
    return pd.DataFrame(filas)
 
 
def tabla_estado_plantas(datos, y, z):
    """DataFrame con el estado de cada planta y sus lineas."""
    filas = []
    for p in datos.plantas:
        abierta = y[p].X > 0.5
        lineas_abiertas = [k for k in datos.productos if z[p, k].X > 0.5]
        filas.append({
            "Planta": p,
            "Estado": "ABIERTA" if abierta else "CERRADA",
            "LineasAbiertas": ", ".join(lineas_abiertas) if lineas_abiertas else "(ninguna)",
        })
    return pd.DataFrame(filas)
 
 
def tabla_produccion(datos, x):
    """DataFrame con la produccion total por planta y producto."""
    filas = []
    for p in datos.plantas:
        for k in datos.productos:
            tot = sum(x[p, k, mk].X for mk in datos.mercados)
            if tot > 1e-6:
                filas.append({"Planta": p, "Producto": k, "ProduccionMillKg": round(tot, 4)})
    return pd.DataFrame(filas)
 
 
# ======================================================================
# Funcion de reporte por consola
# ======================================================================
def reportar(datos, x, y, z, costos, titulo):
    print("=" * 64)
    print(titulo)
    print("=" * 64)
    print(f"COSTO TOTAL OPTIMO: {costos['TOTAL']:,.3f} millones US$\n")
 
    print("Desglose de costos (millones US$):")
    for nombre, valor in costos.items():
        if nombre != "TOTAL":
            pct = 100 * valor / costos["TOTAL"] if costos["TOTAL"] else 0
            print(f"  {nombre:24s}: {valor:10,.3f}  ({pct:5.1f}%)")
    print()
 
    print("Estado de plantas:")
    for _, fila in tabla_estado_plantas(datos, y, z).iterrows():
        print(f"  {fila['Planta']:8s}: {fila['Estado']:8s} | lineas: {fila['LineasAbiertas']}")
    print()
 
    print("Produccion por planta y producto [millones kg]:")
    for _, fila in tabla_produccion(datos, x).iterrows():
        print(f"  {fila['Planta']:8s} {fila['Producto']:16s}: {fila['ProduccionMillKg']:8.2f}")
    print()
 
 
# ======================================================================
# Programa principal
# ======================================================================
def main():
    print("\nCargando datos...\n")
    datos = cargar_datos()
 
    # --- Escenario base (con aranceles) ---
    mb, xb, yb, zb = construir_modelo(datos, aplicar_aranceles=True,
                                      alpha=ALPHA, beta=BETA, etiqueta="BASE")
    if not resolver(mb):
        print("ERROR: el escenario base no encontro solucion optima.")
        return
    costos_base = desglose_costos(datos, xb, yb, zb, True, ALPHA, BETA)
    reportar(datos, xb, yb, zb, costos_base, "ESCENARIO BASE (con aranceles)")
 
    # --- Escenario sin aranceles (pregunta c) ---
    ms, xs, ys, zs = construir_modelo(datos, aplicar_aranceles=False,
                                      alpha=ALPHA, beta=BETA, etiqueta="SIN_ARANCELES")
    if not resolver(ms):
        print("ERROR: el escenario sin aranceles no encontro solucion optima.")
        return
    costos_sin = desglose_costos(datos, xs, ys, zs, False, ALPHA, BETA)
    reportar(datos, xs, ys, zs, costos_sin, "ESCENARIO SIN ARANCELES (pregunta c)")
 
    # --- Comparacion ---
    print("=" * 64)
    print("COMPARACION DE ESCENARIOS")
    print("=" * 64)
    dif = costos_base["TOTAL"] - costos_sin["TOTAL"]
    print(f"  Costo base (con aranceles)     : {costos_base['TOTAL']:,.3f} millones US$")
    print(f"  Costo sin aranceles            : {costos_sin['TOTAL']:,.3f} millones US$")
    print(f"  Diferencia (impacto arancel)   : {dif:,.3f} millones US$")
    print()
    plantas_base = {p for p in datos.plantas if yb[p].X > 0.5}
    plantas_sin  = {p for p in datos.plantas if ys[p].X > 0.5}
    print(f"  Plantas abiertas BASE          : {sorted(plantas_base)}")
    print(f"  Plantas abiertas SIN ARANCELES : {sorted(plantas_sin)}")
    print()
 
    # --- Exportar a Excel ---
    RUTA_RESULTADOS.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(RUTA_RESULTADOS) as w:
        # Resumen de costos comparado
        df_costos = pd.DataFrame({
            "Componente": list(costos_base.keys()),
            "Base_conAranceles": [round(v, 3) for v in costos_base.values()],
            "SinAranceles": [round(costos_sin[k], 3) for k in costos_base.keys()],
        })
        df_costos.to_excel(w, sheet_name="ResumenCostos", index=False)
 
        tabla_estado_plantas(datos, yb, zb).to_excel(w, sheet_name="Plantas_BASE", index=False)
        tabla_produccion(datos, xb).to_excel(w, sheet_name="Produccion_BASE", index=False)
        tabla_flujos(datos, xb).to_excel(w, sheet_name="Flujos_BASE", index=False)
 
        tabla_estado_plantas(datos, ys, zs).to_excel(w, sheet_name="Plantas_SIN", index=False)
        tabla_produccion(datos, xs).to_excel(w, sheet_name="Produccion_SIN", index=False)
        tabla_flujos(datos, xs).to_excel(w, sheet_name="Flujos_SIN", index=False)
 
    print(f"Resultados exportados a: {RUTA_RESULTADOS}")
 
    # --- Generar graficos y documento Word con respuestas ---
    carpeta_res = RAIZ / "resultados"
    rutas_graficos = generar_graficos(datos, xb, costos_base, costos_sin, carpeta_res)
    for r in rutas_graficos:
        print(f"Grafico generado: {r}")
 
    ruta_docx = carpeta_res / "respuestas_seaweedexim.docx"
    generar_word_respuestas(datos, yb, zb, ys, costos_base, costos_sin,
                            rutas_graficos, ruta_docx)
    print(f"Documento de respuestas generado: {ruta_docx}")
 
 
if __name__ == "__main__":
    main()