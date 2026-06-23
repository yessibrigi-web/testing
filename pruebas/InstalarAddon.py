"""
Prueba: Instalar Addon / no modificar
Módulo: Addons
"""

def ejecutar(pagina, frame, on_paso=None, parametros=None, addon=None):

    pagina.set_default_timeout(600000)
    pagina.set_default_navigation_timeout(600000)

    # Número del addon a instalar — PRESERVA el signo tal como lo escribe el usuario.
    # "-142" → addon negativo  |  "142" o "+142" → addon positivo
    # Hay pares de addons que comparten número pero con signo distinto, p.ej.:
    #   -142 = Migración de ajustes puntuales de proyección
    #    142 = Nueva versión de aprobaciones en ADPRO (compras, anticipos, actas...)
    # Default: 142 (positivo)
    parametros = parametros or {}
    if addon:
        addon_raw = str(addon).strip()
    else:
        addon_raw = str(parametros.get("addon") or "142").strip()
    if not addon_raw:
        addon_raw = "142"
    # Descartar "+" si el usuario lo escribió, conservar "-"
    if addon_raw.startswith("+"):
        addon_raw = addon_raw[1:]
    addon_objetivo = addon_raw

    # HD a registrar en la observación (configurado desde el dashboard)
    hd_observacion = str(parametros.get("hd") or "").strip()
    if not hd_observacion:
        return {
            "prueba":       "Instalar Addon",
            "estado":       "error",
            "dato_entrada": addon_objetivo,
            "esperado":     "HD ingresado en el dashboard",
            "obtenido":     "Falta el número de HD en el dashboard (campo 'HD #')",
        }

    if on_paso:
        on_paso(f"Addon objetivo: {addon_objetivo} | HD: {hd_observacion}")

    # Clic en ADPRO
    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)

    if on_paso:
        on_paso("ADPRO")

    # Navegar menú
    for ruta, nombre in [
        ("ADPRO/Mantenimiento", "Mantenimiento"),
        ("ADPRO/Mantenimiento/CONFIGURACION", "CONFIGURACION"),
        ("ADPRO/Mantenimiento/CONFIGURACION/Addons", "Addons"),
    ]:
        pagina.evaluate(f"""
            () => {{
                const items = document.querySelectorAll('div.menu-caja');
                for (const item of items) {{
                    if (item.getAttribute('title') === 'Ruta: {ruta}') {{
                        item.click();
                        break;
                    }}
                }}
            }}
        """)
        pagina.wait_for_timeout(800)

        if on_paso:
            on_paso(nombre)

    # Esperar iframe
    pagina.wait_for_load_state("networkidle")

    frame = pagina.locator("#pagina1").content_frame

    # Esperar contenido
    try:
        frame.locator(".MuiAccordionSummary-root, #btnRecargar").first.wait_for(timeout=15000)
    except Exception:
        pagina.wait_for_timeout(3000)

    # Recargar si es necesario
    try:
        btn = frame.locator("#btnRecargar")
        if btn.is_visible():
            btn.click()
            frame.locator(".MuiAccordionSummary-root").first.wait_for(timeout=10000)
            if on_paso:
                on_paso("Addons recargado")
    except Exception:
        pass

    if on_paso:
        on_paso("Addons cargado")

    # Buscar addon — regex anclado al inicio para NO confundir "-142" con "142"
    # (si solo usáramos substring 'has-text', "142" matchearía también el accordion "-142")
    import re
    patron_addon = re.compile(rf"^{re.escape(addon_objetivo)}\b")
    addon = frame.locator(".MuiAccordionSummary-root").filter(
        has_text=patron_addon
    ).first

    addon.wait_for(timeout=10000)
    addon.hover()
    pagina.wait_for_timeout(500)

    # Clic activar
    addon.locator(".btn-activar").first.click()
    pagina.wait_for_timeout(1000)

    if on_paso:
        on_paso(f"Activar addon {addon_objetivo}")

    # =========================
    # MODAL INSTALACIÓN
    # =========================

    frame.locator("text=Seleccionar todas las empresas").wait_for(timeout=10000)

    if on_paso:
        on_paso("Modal de instalación abierto")

    # Checkbox "Seleccionar todas las empresas"
    checkbox = frame.locator("text=Seleccionar todas las empresas").locator("..")
    checkbox.click(force=True)
    pagina.wait_for_timeout(1500)

    if on_paso:
        on_paso("Checkbox seleccionado")

    # Observaciones (HD configurado desde el dashboard)
    observacion = frame.locator('input[type="text"]').last
    observacion.click()
    observacion.press_sequentially(hd_observacion)
    pagina.wait_for_timeout(1000)

    if on_paso:
        on_paso(f"Observación '{hd_observacion}' ingresada")

    # Botón instalar
    btn_instalar = frame.get_by_role("button", name="Instalar")
    btn_instalar.wait_for(timeout=10000)
    pagina.wait_for_timeout(2000)

    # Ejecutar instalación
    btn_instalar.click(force=True)

    if on_paso:
        on_paso("Instalación ejecutada")

    # =========================
    # ESPERAR FINALIZACIÓN REAL
    # =========================

    btn_cerrar = frame.get_by_role("button", name="Cerrar")
    btn_cerrar.wait_for(timeout=300000)

    if on_paso:
        on_paso("Esperando finalización de instalación...")

    # Esperar hasta que el botón se habilite
    for i in range(300):
        try:
            if btn_cerrar.is_enabled():
                if on_paso:
                    on_paso("Instalación completada en todas las empresas")
                break
        except Exception:
            pass

        # Mantener viva la conexión/log
        if i % 5 == 0:
            if on_paso:
                on_paso(f"Instalando empresas... {i}s")

        # Mantener actividad del navegador
        pagina.mouse.move(1 + (i % 100), 1)
        pagina.wait_for_timeout(1000)
    else:
        raise Exception("La instalación no terminó correctamente")

    # Buscar mensaje de éxito
    mensaje_ok = False
    for locator in [
        frame.locator("text=/[Ii]nstalado/"),
        frame.locator("text=/[Aa]ctivado/"),
        frame.locator("text=/[Éé]xito/"),
        pagina.locator("text=/[Ii]nstalado/"),
        pagina.locator("text=/[Ss]e instal/"),
    ]:
        try:
            if locator.first.is_visible(timeout=2000):
                mensaje_ok = True
                break
        except Exception:
            continue

    # Cerrar modal final
    btn_cerrar.click(force=True)
    pagina.wait_for_timeout(1000)

    if on_paso:
        on_paso("Modal final cerrado")

    # Resultado final
    if mensaje_ok:
        import base64
        try:
            screenshot = base64.b64encode(pagina.screenshot(type="png")).decode("utf-8")
        except Exception:
            screenshot = None

        if on_paso:
            on_paso("Addon instalado correctamente")

        return {
            "prueba":       "Instalar Addon",
            "estado":       "ok",
            "dato_entrada": addon_objetivo,
            "esperado":     "Mensaje de addon instalado",
            "obtenido":     "Addon instalado correctamente",
            "screenshot":   screenshot,
        }
    else:
        if on_paso:
            on_paso("No se detectó confirmación")

        return {
            "prueba":       "Instalar Addon",
            "estado":       "error",
            "dato_entrada": addon_objetivo,
            "esperado":     "Mensaje de addon instalado",
            "obtenido":     "No apareció mensaje de instalación correcta",
        }
