"""
Validación específica del Addon 143 Nueva versión de generación y aprobación de pedidos proyecto
Parametrización: 1 item (Pedidos)
ADPRO: 1 opción (Aprobación de pedidos)
Módulo: Addons
"""
import base64


def capturar(pagina):
    try:
        return base64.b64encode(pagina.screenshot(type="png")).decode("utf-8")
    except Exception:
        return None


def verificar_y_recargar(frame_locator, pagina, nombre, max_intentos=2):
    """
    Verifica si hay error 'Algo salió mal' y recarga hasta max_intentos veces.
    Retorna (hay_error, frame_actualizado)
    """
    frame2 = frame_locator
    for intento in range(max_intentos):
        try:
            if frame2.get_by_text("Algo salió mal", exact=False).is_visible(timeout=3000):
                try:
                    frame2.get_by_role("button", name="Recargar página").click()
                except Exception:
                    pass
                pagina.wait_for_timeout(4000)
                frame2 = pagina.locator("#pagina1").content_frame
            else:
                return False, frame2
        except Exception:
            return False, frame2

    # Verificar si sigue el error después de los intentos
    try:
        if frame2.get_by_text("Algo salió mal", exact=False).is_visible(timeout=3000):
            return True, frame2
    except Exception:
        pass
    return False, frame2


def ejecutar(pagina, frame, on_paso=None):

    errores = []

    # ─────────────────────────────────────────────
    # PASO 1: Verificar item "Pedidos" en Parametrización
    # ─────────────────────────────────────────────
    if on_paso: on_paso("Verificando Parametrización de aprobaciones")

    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)
    pagina.wait_for_timeout(1000)

    for ruta in ["ADPRO/Mantenimiento", "ADPRO/Mantenimiento/CONFIGURACION"]:
        pagina.evaluate(f"""
            () => {{
                const items = document.querySelectorAll('div.menu-caja');
                for (const item of items) {{
                    if (item.getAttribute('title') === 'Ruta: {ruta}') {{
                        item.click(); break;
                    }}
                }}
            }}
        """)
        pagina.wait_for_timeout(800)

    pagina.get_by_role("button", name="Parametrización de").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(3000)

    frame2 = pagina.locator("#pagina1").content_frame

    try:
        btn = frame2.locator("#btnRecargar")
        if btn.is_visible():
            btn.click()
            pagina.wait_for_timeout(3000)
    except Exception:
        pass

    pagina.wait_for_timeout(2000)

    # Verificar error con reintento
    hay_error, frame2 = verificar_y_recargar(frame2, pagina, "Parametrización")
    if hay_error:
        if on_paso: on_paso("❌ Parametrización no carga después de 2 recargas")
        return {
            "prueba":       "Validar Addon 143",
            "estado":       "fail",
            "dato_entrada": "143",
            "esperado":     "Item 'Pedidos' en Parametrización",
            "obtenido":     "Error: Página 'Algo salió mal' persiste después de 2 recargas en Parametrización",
            "screenshot":   capturar(pagina),
        }

    # Verificar item "Pedidos"
    try:
        item = frame2.get_by_text("Pedidos", exact=False).first
        if item.is_visible(timeout=5000):
            if on_paso: on_paso("✓ Pedidos en Parametrización")
        else:
            errores.append("Item 'Pedidos' no visible en Parametrización")
            if on_paso: on_paso("✗ Pedidos no encontrado en Parametrización")
    except Exception as e:
        errores.append(f"Item 'Pedidos' no encontrado: {str(e)[:80]}")
        if on_paso: on_paso("✗ Error buscando Pedidos")

    if errores:
        return {
            "prueba":       "Validar Addon 143",
            "estado":       "fail",
            "dato_entrada": "143",
            "esperado":     "Item 'Pedidos' activo en Parametrización",
            "obtenido":     " | ".join(errores),
            "screenshot":   capturar(pagina),
        }

    # ─────────────────────────────────────────────
    # PASO 2: Verificar Aprobación de pedidos en ADPRO
    # ─────────────────────────────────────────────
    if on_paso: on_paso("Verificando Aprobación de pedidos en ADPRO")

    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)
    pagina.wait_for_timeout(1000)

    for ruta in ["ADPRO/Almacén", "ADPRO/Almacén/PEDIDOS", "ADPRO/Almacén/PEDIDOS/Aprobación pedidos"]:
        pagina.evaluate(f"""
            () => {{
                const items = document.querySelectorAll('div.menu-caja');
                for (const item of items) {{
                    if (item.getAttribute('title') === 'Ruta: {ruta}') {{
                        item.click(); break;
                    }}
                }}
            }}
        """)
        pagina.wait_for_timeout(800)

    # Clic en Aprobación de pedidos
    pagina.evaluate("""
        () => {
            const items = document.querySelectorAll('div.menu-caja');
            for (const item of items) {
                if (item.getAttribute('title') === 'Ruta: ADPRO/Almacén/PEDIDOS/Aprobación pedidos/Aprobación de pedidos') {
                    item.click(); break;
                }
            }
        }
    """)
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(2000)

    frame3 = pagina.locator("#pagina1").content_frame

    # Verificar error con reintento
    hay_error, frame3 = verificar_y_recargar(frame3, pagina, "Aprobación de pedidos")
    if hay_error:
        if on_paso: on_paso("❌ Aprobación de pedidos no carga después de 2 recargas")
        return {
            "prueba":       "Validar Addon 143",
            "estado":       "fail",
            "dato_entrada": "143",
            "esperado":     "Aprobación de pedidos cargada correctamente",
            "obtenido":     "Error: Página 'Algo salió mal' persiste después de 2 recargas en Aprobación de pedidos",
            "screenshot":   capturar(pagina),
        }

    if on_paso: on_paso("✓ Aprobación de pedidos cargada correctamente")

    # ─────────────────────────────────────────────
    # PASO 3: Verificar Pedidos proyecto en ADPRO/Almacén/PEDIDOS
    # ─────────────────────────────────────────────
    if on_paso: on_paso("Verificando Pedidos proyecto en ADPRO/Almacén/PEDIDOS")

    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)
    pagina.wait_for_timeout(1000)

    for ruta in ["ADPRO/Almacén", "ADPRO/Almacén/PEDIDOS"]:
        pagina.evaluate(f"""
            () => {{
                const items = document.querySelectorAll('div.menu-caja');
                for (const item of items) {{
                    if (item.getAttribute('title') === 'Ruta: {ruta}') {{
                        item.click(); break;
                    }}
                }}
            }}
        """)
        pagina.wait_for_timeout(800)

    pagina.evaluate("""
        () => {
            const items = document.querySelectorAll('div.menu-caja');
            for (const item of items) {
                if (item.getAttribute('title') === 'Ruta: ADPRO/Almacén/PEDIDOS/Pedidos proyecto') {
                    item.click(); break;
                }
            }
        }
    """)
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(2000)

    frame4 = pagina.locator("#pagina1").content_frame

    # Si aparece modal "Selector de Proyecto", seleccionar el primer proyecto buscado recientemente
    try:
        modal_visible = frame4.get_by_text("Selector de Proyecto", exact=False).is_visible(timeout=4000)
    except Exception:
        modal_visible = False

    if modal_visible:
        try:
            # Buscar el primer ítem de proyectos recientes dentro del input/lista "seleccione un proyecto"
            primer_proyecto = frame4.locator("input[placeholder*='seleccione un proyecto'], [placeholder*='Seleccione un proyecto']").first
            primer_proyecto.click()
            pagina.wait_for_timeout(500)
            # Seleccionar el primer resultado de proyectos recientes en la lista desplegable
            opcion_reciente = frame4.locator("li, .select2-result, .dropdown-item, option").first
            opcion_reciente.click()
        except Exception:
            # Alternativa: buscar directamente ítems de la lista de recientes
            try:
                frame4.locator("ul li").first.click()
            except Exception:
                pass
        pagina.wait_for_timeout(1000)

    # Esperar hasta 5 segundos a que cargue la página verificando el botón "Nuevo pedido"
    try:
        frame4.get_by_role("button", name="Nuevo pedido").wait_for(state="visible", timeout=5000)
        if on_paso: on_paso("✓ Pedidos proyecto cargado correctamente")
    except Exception:
        if on_paso: on_paso("✗ Botón 'Nuevo pedido' no encontrado en Pedidos proyecto")
        errores.append("Botón 'Nuevo pedido' no visible en Pedidos proyecto")

    if errores:
        return {
            "prueba":       "Validar Addon 143",
            "estado":       "fail",
            "dato_entrada": "143",
            "esperado":     "Pedidos proyecto cargado con botón 'Nuevo pedido'",
            "obtenido":     " | ".join(errores),
            "screenshot":   capturar(pagina),
        }

    return {
        "prueba":       "Validar Addon 143",
        "estado":       "ok",
        "dato_entrada": "143",
        "esperado":     "Item 'Pedidos' en Parametrización, Aprobación de pedidos y Pedidos proyecto en ADPRO",
        "obtenido":     "Addon 143 validado correctamente",
        "screenshot":   capturar(pagina),
    }