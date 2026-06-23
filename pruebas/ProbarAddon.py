"""
Prueba: Probar Addon / no modificar
Módulo: Addons
"""

def ejecutar(pagina, frame, on_paso=None):

    # Ir a ADPRO
    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)
    pagina.wait_for_timeout(1000)
    if on_paso: on_paso("ADPRO")

    # Navegar a Mantenimiento
    pagina.evaluate("""
        () => {
            const items = document.querySelectorAll('div.menu-caja');
            for (const item of items) {
                if (item.getAttribute('title') === 'Ruta: ADPRO/Mantenimiento') {
                    item.click(); break;
                }
            }
        }
    """)
    pagina.wait_for_timeout(1000)
    if on_paso: on_paso("Mantenimiento")

    # Navegar a CONFIGURACION
    pagina.evaluate("""
        () => {
            const items = document.querySelectorAll('div.menu-caja');
            for (const item of items) {
                if (item.getAttribute('title') === 'Ruta: ADPRO/Mantenimiento/CONFIGURACION') {
                    item.click(); break;
                }
            }
        }
    """)
    pagina.wait_for_timeout(1000)
    if on_paso: on_paso("CONFIGURACION")

    # Abrir Parametrización
    pagina.get_by_role("button", name="Parametrización de").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(1000)
    if on_paso: on_paso("Parametrización de")

    # Recargar si es necesario
    frame2 = pagina.locator("#pagina1").content_frame
    pagina.wait_for_timeout(3000)
    try:
        btn = frame2.locator("#btnRecargar")
        if btn.is_visible():
            btn.click()
            pagina.wait_for_timeout(3000)
        if on_paso: on_paso("Página cargada")
    except Exception:
        pass

    return {
        "prueba":       "Probar Addon",
        "estado":       "ok",
        "dato_entrada": "-",
        "esperado":     "Módulo de Parametrización accesible",
        "obtenido":     "Módulo cargado correctamente",
    }
