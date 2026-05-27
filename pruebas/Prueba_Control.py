"""
Prueba: Generación de control de proyecto
Módulo: Control 
"""

def ejecutar(pagina, frame, on_paso=None):

    # Interceptar errores HTTP
    errores_http = []
    def capturar_respuesta(response):
        if response.status >= 400:
            errores_http.append(f"HTTP {response.status}: {response.url[:80]}")
    pagina.on("response", capturar_respuesta)

    def verificar_error_pantalla():
        """Verifica si hay error visible en pantalla y retorna el mensaje."""
        try:
            toast = frame.locator("text=Ocurrió un error en el servidor").first
            if toast.is_visible():
                detalle = ""
                try:
                    detalle = frame.locator("body").inner_text()
                    lineas = [l.strip() for l in detalle.split("\n") if l.strip()]
                    detalle = " | ".join(lineas[:3])[:300]
                except Exception:
                    pass
                return f"Error servidor: {detalle}" if detalle else "Ocurrió un error en el servidor"
        except Exception:
            pass

        try:
            cuerpo = frame.locator("body").inner_text()
            if "error" in cuerpo.lower() and ("OLE DB" in cuerpo or "ODBC" in cuerpo or "SQL" in cuerpo):
                lineas = [l.strip() for l in cuerpo.split("\n") if l.strip()]
                return " | ".join(lineas[:3])[:300]
        except Exception:
            pass

        return None

    # ── Navegación ──
    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)
    pagina.wait_for_timeout(1000)
    if on_paso: on_paso("ADPRO")

    pagina.get_by_role("button", name="Control").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("Control")

    pagina.get_by_role("button", name="Control del proyecto").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("Control del proyecto")

    frame = pagina.locator("#pagina1").content_frame

    # Verificar error al cargar la página
    pagina.wait_for_timeout(2000)
    error = verificar_error_pantalla()
    if error or errores_http:
        mensaje = error or errores_http[0]
        return {
            "prueba":       "Control",
            "estado":       "fail",
            "dato_entrada": "-",
            "esperado":     "Página cargada sin errores",
            "obtenido":     mensaje,
        }
    if on_paso: on_paso("Página cargada")

    # El modal "Selector de Proyecto" vive en el DOM principal (fuera del iframe)
    pagina.wait_for_timeout(2000)
    try:
        _modal_visible = pagina.locator("#contenedor-dialogselectorObra").is_visible(timeout=3000)
    except Exception:
        _modal_visible = False

    if _modal_visible:
        if on_paso: on_paso("Modal Selector de Proyecto detectado")
        try:
            pagina.locator("ul#obrasFrecuentes .contenedor-itemObrafrecuente li[title]").first.click()
        except Exception:
            try:
                pagina.locator("ul#obrasFrecuentes li").first.click()
            except Exception:
                pass
        pagina.wait_for_timeout(2000)

    # ── Generar control ──
    frame.get_by_role("button", name="Generar control").click()
    pagina.wait_for_timeout(1000)
    if on_paso: on_paso("Generar control")

    frame.get_by_role("button", name="Aceptar").click()
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Aceptar")

    # Verificar error después de Aceptar
    error = verificar_error_pantalla()
    if error or errores_http:
        mensaje = error or errores_http[0]
        return {
            "prueba":       "Control",
            "estado":       "fail",
            "dato_entrada": "-",
            "esperado":     "Control generado sin errores",
            "obtenido":     mensaje,
        }

    # ── Consultar ──
    frame.get_by_role("button", name="Consultar").click()
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Consultar")

    # Verificar error después de Consultar
    error = verificar_error_pantalla()
    if error or errores_http:
        mensaje = error or errores_http[0]
        return {
            "prueba":       "Control",
            "estado":       "fail",
            "dato_entrada": "-",
            "esperado":     "Consulta ejecutada sin errores",
            "obtenido":     mensaje,
        }

    return {
        "prueba":       "Control",
        "estado":       "ok",
        "dato_entrada": "-",
        "esperado":     "Control del proyecto generado correctamente",
        "obtenido":     "Flujo completado correctamente",
    }