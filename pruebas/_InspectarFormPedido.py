"""
Prueba: _Inspeccionar Formulario Pedido
Módulo: Diagnóstico
Navega a Pedidos proyecto, abre nuevo pedido y captura el DOM del frame
para identificar los IDs exactos de los campos (obra, insumo, cantidad).
NO modifica nada — solo lee.
"""


def ejecutar(pagina, frame, on_paso=None) -> dict:

    def paso(msg):
        if on_paso:
            on_paso(msg)

    # ── Navegación ────────────────────────────────────────────────────────────
    paso("Navegando a ADPRO")
    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)
    pagina.wait_for_timeout(1000)

    for ruta in [
        "ADPRO/Almacén",
        "ADPRO/Almacén/PEDIDOS",
        "ADPRO/Almacén/PEDIDOS/Pedidos proyecto",
    ]:
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

    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(2000)
    paso("En Pedidos proyecto")

    fr = pagina.locator("#pagina1").content_frame

    # ── Abrir nuevo pedido ────────────────────────────────────────────────────
    btn_encontrado = None
    for nombre in ("Nuevo pedido", "Nuevo", "Agregar", "New"):
        try:
            loc = fr.get_by_role("button", name=nombre)
            loc.wait_for(state="visible", timeout=4000)
            btn_encontrado = nombre
            loc.click(force=True)
            break
        except Exception:
            pass

    pagina.wait_for_timeout(2500)
    paso(f"Botón usado: {btn_encontrado or 'NO ENCONTRADO'}")

    # ── Capturar DOM del frame ────────────────────────────────────────────────
    dom_inputs = fr.evaluate("""
        () => {
            const inputs = document.querySelectorAll('input, select, textarea, [role="combobox"], [role="spinbutton"]');
            const resultado = [];
            for (const el of inputs) {
                resultado.push({
                    tag:         el.tagName,
                    id:          el.id || '',
                    name:        el.name || '',
                    type:        el.type || '',
                    role:        el.getAttribute('role') || '',
                    ariaLabel:   el.getAttribute('aria-label') || '',
                    placeholder: el.placeholder || '',
                    value:       el.value || '',
                    readonly:    el.readOnly || false,
                    visible:     el.offsetParent !== null,
                });
            }
            return resultado;
        }
    """)

    dom_botones = fr.evaluate("""
        () => {
            const btns = document.querySelectorAll('button, [role="button"]');
            const resultado = [];
            for (const b of btns) {
                if (b.offsetParent !== null) {
                    resultado.push({
                        tag:       b.tagName,
                        id:        b.id || '',
                        text:      (b.innerText || b.textContent || '').trim().slice(0, 60),
                        ariaLabel: b.getAttribute('aria-label') || '',
                        visible:   true,
                    });
                }
            }
            return resultado;
        }
    """)

    # ── Formatear resultado legible ───────────────────────────────────────────
    lineas_inputs = []
    for el in (dom_inputs or []):
        if not el.get("visible"):
            continue
        identificador = el.get("id") or el.get("name") or el.get("ariaLabel") or el.get("placeholder") or "(sin id)"
        lineas_inputs.append(
            f"  [{el.get('tag')}] id='{el.get('id')}' name='{el.get('name')}' "
            f"type='{el.get('type')}' role='{el.get('role')}' "
            f"aria-label='{el.get('ariaLabel')}' placeholder='{el.get('placeholder')}' "
            f"value='{el.get('value')}' readonly={el.get('readonly')}"
        )

    lineas_botones = []
    for b in (dom_botones or []):
        lineas_botones.append(
            f"  [{b.get('tag')}] id='{b.get('id')}' text='{b.get('text')}' aria-label='{b.get('ariaLabel')}'"
        )

    resumen = (
        f"=== INPUTS ({len(lineas_inputs)}) ===\n"
        + "\n".join(lineas_inputs[:60])
        + f"\n\n=== BOTONES VISIBLES ({len(lineas_botones)}) ===\n"
        + "\n".join(lineas_botones[:30])
    )

    paso("DOM capturado — copia el resultado de 'obtenido'")

    return {
        "prueba":       "_Inspeccionar Formulario Pedido",
        "estado":       "ok",
        "dato_entrada": f"Botón nuevo usado: {btn_encontrado or 'ninguno'}",
        "esperado":     "Lista de campos del formulario",
        "obtenido":     resumen,
    }
