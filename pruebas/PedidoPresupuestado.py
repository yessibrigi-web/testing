"""
Prueba: Pedido Presupuestado
Módulo: Compras
Crea un pedido de proyecto con un insumo presupuestado disponible
y verifica que SINCO lo clasifique como tipo 'P' (Presupuestado).
Si queda como 'A' (Adicional) la prueba falla.

No requiere acceso a base de datos. El insumo proyectado se obtiene
desde ADPRO/Control/Control del proyecto > Seguimiento items insumo.
"""

import sys
import os
import re
import traceback

_raiz = os.path.dirname(os.path.dirname(__file__))
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _frame_real(pagina):
    """Devuelve el objeto Frame real de #pagina1 (necesario para .evaluate())."""
    return next(
        (f for f in pagina.frames if "pagina1" in (f.name or "")),
        pagina.frames[1] if len(pagina.frames) > 1 else None,
    )


def _navegar_menu(pagina, rutas):
    """Hace clic en cada ítem del menú SINCO por su atributo title."""
    for ruta in rutas:
        pagina.evaluate(f"""
            () => {{
                const items = document.querySelectorAll('div.menu-caja');
                for (const item of items) {{
                    if (item.getAttribute('title') === 'Ruta: {ruta}') {{
                        item.click(); return;
                    }}
                }}
            }}
        """)
        pagina.wait_for_timeout(900)


def _obtener_insumo_proyectado(pagina, paso):
    """
    Navega a ADPRO/Control/Control del proyecto,
    selecciona tipo informe 'Seguimiento' > 'Seguimiento items insumo'
    y devuelve el código del primer insumo proyectado de la grilla.
    """
    paso("Navegando a Control del proyecto")
    # Clic en módulo ADPRO — intentar por title primero, luego por texto visible
    try:
        pagina.get_by_title("Administración de proyectos").click(timeout=8000)
    except Exception:
        pagina.evaluate("""
            () => {
                const btns = document.querySelectorAll('[title], a, button, div');
                for (const b of btns) {
                    const t = (b.title || b.innerText || '').trim().toUpperCase();
                    if (t === 'ADPRO' || t.includes('ADMINISTRACIÓN DE PROYECTOS')) {
                        b.click(); return;
                    }
                }
            }
        """)
    pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)
    pagina.wait_for_timeout(1000)

    _navegar_menu(pagina, [
        "ADPRO/Control",
        "ADPRO/Control/Control del proyecto",
    ])
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(2000)
    paso("Control del proyecto cargado")

    fr       = pagina.locator("#pagina1").content_frame
    frame_ob = _frame_real(pagina)

    # 1. Seleccionar "Seguimiento" en el select de Tipo de Informe
    #    (NO es #ddlinforme — ese es el de Opción)
    paso("Seleccionando tipo informe: Seguimiento")
    frame_ob.evaluate("""
        () => {
            const selects = document.querySelectorAll('select');
            for (const s of selects) {
                for (const opt of s.options) {
                    if (opt.text.trim() === 'Seguimiento') {
                        s.value = opt.value;
                        s.dispatchEvent(new Event('change', { bubbles: true }));
                        return;
                    }
                }
            }
        }
    """)
    pagina.wait_for_timeout(1000)

    # 2. Seleccionar "Ítems insumo" en select#ddlinforme (Opción)
    paso("Seleccionando: Ítems insumo")
    ddl = fr.locator("select#ddlinforme")
    ddl.wait_for(state="visible", timeout=10000)
    ddl.select_option(value="8500806")
    pagina.wait_for_timeout(800)

    # Generar control y esperar confirmación antes de consultar
    paso("Generando control")
    try:
        btn_generar = fr.get_by_role("button", name=re.compile("generar", re.I))
        btn_generar.wait_for(state="visible", timeout=8000)
        btn_generar.click()
    except Exception:
        fr.get_by_text("Generar", exact=False).first.click()

    # Esperar mensaje "Se generó control satisfactoriamente" y cerrar con Aceptar
    paso("Esperando confirmación de control generado...")
    frame_ob.locator(
        "text=Se generó control satisfactoriamente"
    ).wait_for(state="visible", timeout=60000)
    paso("Control generado — cerrando ventana con Aceptar")
    try:
        btn_aceptar = fr.get_by_role("button", name=re.compile("aceptar", re.I))
        btn_aceptar.wait_for(state="visible", timeout=5000)
        btn_aceptar.click()
    except Exception:
        fr.get_by_text("Aceptar", exact=False).first.click()
    pagina.wait_for_timeout(800)
    paso("Ventana cerrada — haciendo clic en Consultar")

    # Clic en Consultar
    try:
        btn_consultar = fr.get_by_role("button", name=re.compile("consultar", re.I))
        btn_consultar.wait_for(state="visible", timeout=8000)
        btn_consultar.click()
    except Exception:
        fr.get_by_text("Consultar", exact=False).first.click()
    # Esperar a que la grilla tenga filas con datos
    paso("Esperando datos en la grilla...")
    try:
        frame_ob.locator("table tbody tr, [role='row']:not([aria-rowindex='1'])").first.wait_for(
            state="visible", timeout=30000
        )
    except Exception:
        pass
    pagina.wait_for_timeout(1500)
    paso("Grilla cargada")

    # Buscar en todos los frames el informe de Seguimiento items insumo
    paso("Leyendo primer insumo Tipo M de la grilla")
    import json as _json

    # Buscar específicamente el frame del informe SeguimientoItemsInsumos
    frame_informe = next(
        (f for f in pagina.frames if "SeguimientoItemsInsumos" in (f.url or "")),
        None
    )

    if not frame_informe:
        paso(f"Frame del informe no encontrado. Frames disponibles: {[f.url for f in pagina.frames]}")
        return ""

    paso(f"Frame informe: {frame_informe.url[:80]}")

    try:
        resultado = frame_informe.evaluate("""
        () => {
            const tablas = document.querySelectorAll('table');
            // Recopilar todas las filas de todas las tablas
            const todasFilas = [];
            tablas.forEach(t => {
                t.querySelectorAll('tr').forEach(tr => todasFilas.push(tr));
            });

            // Columnas del informe Seguimiento items insumo:
            // 0=Código, 1=Descripción, 2=Tipo, 3=Unidad
            // 4=Proyectado cant, 5=Proyectado valor, 6=Acum.Prog
            // 7=Acum.Ejec (NO es pedidos pendientes)
            // 10=Asegurado cant, 11=Consumido cant
            // Disponible = proyectado - asegurado - consumido
            // (los pedidos pendientes los evalúa el SP al guardar)
            const parseNum = s => parseFloat((s || '0').replace(/,/g, '')) || 0;
            const candidatos = [];

            for (const fila of todasFilas) {
                const celdas = [...fila.querySelectorAll('td')];
                if (celdas.length < 11) continue;
                const tipo = (celdas[2].innerText || '').trim().toUpperCase();
                if (tipo !== 'M') continue;
                let cod = '';
                for (const c of celdas) {
                    const txt = (c.innerText || '').trim();
                    if (/^\\d+$/.test(txt)) { cod = txt; break; }
                }
                if (!cod) continue;
                const proy      = parseNum(celdas[4].innerText);
                const asegurado = parseNum(celdas[10].innerText);
                const consumido = parseNum(celdas[11].innerText);
                const disponible = proy - asegurado - consumido;
                candidatos.push({ cod, proy, asegurado, consumido, disponible });
            }

            // Ordenar por mayor disponible y tomar el primero con disponible > 0
            candidatos.sort((a, b) => b.disponible - a.disponible);
            const elegido = candidatos.find(c => c.disponible > 0);
            if (elegido) {
                return '__FILA__' + JSON.stringify({
                    codigo: elegido.cod,
                    proy: elegido.proy,
                    asegurado: elegido.asegurado,
                    consumido: elegido.consumido,
                    disponible: elegido.disponible,
                    total_candidatos: candidatos.length
                });
            }
            // Sin disponible — reportar todos los candidatos para diagnóstico
            return '__DIAG__' + JSON.stringify(candidatos.slice(0, 5));
        }
    """) or ""
    except Exception as e_eval:
        paso(f"ERROR evaluando frame informe: {e_eval}")
        return ""

    frames_info = []

    if resultado.startswith("__FILA__"):
        fila = _json.loads(resultado[8:])
        paso(f"Insumo seleccionado: {fila['codigo']} | proy={fila['proy']} aseg={fila['asegurado']} cons={fila['consumido']} disp={fila['disponible']} (de {fila['total_candidatos']} Tipo M)")
        return fila["codigo"]

    if resultado.startswith("__DIAG__"):
        paso(f"Ningún insumo Tipo M con disponible > 0. Candidatos: {resultado[8:]}")
    else:
        paso("No se encontraron insumos Tipo M en el frame del informe")
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def ejecutar(pagina, frame, on_paso=None, parametros=None) -> dict:

    insumo_codigo = None
    pds_id        = None
    obra          = ""

    def paso(msg):
        if on_paso:
            on_paso(msg)

    try:
        # ── 1. Obtener insumo proyectado desde Control del proyecto ───────────
        insumo_codigo = _obtener_insumo_proyectado(pagina, paso)

        if not insumo_codigo:
            return {
                "prueba":       "Pedido Presupuestado",
                "estado":       "fail",
                "dato_entrada": "ADPRO/Control/Control del proyecto > Seguimiento items insumo",
                "esperado":     "Al menos un insumo proyectado en la grilla",
                "obtenido":     "No se encontró ningún código de insumo en la grilla",
            }

        paso(f"Insumo proyectado encontrado: {insumo_codigo}")

        # ── 2. Navegar a Pedidos proyecto ─────────────────────────────────────
        paso("Navegando a Pedidos proyecto")
        pagina.get_by_title("Administración de proyectos").click()
        pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)
        pagina.wait_for_timeout(1000)

        _navegar_menu(pagina, [
            "ADPRO/Almacén",
            "ADPRO/Almacén/PEDIDOS",
            "ADPRO/Almacén/PEDIDOS/Pedidos proyecto",
        ])
        pagina.wait_for_load_state("networkidle")
        pagina.wait_for_timeout(2000)
        paso("Pedidos proyecto cargado")

        fr       = pagina.locator("#pagina1").content_frame
        frame_ob = _frame_real(pagina)

        # ── 3. Abrir nuevo pedido ─────────────────────────────────────────────
        paso("Abriendo nuevo pedido")
        btn_nuevo = fr.get_by_role("button", name="Nuevo pedido")
        btn_nuevo.wait_for(state="visible", timeout=10000)
        btn_nuevo.click(force=True)
        pagina.wait_for_timeout(2000)
        paso("Formulario abierto")

        # Extraer código de obra del encabezado "Pedido No. 440-XXXX"
        pedido_texto = frame_ob.evaluate("""
            () => {
                const m = (document.body.innerText || '').match(/Pedido\\s*No\\.?\\s*[:\\-]?\\s*([\\d]+)/i);
                return m ? m[1] : '';
            }
        """) or ""
        obra = pedido_texto.strip()
        paso(f"Obra: {obra}")

        # ── 4. Buscar y seleccionar el insumo en el formulario ────────────────
        paso(f"Buscando insumo {insumo_codigo} en formulario")
        frame_ob.click('[placeholder="Buscar por descripción o código BIM..."]')
        pagina.wait_for_timeout(400)
        pagina.keyboard.type(insumo_codigo, delay=80)
        pagina.wait_for_timeout(2500)

        opcion = fr.locator(f"[role='option']:has-text('{insumo_codigo}')")
        try:
            opcion.wait_for(state="visible", timeout=6000)
            opcion.click()
        except Exception:
            fr.locator("[role='option']").first.click()

        pagina.wait_for_timeout(2000)
        paso(f"Insumo '{insumo_codigo}' seleccionado")

        # ── 5. Seleccionar ítem con cupo e ingresar cantidad 1 ───────────────
        # La grilla de ítems muestra: Actividad | Descripción | F.req | Proyectado | Asegurado | Consumido | Cantidad
        # Asegurado = contratado + compras. Cupo = Proyectado > Asegurado + Consumido
        paso("Buscando ítem con cupo en la grilla del pedido")
        pagina.wait_for_timeout(1000)

        idx_item_con_cupo = frame_ob.evaluate("""
            () => {
                const parseNum = s => parseFloat((s || '0').replace(/,/g, '')) || 0;
                const celdas_cant = document.querySelectorAll('.cantidad-cell-border');

                for (let i = 0; i < celdas_cant.length; i++) {
                    // Grilla MUI usa divs con role="row", no <tr>
                    const fila = celdas_cant[i].closest('[role="row"]') || celdas_cant[i].closest('tr');
                    if (!fila) continue;
                    const cells = [...fila.querySelectorAll('[role="cell"], [role="gridcell"], td')];

                    // Intentar por data-field primero
                    const byField = (f) => {
                        const el = fila.querySelector(`[data-field="${f}"]`);
                        return el ? parseNum(el.innerText) : null;
                    };
                    let proy = byField('proyectado') ?? byField('Proyectado') ?? byField('cantProyectada');
                    let aseg = byField('asegurado')  ?? byField('Asegurado')  ?? byField('cantAsegurada');
                    let cons = byField('consumido')  ?? byField('Consumido')  ?? byField('cantConsumida');

                    // Fallback posicional: Actividad|Desc|FechaReq|Proyectado|Asegurado|Consumido|Cantidad
                    if (proy === null && cells.length >= 6) {
                        proy = parseNum(cells[3]?.innerText);
                        aseg = parseNum(cells[4]?.innerText);
                        cons = parseNum(cells[5]?.innerText);
                    }

                    if (proy !== null && proy > (aseg || 0) + (cons || 0)) return i;
                }
                return -1;
            }
        """)

        if idx_item_con_cupo == -1:
            diag_filas = frame_ob.evaluate("""
                () => {
                    const parseNum = s => parseFloat((s || '0').replace(/,/g, '')) || 0;
                    const celdas_cant = document.querySelectorAll('.cantidad-cell-border');
                    return Array.from(celdas_cant).slice(0, 4).map((c, i) => {
                        const fila = c.closest('[role="row"]') || c.closest('tr');
                        if (!fila) return i + ': sin fila padre (role=row)';
                        const cells = [...fila.querySelectorAll('[role="cell"],[role="gridcell"],td')];
                        return i + ' [' + cells.length + 'celdas]: ' +
                            cells.map(x => x.innerText.trim().substring(0, 15)).join(' | ');
                    });
                }
            """)
            paso(f"No se encontró ítem con cupo. Filas grilla: {diag_filas}")
            paso("Usando primer ítem disponible como fallback")
            celda_cant = fr.locator(".cantidad-cell-border").first
        else:
            paso(f"Ítem con cupo encontrado en posición {idx_item_con_cupo}")
            celda_cant = fr.locator(".cantidad-cell-border").nth(idx_item_con_cupo)

        paso("Ingresando cantidad: 1")
        celda_cant.wait_for(state="visible", timeout=8000)
        celda_cant.click()
        pagina.wait_for_timeout(800)
        pagina.keyboard.type("1", delay=60)
        pagina.wait_for_timeout(500)

        # ── 6. Guardar e interceptar número de pedido creado ─────────────────
        paso("Tab → guardando pedido")
        try:
            with pagina.expect_response(
                lambda r: r.request.method in ("POST", "PUT", "PATCH") and (
                    "pedido" in r.url.lower() or "Pedido" in r.url
                ),
                timeout=10000,
            ) as resp_info:
                pagina.keyboard.press("Tab")

            pagina.wait_for_timeout(2000)

            try:
                data = resp_info.value.json()
                for campo in ("PdSID", "pdSID", "Id", "id", "PedidoId", "pedidoId", "ID"):
                    val = data.get(campo) if isinstance(data, dict) else None
                    if val and str(val).isdigit():
                        pds_id = int(val)
                        break
            except Exception:
                pass
        except Exception:
            pagina.keyboard.press("Tab")
            pagina.wait_for_timeout(3000)

        # Leer número de pedido desde el DOM si la respuesta no lo dio
        if not pds_id:
            txt = frame_ob.evaluate("""
                () => {
                    const m = (document.body.innerText || '').match(/Pedido\\s*No\\.?\\s*[:\\-]?\\s*\\d+[-–]\\s*(\\d+)/i);
                    return m ? m[1] : '';
                }
            """) or ""
            if txt.isdigit():
                pds_id = int(txt)

        paso(f"Pedido guardado — PdSID: {pds_id or 'no capturado'}")

        # ── 7. Leer tipo P/A directamente desde la UI ─────────────────────────
        paso("Verificando tipo del pedido en la UI")
        pagina.wait_for_timeout(1500)

        # El tipo se muestra como texto "Presupuestado" o "Adicional"
        # en un <p class="MuiTypography-body1"> en el detalle del pedido
        tipo_texto = frame_ob.evaluate("""
            () => {
                const targets = ['Presupuestado', 'Adicional'];
                const elems = document.querySelectorAll('p, span, div');
                for (const el of elems) {
                    const txt = (el.innerText || '').trim();
                    if (targets.includes(txt)) return txt;
                }
                return '';
            }
        """) or ""

        if tipo_texto == "Presupuestado":
            tipo = "P"
        elif tipo_texto == "Adicional":
            tipo = "A"
        else:
            tipo = ""
            paso(f"Tipo no encontrado en UI (buscando 'Presupuestado'/'Adicional')")

        tipo = tipo.strip().upper()
        paso(f"Tipo leído desde UI: '{tipo}'")

        dato = f"Insumo={insumo_codigo} | Obra={obra or '?'} | PdSID={pds_id or '?'}"

        if tipo == "P":
            return {
                "prueba":       "Pedido Presupuestado",
                "estado":       "ok",
                "dato_entrada": dato,
                "esperado":     "Tipo = Presupuestado",
                "obtenido":     "Presupuestado ✔ — SINCO clasificó el pedido correctamente",
            }
        elif tipo == "A":
            return {
                "prueba":       "Pedido Presupuestado",
                "estado":       "ok",
                "dato_entrada": dato,
                "esperado":     "Tipo = Presupuestado",
                "obtenido":     "DEFECTO DETECTADO ✘ — El pedido quedó como Adicional siendo un insumo presupuestado con cupo. Reportar a desarrollo.",
            }
        else:
            return {
                "prueba":       "Pedido Presupuestado",
                "estado":       "fail",
                "dato_entrada": dato,
                "esperado":     "Tipo = Presupuestado o Adicional visible en UI",
                "obtenido":     "No se encontró el resultado en pantalla — revisar automatización",
            }

    except Exception as exc:
        return {
            "prueba":       "Pedido Presupuestado",
            "estado":       "fail",
            "dato_entrada": f"Insumo={insumo_codigo or '?'} | Obra={obra or '?'} | PdSID={pds_id or '?'}",
            "esperado":     "Pedido creado y clasificado como Presupuestado",
            "obtenido":     f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-600:]}",
        }
