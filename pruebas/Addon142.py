"""
Validación específica del Addon 142 Nueva versión de aprobaciones en ADPRO (compras, anticipos de almacén, actas de avance cliente y estándar y anticipos cliente)
Parametrización: 6 items
ADPRO: 3 opciones de aprobación
Módulo: Addons
"""
import base64


def capturar(pagina):
    try:
        return base64.b64encode(pagina.screenshot(type="png")).decode("utf-8")
    except Exception:
        return None


def verificar_item_parametrizacion(frame, nombre_item, pagina):
    """Verifica que un item exista y esté visible en la lista de parametrización."""
    try:
        item = frame.get_by_text(nombre_item, exact=False).first
        if item.is_visible(timeout=5000):
            return True, None
        return False, f"Item '{nombre_item}' no visible"
    except Exception as e:
        return False, f"Item '{nombre_item}' no encontrado: {str(e)[:80]}"


def verificar_opcion_adpro(pagina, ruta, nombre_boton, mensajes_info=None):
    """Navega a una opción de ADPRO y verifica que cargue correctamente.

    Devuelve (ok, error, advertencia):
      ok=True,  error=None,  advertencia=None  → cargó sin problemas
      ok=True,  error=None,  advertencia=str   → cargó pero hay aviso de config del cliente
      ok=False, error=str,   advertencia=None  → error real de flujo

    mensajes_info: subcadenas que, si aparecen en pantalla, representan
    configuración pendiente del cliente y NO deben contarse como error.
    """
    mensajes_info = mensajes_info or []
    try:
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
        pagina.wait_for_load_state("networkidle")
        pagina.wait_for_timeout(2000)

        frame2 = pagina.locator("#pagina1").content_frame

        # Mensajes informativos del cliente — no son errores de flujo del addon
        for msg in mensajes_info:
            try:
                if frame2.get_by_text(msg, exact=False).is_visible(timeout=3000):
                    advertencia = f"⚠️ {nombre_boton}: {msg[:90]} (configuración pendiente del cliente)"
                    return True, None, advertencia
            except Exception:
                pass

        # Verificar error "Algo salió mal"
        try:
            if frame2.get_by_text("Algo salió mal", exact=False).is_visible(timeout=3000):
                return False, f"Error al cargar '{nombre_boton}': Algo salió mal", None
        except Exception:
            pass

        return True, None, None
    except Exception as e:
        return False, f"Error navegando a '{nombre_boton}': {str(e)[:80]}", None


def expandir_menu_padres(pagina, rutas_padres):
    """Re-abre el menú admin y expande la cadena de menús padres."""
    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)
    pagina.wait_for_timeout(800)
    for ruta in rutas_padres:
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


def ejecutar(pagina, frame, on_paso=None):

    errores = []

    # ─────────────────────────────────────────────
    # PASO 1: Verificar items en Parametrización
    # ─────────────────────────────────────────────
    if on_paso: on_paso("Verificando Parametrización de aprobaciones")

    # Navegar a Parametrización
    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)
    pagina.wait_for_timeout(1000)

    for ruta, nombre in [
        ("ADPRO/Mantenimiento", "Mantenimiento"),
        ("ADPRO/Mantenimiento/CONFIGURACION", "CONFIGURACION"),
    ]:
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

    # Recargar si necesario
    try:
        btn = frame2.locator("#btnRecargar")
        if btn.is_visible():
            btn.click()
            pagina.wait_for_timeout(3000)
    except Exception:
        pass

    pagina.wait_for_timeout(2000)

    # Verificar error general
    # Verificar error general — reintentar hasta 2 veces
    for intento in range(2):
        try:
            if frame2.get_by_text("Algo salió mal", exact=False).is_visible(timeout=3000):
                if on_paso: on_paso(f"⚠️ Error al cargar, recargando (intento {intento + 1})...")
                frame2.get_by_role("button", name="Recargar página").click()
                pagina.wait_for_timeout(4000)
                frame2 = pagina.locator("#pagina1").content_frame
            else:
                break
        except Exception:
            break
    else:
        # Verificar si sigue el error después de 2 recargas
        try:
            if frame2.get_by_text("Algo salió mal", exact=False).is_visible(timeout=3000):
                if on_paso: on_paso("❌ Parametrización no carga después de 2 recargas")
                return {
                    "prueba":       "Validar Addon 142",
                    "estado":       "fail",
                    "dato_entrada": "142",
                    "esperado":     "Parametrización cargada con 6 items",
                    "obtenido":     "Error: Página 'Algo salió mal' persiste después de 2 recargas",
                    "screenshot":   capturar(pagina),
                }
        except Exception:
            pass

    # Verificar los 6 items
    items_esperados = [
        "Actas de avance cliente",
        "Actas de avance estándar",
        "Anticipos cliente",
        "Órdenes de compra",
        "Anticipos Almacén",
        "Anticipos Almacén única etapa",
    ]

    for item in items_esperados:
        ok, error = verificar_item_parametrizacion(frame2, item, pagina)
        if ok:
            if on_paso: on_paso(f"✓ {item}")
        else:
            errores.append(error)
            if on_paso: on_paso(f"✗ {item}")

    if errores:
        return {
            "prueba":       "Validar Addon 142",
            "estado":       "fail",
            "dato_entrada": "142",
            "esperado":     "6 items en Parametrización de aprobaciones",
            "obtenido":     f"Items faltantes: {', '.join(errores)}",
            "screenshot":   capturar(pagina),
        }

    if on_paso: on_paso("✓ Los 6 items de Parametrización están activos")

    # ─────────────────────────────────────────────
    # PASO 2: Verificar opciones en ADPRO
    # ─────────────────────────────────────────────
    if on_paso: on_paso("Verificando opciones de Aprobaciones en ADPRO")

    # Navegar al menú Ejecución → Aprobaciones
    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)
    pagina.wait_for_timeout(1000)

    for ruta, nombre in [
        ("ADPRO/Ejecución", "Ejecución"),
        ("ADPRO/Ejecución/Aprobaciones", "Aprobaciones"),
    ]:
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

    opciones_adpro = [
        ("ADPRO/Ejecución/Aprobaciones/Aprobación anticipos cliente",    "Aprobación anticipos cliente"),
        ("ADPRO/Ejecución/Aprobaciones/Aprobación actas avance cliente",  "Aprobación actas avance cliente"),
        ("ADPRO/Ejecución/Aprobaciones/Aprobación actas avance estándar", "Aprobación actas avance estándar"),
    ]

    for ruta, nombre in opciones_adpro:
        ok, error, advertencia = verificar_opcion_adpro(pagina, ruta, nombre)
        if ok:
            if on_paso: on_paso(advertencia if advertencia else f"✓ {nombre}")
        else:
            errores.append(error)
            if on_paso: on_paso(f"✗ {nombre}")

    # Opciones adicionales bajo ADPRO/Almacén (3 padres distintos)
    # Cada entrada: (padres, ruta_hoja, nombre, mensajes_info)
    # mensajes_info: mensajes del ERP que indican configuración pendiente del
    # cliente, no un error de flujo del addon.
    opciones_almacen = [
        (
            ["ADPRO/Almacén", "ADPRO/Almacén/COMPRAS", "ADPRO/Almacén/COMPRAS/APROBACIÓN ÓRDENES DE COMPRA"],
            "ADPRO/Almacén/COMPRAS/APROBACIÓN ÓRDENES DE COMPRA/Aprobaciones orden de compra",
            "Aprobaciones orden de compra",
            [],
        ),
        (
            ["ADPRO/Almacén", "ADPRO/Almacén/Anticipos", "ADPRO/Almacén/Anticipos/Aprobaciones"],
            "ADPRO/Almacén/Anticipos/Aprobaciones/Aprobación de anticipos",
            "Aprobación de anticipos",
            [],
        ),
        (
            ["ADPRO/Almacén", "ADPRO/Almacén/ANTICIPOS", "ADPRO/Almacén/ANTICIPOS/APROBACIÓN ANTICIPOS"],
            "ADPRO/Almacén/ANTICIPOS/APROBACIÓN ANTICIPOS/Aprobación única de anticipos",
            "Aprobación única de anticipos",
            # El ERP puede mostrar este aviso cuando no hay semanas parametrizadas;
            # es una configuración que debe hacer el cliente, no un fallo del addon.
            ["No se encontraron semanas parametrizadas"],
        ),
    ]

    for padres, ruta, nombre, msgs_info in opciones_almacen:
        expandir_menu_padres(pagina, padres)
        ok, error, advertencia = verificar_opcion_adpro(pagina, ruta, nombre, msgs_info)
        if ok:
            if on_paso: on_paso(advertencia if advertencia else f"✓ {nombre}")
        else:
            errores.append(error)
            if on_paso: on_paso(f"✗ {nombre}")

    if errores:
        return {
            "prueba":       "Validar Addon 142",
            "estado":       "fail",
            "dato_entrada": "142",
            "esperado":     "6 opciones de Aprobaciones activas en ADPRO",
            "obtenido":     f"Errores: {' | '.join(errores)}",
            "screenshot":   capturar(pagina),
        }

    if on_paso: on_paso("✓ Todas las opciones de Aprobaciones están activas")

    return {
        "prueba":       "Validar Addon 142",
        "estado":       "ok",
        "dato_entrada": "142",
        "esperado":     "6 items en Parametrización y 6 opciones en ADPRO activas",
        "obtenido":     "Addon 142 validado correctamente",
        "screenshot":   capturar(pagina),
    }
