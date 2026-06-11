"""
Prueba: Dar Acceso usuario 50
Módulo: Configuracion
"""

def ejecutar(pagina, frame, on_paso=None):

    # Ir a Configuración de usuarios
    pagina.locator("#menuconfig4").get_by_role("img").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("Menú configuración")

    pagina.get_by_role("button", name="Usuarios").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("Usuarios")

    pagina.get_by_role("button", name="Registro de usuarios").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("Registro de usuarios")

    # Buscar usuario y configurar accesos
    left = pagina.locator("#pagina1").content_frame.get_by_title("leftFrame").content_frame

    left.locator("#usu").click()
    left.locator("#usu").fill("50")
    left.locator("#usu").press("Tab")
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("Usuario 50")

    # Esperar a que el dropdown #menu esté habilitado dinámicamente
    left.locator("#menu:not([disabled])").wait_for(state="visible", timeout=15000)
    pagina.wait_for_timeout(500)

    # Seleccionar "General"
    left.locator("#menu").select_option("1")
    pagina.wait_for_timeout(2000)
    if on_paso: on_paso("General seleccionado")

    # Navegar directamente al mainFrame con la URL de Información General del usuario 50
    pagina.evaluate("""
        () => {
            const iframe = document.querySelector('#pagina1');
            if (!iframe) return;
            const mainFrame = iframe.contentDocument.querySelector('[title="mainFrame"]');
            if (mainFrame) {
                mainFrame.src = 'EdicionInfGeneral.asp?usu=50&mostrar=NO&usuCB=50&UsuarioI=50&TipoEjec=0';
            }
        }
    """)
    pagina.wait_for_timeout(4000)
    if on_paso: on_paso("Información General cargada")

    # Ver accesos — botón en mainFrame con name="btPerfil"
    main = pagina.locator("#pagina1").content_frame.get_by_title("mainFrame").content_frame
    main.locator("input[name='btPerfil']").wait_for(state="visible", timeout=15000)
    main.locator("input[name='btPerfil']").click()
    pagina.wait_for_timeout(4000)
    if on_paso: on_paso("Ver Accesos")

    # Expandir árbol ADPRO → Mantenimiento → CONFIGURACION
    pagina.wait_for_timeout(1000)
    main.get_by_role("row", name="ADPRO").get_by_role("img").first.click()
    pagina.wait_for_timeout(1000)
    if on_paso: on_paso("ADPRO expandido")

    main.get_by_role("row", name="Mantenimiento ADPRO").get_by_role("img").first.click()
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("Mantenimiento expandido")

    main.get_by_role("row", name="Mantenimiento ADPRO").get_by_role("cell").nth(1).click()
    pagina.wait_for_timeout(500)

    main.get_by_role("cell", name="CONFIGURACION").click()
    pagina.wait_for_timeout(500)

    main.get_by_role("row", name="CONFIGURACION ADPRO Mantenimiento").get_by_role("img").first.click()
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("CONFIGURACION expandida")

    main.get_by_role("cell", name="Parametrización de").click()
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("Parametrización encontrada")

    # Activar acceso al nuevo addon solo si no está marcado
    checkbox = main.get_by_alt_text("070090130137")
    if not checkbox.is_checked():
        checkbox.check()
        if on_paso: on_paso("Acceso activado")
    else:
        if on_paso: on_paso("Acceso ya estaba activo")
    pagina.wait_for_timeout(1000)

    return {
        "prueba":       "Dar Acceso Addon",
        "estado":       "ok",
        "dato_entrada": "Usuario 50",
        "esperado":     "Acceso activado en configuración",
        "obtenido":     "Acceso activado correctamente",
    }