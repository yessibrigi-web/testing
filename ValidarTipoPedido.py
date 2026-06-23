"""
ValidarTipoPedido.py
=====================================================================
Replica la lógica del SP [ADP_API_PED].[ActualizarCantAdiPedido]
para calcular si un pedido es Presupuestado ('P') o Adicional ('A')
y cuál es su cantidad adicional.

AUTOR ORIGINAL SP: Victor Hugo Tovar — SINCOSOFT S.A.S.
ADAPTACIÓN PYTHON: Proyecto YOM — Automatización de pruebas SINCO ERP

USO COMO MÓDULO DE PRUEBA:
    from ValidarTipoPedido import calcular_tipo_pedidos
    resultado = calcular_tipo_pedidos(conn, [378650, 378633])

USO COMO SCRIPT DIRECTO:
    python ValidarTipoPedido.py

REQUISITO:
    pip install pyodbc
=====================================================================
"""

import pyodbc
from decimal import Decimal, ROUND_HALF_UP
from typing import Union


# ─────────────────────────────────────────────
# CONEXIÓN — ajusta los parámetros de tu entorno
# ─────────────────────────────────────────────
def conectar(server: str = None, database: str = None,
             trusted: bool = True, user: str = None, password: str = None) -> pyodbc.Connection:
    """
    Devuelve una conexión pyodbc al servidor SQL Server de SINCO ERP.
    Por defecto usa Windows Authentication (trusted_connection=yes).
    """
    if server is None:
        server   = input("Servidor SQL (ej: localhost\\SQLEXPRESS): ").strip()
    if database is None:
        database = input("Base de datos (ej: SINCO_OBRA): ").strip()

    if trusted:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server};DATABASE={database};"
            f"Trusted_Connection=yes;"
        )
    else:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server};DATABASE={database};"
            f"UID={user};PWD={password};"
        )
    return pyodbc.connect(conn_str)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _d(val) -> Decimal:
    """Convierte a Decimal, tratando None como 0."""
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def _cfg(cursor, codigo: str) -> int:
    """Lee un valor de ADPconfig. Devuelve 0 si no existe."""
    cursor.execute(
        "SELECT ISNULL((SELECT CnfValor FROM dbo.ADPconfig WHERE CnfCodigo = ?), 0)",
        codigo
    )
    row = cursor.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _calcular_adicional_lista(rows_precal: list) -> Decimal:
    """
    Aplica la misma lógica CASE del SP para calcular [Cantidad Adicional]
    por item y luego el total, devolviendo el @PdsCantAdicional final.

    rows_precal: lista de dicts con las columnas de #TabPreCal.
    """
    # ── Paso 1: calcular adicional por item (solo filas con Solicitada != 0) ──
    adicional_items: list[Decimal] = []
    for r in rows_precal:
        sol   = _d(r["Solicitada"])
        aseg  = _d(r["Ppto_Sol_Ped_Asegurada"])
        consu = _d(r["Ppto_Sol_Ped_Consumida"])

        if sol == 0:
            continue  # el SP excluye filas con Solicitada = 0 para el cálculo por item

        if aseg >= 0 and consu >= 0:
            adi = Decimal("0")
        elif aseg <= 0 and consu >= 0:
            adi = aseg
        elif aseg >= 0 and consu <= 0:
            adi = consu
        else:  # ambas negativas
            adi = consu if (abs(consu) - abs(aseg)) > 0 else aseg

        adicional_items.append(adi)

    adic_x_item = sum(adicional_items, Decimal("0"))

    # ── Paso 2: calcular adicional por total (suma de TODAS las filas) ──
    sum_aseg  = sum(_d(r["Ppto_Sol_Ped_Asegurada"]) for r in rows_precal)
    sum_consu = sum(_d(r["Ppto_Sol_Ped_Consumida"]) for r in rows_precal)

    if sum_aseg >= 0 and sum_consu >= 0:
        adic_x_total = Decimal("0")
    elif sum_aseg <= 0 and sum_consu >= 0:
        adic_x_total = sum_aseg
    elif sum_aseg >= 0 and sum_consu <= 0:
        adic_x_total = sum_consu
    else:
        adic_x_total = sum_consu if (abs(sum_consu) - abs(sum_aseg)) > 0 else sum_aseg

    # ── Paso 3: combinar item vs total ──
    if adic_x_item >= 0 and adic_x_total >= 0:
        pds_cant_adicional = Decimal("0")
    elif adic_x_item <= 0 and adic_x_total >= 0:
        pds_cant_adicional = adic_x_item
    elif adic_x_item >= 0 and adic_x_total <= 0:
        pds_cant_adicional = adic_x_total
    else:
        pds_cant_adicional = adic_x_total if (abs(adic_x_total) - abs(adic_x_item)) > 0 else adic_x_item

    return pds_cant_adicional * Decimal("-1")


# ─────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────
def calcular_tipo_pedidos(
    conn: pyodbc.Connection,
    pds_ids: list[int],
    verbose: bool = True
) -> list[dict]:
    """
    Replica [ADP_API_PED].[ActualizarCantAdiPedido] en Python.

    Para cada PdSID calcula:
      - PdsCantAdicional  : cantidad que excede el presupuesto
      - PdSTipoCant       : 'P' (Presupuestado) o 'A' (Adicional)
      - Resultado         : 'PRESUPUESTADO' | 'ADICIONAL'
      - Detalle           : dict con los valores intermedios

    No modifica la base de datos — solo calcula y devuelve.

    Parámetros
    ----------
    conn     : conexión pyodbc activa
    pds_ids  : lista de IDs de pedido a evaluar
    verbose  : imprime resumen por consola si True

    Devuelve
    --------
    Lista de dicts, uno por pedido.
    """
    if not pds_ids:
        return []

    cursor = conn.cursor()
    resultados = []

    # ── Leer configs globales (una sola vez) ──
    cfg_no_adic   = _cfg(cursor, "AgrInsNoAdicional")
    cfg_adic      = _cfg(cursor, "PedValAgrAdicional")
    cfg_apr_unica = _cfg(cursor, "AgrPedidosAprUnica")

    # ── Cargar datos base de los pedidos ──
    ids_str = ",".join(str(i) for i in pds_ids)
    cursor.execute(f"""
        SELECT PE.PdSID, O.ObrObra, PE.PdSProd, PE.PdSCant
        FROM dbo.PedidosSucursal PE
        INNER JOIN dbo.ADPObras O ON PE.PdSSucursal = O.ObrSucursal
        WHERE PE.PdSID IN ({ids_str})
    """)
    pedidos = {r.PdSID: {"obra": r.ObrObra, "insumo": r.PdSProd, "cant": _d(r.PdSCant)}
               for r in cursor.fetchall()}

    if not pedidos:
        raise ValueError(f"No se encontraron pedidos con IDs: {pds_ids}")

    # ── Procesar cada pedido ──
    for pds_id in pds_ids:
        if pds_id not in pedidos:
            resultados.append({"PdSID": pds_id, "Error": "No encontrado en BD"})
            continue

        p    = pedidos[pds_id]
        obra   = p["obra"]
        insumo = p["insumo"]
        cant   = p["cant"]

        # ── ¿Insumo no adicional por agrupación? ──
        insumo_no_adi = 0
        if cfg_no_adic == 1:
            cursor.execute("""
                SELECT ISNULL(A.AgrNoAdicional, 0)
                FROM dbo.Productos PR
                INNER JOIN dbo.Agrupaciones A ON PR.ProGrupo = A.AgrID
                WHERE PR.ProCod = ?
            """, insumo)
            row = cursor.fetchone()
            insumo_no_adi = int(row[0]) if row else 0

        if insumo_no_adi == 1:
            pds_cant_adicional = Decimal("0")

        else:
            # ── Recopilar datos de ADPControl (clases P, Y, C → Presupuestada y Consumida) ──
            cursor.execute("""
                SELECT ConItem, SUM(ConCP) AS SumCP, SUM(ConCC) AS SumCC
                FROM dbo.ADPControl WITH(NOLOCK)
                WHERE ConClase IN ('P','Y','C')
                  AND ConObra = ? AND ConInsumo = ?
                GROUP BY ConItem
            """, obra, insumo)
            control_pyc = {r.ConItem: {"pres": _d(r.SumCP), "consu": _d(r.SumCC)}
                           for r in cursor.fetchall()}

            # ── ADPControl clase T → Asegurado ──
            cursor.execute("""
                SELECT ConItem, SUM(ConCC) AS SumCC
                FROM dbo.ADPControl WITH(NOLOCK)
                WHERE ConClase = 'T'
                  AND ConObra = ? AND ConInsumo = ?
                GROUP BY ConItem
            """, obra, insumo)
            control_t = {r.ConItem: _d(r.SumCC) for r in cursor.fetchall()}

            # ── Cantidades pedidas del pedido actual (POA) ──
            cursor.execute("""
                SELECT POA.POAItem, POA.POACant
                FROM dbo.PedidosSucursal PS WITH(NOLOCK)
                INNER JOIN dbo.ADPPedidosObraAsignacion POA WITH(NOLOCK) ON PS.PdSID = POA.POAPedido
                INNER JOIN dbo.ADPObras O WITH(NOLOCK) ON PS.PdSSucursal = O.ObrSucursal
                WHERE O.ObrObra = ? AND PS.PdSProd = ? AND PS.PdSID = ?
            """, obra, insumo, pds_id)
            pedido_actual = {}
            for r in cursor.fetchall():
                pedido_actual[r.POAItem] = pedido_actual.get(r.POAItem, Decimal("0")) + _d(r.POACant)

            # ── Cantidades pedidas de OTROS pedidos (estado 0-2, excluye los del batch) ──
            cursor.execute(f"""
                SELECT POAH.POAItem, SUM(POAH.POACant) AS SumPOA
                FROM dbo.PedidosSucursal PSH WITH(NOLOCK)
                INNER JOIN dbo.ADPPedidosObraAsignacion POAH WITH(NOLOCK) ON PSH.PdSID = POAH.POAPedido
                INNER JOIN dbo.ADPObras O WITH(NOLOCK) ON PSH.PdSSucursal = O.ObrSucursal
                WHERE PSH.PdSEstado BETWEEN 0 AND 2
                  AND O.ObrObra = ?
                  AND PSH.PdSID NOT IN ({ids_str})
                  AND PSH.PdSProd = ?
                GROUP BY POAH.POAItem
            """, obra, insumo)
            otros_pedidos = {r.POAItem: _d(r.SumPOA) for r in cursor.fetchall()}

            # ── Comprada (Compras + Movimientos TE/TS) ──
            cursor.execute("""
                SELECT CC.CmCPpDId, SUM(CC.CmCCant) AS SumComp
                FROM dbo.Compras C WITH(NOLOCK)
                INNER JOIN dbo.ComprasDet CD WITH(NOLOCK) ON C.CompID = CD.CompDetCompras
                INNER JOIN dbo.ADPObras O WITH(NOLOCK) ON C.CompSuc = O.ObrSucursal
                INNER JOIN dbo.ADP_ComprasCostos CC WITH(NOLOCK) ON CD.CompDetID = CC.CmCComprasDet
                WHERE O.ObrObra = ? AND CD.CompDetProd = ?
                GROUP BY CC.CmCPpDId
            """, obra, insumo)
            comprada = {r.CmCPpDId: _d(r.SumComp) for r in cursor.fetchall()}

            cursor.execute("""
                SELECT MvIItemADP, SUM(MvISigno * MvICant) AS SumMov
                FROM dbo.MovimientosInv M WITH(NOLOCK)
                INNER JOIN dbo.ADPObras O WITH(NOLOCK) ON M.MvISucursal = O.ObrSucursal
                WHERE O.ObrObra = ? AND M.MvITipo IN ('TE','TS') AND M.MvICod = ?
                GROUP BY MvIItemADP
            """, obra, insumo)
            movimientos = {r.MvIItemADP: _d(r.SumMov) for r in cursor.fetchall()}

            # ── Presupuesto (items del proyecto) ──
            cursor.execute("""
                SELECT PD.PpDId, PD.PpDNoItem
                FROM dbo.ADPPptoDet PD WITH(NOLOCK)
            """)
            # Obtenemos todos los items relevantes juntando las claves de las tablas previas
            todos_items = set(control_pyc.keys()) | set(control_t.keys()) | \
                          set(pedido_actual.keys()) | set(otros_pedidos.keys()) | \
                          set(comprada.keys()) | set(movimientos.keys())

            # ── Construir #TabPreCal en memoria ──
            rows_precal = []
            for item in todos_items:
                presup = control_pyc.get(item, {}).get("pres", Decimal("0"))
                consu  = control_pyc.get(item, {}).get("consu", Decimal("0"))
                aseg   = control_t.get(item, Decimal("0"))
                sol    = pedido_actual.get(item, Decimal("0"))
                pedida = otros_pedidos.get(item, Decimal("0"))
                comp   = comprada.get(item, Decimal("0")) + movimientos.get(item, Decimal("0"))

                cantidad_asegurada = comp + aseg   # Asegurada = Comprada + T

                ppto_aseg  = presup - (sol + pedida + cantidad_asegurada)
                ppto_consu = presup - (sol + pedida + consu)

                # Ajuste: si la diferencia calculada supera la solicitada, se iguala
                if sol != 0 and ppto_aseg < 0:
                    if sol < abs(ppto_aseg):
                        ppto_aseg = -sol
                if sol != 0 and ppto_consu < 0:
                    if sol < abs(ppto_consu):
                        ppto_consu = -sol

                rows_precal.append({
                    "Item": item,
                    "Presupuestada": presup,
                    "Solicitada": sol,
                    "Pedida": pedida,
                    "Consumida": consu,
                    "Asegurada": cantidad_asegurada,
                    "Ppto_Sol_Ped_Asegurada": ppto_aseg,
                    "Ppto_Sol_Ped_Consumida": ppto_consu,
                })

            pds_cant_adicional = _calcular_adicional_lista(rows_precal)

        # ── Ajuste final de PdsCantAdicional (igual que el UPDATE del SP) ──
        if pds_cant_adicional >= cant:
            pds_cant_adicional = cant
        elif pds_cant_adicional <= 0:
            pds_cant_adicional = Decimal("0")

        # ── Determinar PdSTipoCant ──
        tipo = "P" if pds_cant_adicional == 0 else "A"

        # ── Validaciones de configuración de agrupación (mismo orden que el SP) ──
        cursor.execute("""
            SELECT ISNULL(A.AgrReqAprobPed, 0),
                   ISNULL(A.AgrPedidosAprUnica, 0),
                   ISNULL(A.AgrNoAdicional, 0)
            FROM dbo.Productos PR WITH(NOLOCK)
            INNER JOIN dbo.Agrupaciones A WITH(NOLOCK) ON PR.ProGrupo = A.AgrID
            WHERE PR.ProCod = ?
        """, insumo)
        agr = cursor.fetchone()
        agr_req_aprob    = int(agr[0]) if agr else 0
        agr_apr_unica    = int(agr[1]) if agr else 0
        agr_no_adicional = int(agr[2]) if agr else 0

        if cfg_adic == 1 and agr_req_aprob == 1:
            tipo = "A"
        if cfg_apr_unica == 1 and agr_apr_unica == 1:
            tipo = "A"
        if cfg_no_adic == 1:
            tipo = "P" if agr_no_adicional == 1 else "A"

        resultado = {
            "PdSID": pds_id,
            "Obra": obra,
            "Insumo": insumo,
            "CantPedida": float(cant),
            "CantAdicional": float(pds_cant_adicional),
            "TipoCant": tipo,
            "Resultado": "PRESUPUESTADO" if tipo == "P" else "ADICIONAL",
        }
        resultados.append(resultado)

        if verbose:
            print(f"\n── Pedido {pds_id} ──────────────────────")
            print(f"   Obra    : {obra}  |  Insumo : {insumo}")
            print(f"   CantPed : {cant}")
            print(f"   CantAdi : {pds_cant_adicional}")
            print(f"   Tipo    : {tipo}  →  {resultado['Resultado']}")

    cursor.close()
    return resultados


# ─────────────────────────────────────────────
# FUNCIÓN DE PRUEBA — para el template YOM
# ─────────────────────────────────────────────
def ejecutar(pagina=None, frame=None, on_paso=None, conn=None,
             pds_ids: list[int] = None) -> dict:
    """
    Adaptador al template YOM del proyecto Nuevo_Proyecto_YOM.

    Permite ejecutar la validación desde el dashboard sin necesidad
    de un navegador (es una prueba de lógica de negocio pura vía BD).

    Parámetros
    ----------
    pagina, frame : se ignoran (la prueba no usa Playwright)
    on_paso       : callback opcional para reportar pasos al dashboard
    conn          : conexión pyodbc activa (si None, pide credenciales)
    pds_ids       : lista de IDs a validar (si None, pide por consola)

    Devuelve el dict estándar YOM con prueba/estado/dato_entrada/esperado/obtenido
    """
    def paso(msg):
        if on_paso:
            on_paso(msg)
        print(f"  >> {msg}")

    try:
        if conn is None:
            conn = conectar()

        if pds_ids is None:
            raw = input("IDs de pedido a validar (separados por coma): ")
            pds_ids = [int(x.strip()) for x in raw.split(",") if x.strip()]

        paso(f"Validando {len(pds_ids)} pedido(s): {pds_ids}")
        resultados = calcular_tipo_pedidos(conn, pds_ids, verbose=False)

        # Buscar si algún pedido que debería ser presupuestado quedó como adicional
        fallidos = [r for r in resultados if r.get("TipoCant") == "A"]
        pasados  = [r for r in resultados if r.get("TipoCant") == "P"]

        for r in resultados:
            paso(f"Pedido {r['PdSID']} → {r['Resultado']}  (CantAdi={r['CantAdicional']})")

        if not fallidos:
            estado = "PASS"
            obtenido = f"Todos los pedidos presupuestados correctamente: {[r['PdSID'] for r in pasados]}"
        else:
            estado = "FAIL"
            obtenido = f"Pedidos marcados como ADICIONAL: {[r['PdSID'] for r in fallidos]}"

        return {
            "prueba": "Validación tipo pedido (Presupuestado vs Adicional)",
            "estado": estado,
            "dato_entrada": f"PdSIDs: {pds_ids}",
            "esperado": "Todos los pedidos con TipoCant = 'P' (Presupuestado)",
            "obtenido": obtenido,
        }

    except Exception as e:
        return {
            "prueba": "Validación tipo pedido (Presupuestado vs Adicional)",
            "estado": "ERROR",
            "dato_entrada": str(pds_ids),
            "esperado": "TipoCant = 'P' para todos",
            "obtenido": str(e),
        }


# ─────────────────────────────────────────────
# EJECUCIÓN DIRECTA
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  Validador de tipo de pedido — SINCO ADPRO")
    print("  Replica: [ADP_API_PED].[ActualizarCantAdiPedido]")
    print("=" * 55)

    try:
        conexion = conectar()
        raw_ids  = input("\nIngresa los PdSIDs a validar (separados por coma): ")
        ids      = [int(x.strip()) for x in raw_ids.split(",") if x.strip()]

        resultados = calcular_tipo_pedidos(conexion, ids, verbose=True)

        print("\n" + "=" * 55)
        print("  RESUMEN FINAL")
        print("=" * 55)
        for r in resultados:
            estado_icon = "✔" if r["Resultado"] == "PRESUPUESTADO" else "✘"
            print(f"  {estado_icon}  Pedido {r['PdSID']:>8}  →  {r['Resultado']}"
                  f"  (Cant. Adicional: {r['CantAdicional']})")

        conexion.close()

    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")
    except Exception as ex:
        print(f"\nERROR: {ex}")
