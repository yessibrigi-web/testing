"""
Prueba: Inspeccionar Formulario Pedido
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

    # FrameLocator: para interacciones de elementos (click, fill, etc.)
    fr = pagina.locator("#pagina1").content_frame

    # Frame real: necesario para .evaluate()
    frame_obj = next(
        (f for f in pagina.frames if "pagina1" in (f.name or "")),
        pagina.frames[1] if len(pagina.frames) > 1 else None,
    )

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

    # ── Escribir en buscador con teclado (DevExtreme no acepta fill) ──────────
    dropdown_html = ""
    try:
        # Usar el id directo sobre el Frame real para asegurar foco
        frame_obj.click("#_r_9_")
        pagina.wait_for_timeout(500)
        pagina.keyboard.type("A", delay=80)   # teclado real, carácter a carácter
        pagina.wait_for_timeout(3000)
        paso("Texto 'A' escrito con teclado")

        # Capturar estructura del dropdown
        dropdown_html = frame_obj.evaluate("""
            () => {
                const candidatos = [
                    ...document.querySelectorAll(
                        'ul li, [role="listbox"], [role="option"], ' +
                        '.dx-list-item, .dx-item, .dx-dropdowneditor-overlay *'
                    )
                ];
                return candidatos
                    .filter(el => el.offsetParent !== null)
                    .slice(0, 30)
                    .map(el =>
                        `[${el.tagName}] class='${el.className}' ` +
                        `role='${el.getAttribute("role") || ""}' ` +
                        `text='${(el.innerText || "").trim().slice(0, 80)}'`
                    )
                    .join("\\n");
            }
        """)
        paso(f"Dropdown: {len(dropdown_html)} chars")

        # Clic en la primera opción MUI
        primera_opcion = fr.locator("[role='option']").first
        primera_opcion.wait_for(state="visible", timeout=5000)
        texto_opcion = primera_opcion.inner_text()
        primera_opcion.click()
        pagina.wait_for_timeout(2000)
        paso(f"Opción seleccionada: {texto_opcion[:60]}")

        # Ahora aparece una fila con "Cant. pedida" — hacer clic en ella
        fila_insumo = fr.locator("button:has-text('Cant. pedida')").first
        fila_insumo.wait_for(state="visible", timeout=5000)
        fila_insumo.click()
        pagina.wait_for_timeout(3000)
        paso("Clic en fila insumo (Cant. pedida)")

    except Exception as e:
        paso(f"Error búsqueda: {e}")

    # ── Capturar DOM del frame ────────────────────────────────────────────────
    dom_inputs = frame_obj.evaluate("""
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

    dom_botones = frame_obj.evaluate("""
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

    # ── Capturar celda Cantidad y PedidoNo ───────────────────────────────────
    detalle_extra = frame_obj.evaluate("""
        () => {
            const resultado = [];

            // 1. Buscar contenteditable
            const editables = document.querySelectorAll('[contenteditable="true"]');
            editables.forEach(el => {
                if (el.offsetParent !== null) {
                    resultado.push(`[CONTENTEDITABLE] class='${el.className}' text='${(el.innerText||"").trim().slice(0,80)}'`);
                }
            });

            // 2. Buscar td o celdas de grid visibles
            const celdas = document.querySelectorAll('td, [role="gridcell"], [role="cell"]');
            celdas.forEach(el => {
                if (el.offsetParent !== null) {
                    resultado.push(`[${el.tagName}/cell] class='${el.className}' text='${(el.innerText||"").trim().slice(0,80)}'`);
                }
            });

            // 3. Buscar el campo PedidoNo (texto visible con el número de pedido)
            const todo = document.body.innerText || "";
            const matchPedido = todo.match(/Pedido\\s*No\\.?\\s*[:\\-]?\\s*([\\w\\-X]+)/i);
            resultado.push(`[PEDIDO_NO_TEXT] = '${matchPedido ? matchPedido[1] : "no encontrado"}'`);

            // 4. Cualquier span/div con "440" o "XXXX"
            const spans = document.querySelectorAll('span, div, p, h1, h2, h3, h4, label');
            spans.forEach(el => {
                const txt = (el.innerText || "").trim();
                if ((txt.includes("440") || txt.includes("XXXX") || txt.includes("Pedido")) && txt.length < 60 && el.offsetParent !== null) {
                    resultado.push(`[${el.tagName}] class='${el.className.slice(0,40)}' text='${txt}'`);
                }
            });

            return resultado.slice(0, 40).join("\\n");
        }
    """)

    resumen = (
        f"=== INPUTS FRAME ({len(lineas_inputs)}) ===\n"
        + "\n".join(lineas_inputs[:60])
        + f"\n\n=== BOTONES FRAME ({len(lineas_botones)}) ===\n"
        + "\n".join(lineas_botones[:30])
        + f"\n\n=== DROPDOWN ===\n{dropdown_html or '(nada)'}"
        + f"\n\n=== CELDA CANTIDAD / PEDIDO NO ===\n{detalle_extra or '(nada)'}"
    )

    paso("DOM capturado — copia el resultado de 'obtenido'")

    return {
        "prueba":       "Inspeccionar Formulario Pedido",
        "estado":       "ok",
        "dato_entrada": f"Botón nuevo usado: {btn_encontrado or 'ninguno'}",
        "esperado":     "Lista de campos del formulario",
        "obtenido":     resumen,
    }
