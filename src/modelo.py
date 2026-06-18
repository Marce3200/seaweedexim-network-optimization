# -*- coding: utf-8 -*-
"""
modelo.py
---------
PASO 3: formulacion del modelo de optimizacion en Gurobi para el diseno
optimo de la red de produccion/distribucion de Seaweedexim Company (2026).

El modelo es un problema de localizacion de capacidad (capacitated facility
location) con decisiones jerarquicas de apertura/cierre:

  CONJUNTOS
    P : plantas        (Chile, Espana, China, Corea, Japon, Mexico)
    M : mercados       (America Latina, Europa, Asia 01, Asia 02, Japon, America del Norte)
    K : productos      (Fertilexum, Beautylexquim, Healthmixerium)

  VARIABLES DE DECISION
    x[p,k,m] >= 0  (continua) : millones de kg del producto k producidos en la
                                planta p y enviados al mercado m.
    y[p] in {0,1}             : 1 si la planta p opera, 0 si se cierra.
    z[p,k] in {0,1}           : 1 si la linea del producto k esta abierta en la planta p.

  PARAMETROS PRINCIPALES
    alpha : fraccion del costo fijo de planta que se AHORRA al cerrarla   (0.40)
    beta  : fraccion del costo fijo de producto que se AHORRA al cerrar la linea (0.20)
    => si se cierra, se sigue pagando (1-alpha) o (1-beta) del costo fijo.

  FUNCION OBJETIVO (minimizar costo total anual, en millones US$)
    + costo fijo de plantas      : CF_p * [ (1-alpha) + alpha * y[p] ]
    + costo fijo de productos     : CF_pk * [ (1-beta) + beta * z[p,k] ]
    + costo variable de produccion: cvar[p,k] * x[p,k,m]
    + costo de transporte         : transp[p,m] * x[p,k,m]
    + aranceles (solo en destino)  : arancel[m] * (cvar[p,k] + transp[p,m]) * x[p,k,m]
                                     aplicado solo si aplica_arancel[p,m] == 1
                                     (los flujos locales estan exentos)

  RESTRICCIONES
    (R1) Demanda    : la produccion enviada a cada mercado iguala su demanda.
    (R2) Capacidad  : la produccion total de una planta no supera su capacidad (si opera).
    (R3) Linea-flujo: solo se puede producir un producto si su linea esta abierta.
    (R4) Jerarquia  : una linea solo puede abrirse si la planta opera (z <= y).
"""

import gurobipy as gp
from gurobipy import GRB


def construir_modelo(datos, aplicar_aranceles=True, alpha=0.40, beta=0.20, etiqueta="modelo"):
    """
    Construye y devuelve el modelo de Gurobi (sin resolver todavia).

    Parametros
    ----------
    datos : objeto Datos (de cargar_datos.py) con todos los parametros.
    aplicar_aranceles : bool. True = escenario base; False = escenario pregunta c).
    alpha : float. Ahorro al cerrar una planta completa (default 0.40).
    beta  : float. Ahorro al cerrar la linea de un producto (default 0.20).
    etiqueta : str. Nombre del modelo (util para distinguir escenarios).

    Retorna
    -------
    (modelo, x, y, z) : el modelo Gurobi y sus diccionarios de variables.
    """
    P = datos.plantas
    M = datos.mercados
    K = datos.productos

    m = gp.Model(f"Seaweedexim_{etiqueta}")
    m.Params.OutputFlag = 0   # silencioso. Cambiar a 1 para ver el log del solver.

    # ------------------------------------------------------------------
    # VARIABLES DE DECISION
    # ------------------------------------------------------------------
    # x[p,k,mk] : flujo (millones kg) de producto k desde planta p al mercado mk
    x = m.addVars(P, K, M, lb=0.0, name="x")
    # y[p] : 1 si la planta opera
    y = m.addVars(P, vtype=GRB.BINARY, name="y")
    # z[p,k] : 1 si la linea del producto k esta abierta en la planta p
    z = m.addVars(P, K, vtype=GRB.BINARY, name="z")

    # ------------------------------------------------------------------
    # FUNCION OBJETIVO
    # ------------------------------------------------------------------
    # (1) Costo fijo de plantas.
    #     Si y=1 (opera): paga el 100% del costo fijo.
    #     Si y=0 (cierra): paga (1-alpha), es decir, ahorra alpha.
    #     Forma lineal: CF*(1-alpha) + CF*alpha*y  ->  CF cuando y=1, CF*(1-alpha) cuando y=0.
    costo_fijo_planta = gp.quicksum(
        datos.cf_planta[p] * ((1 - alpha) + alpha * y[p])
        for p in P
    )

    # (2) Costo fijo de productos (lineas), analogo con beta y z[p,k].
    costo_fijo_producto = gp.quicksum(
        datos.cf_producto[p][k] * ((1 - beta) + beta * z[p, k])
        for p in P for k in K
    )

    # (3) Costo variable de produccion (materia prima + produccion), en millones US$.
    #     cvar esta en US$/kg y x en millones de kg -> el producto da millones de US$.
    costo_variable = gp.quicksum(
        datos.cvar[p][k] * x[p, k, mk]
        for p in P for k in K for mk in M
    )

    # (4) Costo de transporte.
    costo_transporte = gp.quicksum(
        datos.transporte[p][mk] * x[p, k, mk]
        for p in P for k in K for mk in M
    )

    # (5) Aranceles: aplican en destino sobre (costo variable + transporte),
    #     solo cuando aplica_arancel[(p,mk)] == 1 (flujos no locales).
    if aplicar_aranceles:
        costo_arancel = gp.quicksum(
            datos.arancel[mk] * (datos.cvar[p][k] + datos.transporte[p][mk]) * x[p, k, mk]
            for p in P for k in K for mk in M
            if datos.aplica_arancel[(p, mk)] == 1
        )
    else:
        costo_arancel = 0.0

    m.setObjective(
        costo_fijo_planta + costo_fijo_producto
        + costo_variable + costo_transporte + costo_arancel,
        GRB.MINIMIZE
    )

    # ------------------------------------------------------------------
    # RESTRICCIONES
    # ------------------------------------------------------------------
    # (R1) Satisfacer exactamente la demanda de cada producto en cada mercado.
    for mk in M:
        for k in K:
            m.addConstr(
                gp.quicksum(x[p, k, mk] for p in P) == datos.demanda[mk][k],
                name=f"demanda[{k},{mk}]"
            )

    # (R2) Capacidad: la produccion total de la planta no supera su capacidad,
    #      y si la planta esta cerrada (y=0) no puede producir nada.
    for p in P:
        m.addConstr(
            gp.quicksum(x[p, k, mk] for k in K for mk in M) <= datos.capacidad[p] * y[p],
            name=f"capacidad[{p}]"
        )

    # (R3) Vinculo linea-flujo: solo se produce un producto si su linea esta abierta.
    #      La capacidad de la planta sirve como cota superior natural (Big-M).
    for p in P:
        for k in K:
            m.addConstr(
                gp.quicksum(x[p, k, mk] for mk in M) <= datos.capacidad[p] * z[p, k],
                name=f"linea[{p},{k}]"
            )

    # (R4) Jerarquia: una linea solo puede estar abierta si la planta opera.
    for p in P:
        for k in K:
            m.addConstr(z[p, k] <= y[p], name=f"jerarquia[{p},{k}]")

    return m, x, y, z


def resolver(modelo):
    """Optimiza el modelo y devuelve True si encontro solucion optima."""
    modelo.optimize()
    return modelo.Status == GRB.OPTIMAL


# Bloque de prueba: corre el modelo en el escenario base usando los datos reales.
if __name__ == "__main__":
    from cargar_datos import cargar_datos

    datos = cargar_datos()
    modelo, x, y, z = construir_modelo(datos, aplicar_aranceles=True,
                                       alpha=0.40, beta=0.20, etiqueta="BASE")
    ok = resolver(modelo)

    print("=" * 60)
    print("PRUEBA DEL MODELO - ESCENARIO BASE (con aranceles)")
    print("=" * 60)
    if ok:
        print(f"Estado: OPTIMO")
        print(f"Costo total optimo: {modelo.ObjVal:,.3f} millones US$")
        print()
        print("Plantas abiertas/cerradas:")
        for p in datos.plantas:
            estado = "ABIERTA" if y[p].X > 0.5 else "CERRADA"
            print(f"  {p:8s}: {estado}")
    else:
        print(f"El modelo no encontro solucion optima. Estado: {modelo.Status}")