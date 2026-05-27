"""
Prueba: CambioRangoFechas
Módulo: Inventarios
Cambia el valor de cualquier variable en Maestro ADP configuración.
El nombre de la variable y el valor nuevo se reciben como parámetros desde el dashboard.
"""
import base64


def capturar(pagina):
    try:
        return base64.b64encode(pagina.screenshot(type="png")).decode("utf-8")
    except Exception:
        return None


def ejecutar(pagina, frame, on_paso=None, parametros=None):

    parametros = parametros or {}

    # Nombre de la variable a buscar (campo "Variable" del dashboard)
    variable = str(parametros.get("variable") or "rangofechamovinv").strip().lower()
    if not variable:
        variable = "rangofechamovinv"

    # Nuevo valor a asignar (campo "Valor" del dashboard)
    valor = str(parametros.get("valor") or "365").strip()
    if not valor:
        valor = "365"

    # ── Navegación ──
    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_selector("div.menu-caja:visible", timeout=30000)
    pagina.wait_for_timeout(1000)
    if on_paso: on_paso("ADPRO")

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

    pagina.evaluate("""
        () => {
            const items = document.querySelectorAll('div.menu-caja');
            for (const item of items) {
                if (item.getAttribute('title') === 'Ruta: ADPRO/Mantenimiento/CONFIGURACION/Maestro ADP configuración') {
                    item.click(); break;
                }
            }
        }
    """)
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(2000)
    if on_paso: on_paso("Maestro ADP configuración")

    frame2 = pagina.locator("#pagina1").content_frame

    # ── Buscar variable ──
    codigo_input = frame2.get_by_role("textbox", name="Codigo")
    codigo_input.click()
    codigo_input.fill(variable)
    pagina.wait_for_timeout(500)
    if on_paso: on_paso(f"Variable '{variable}' ingresada")

    frame2.get_by_role("button", name="Consultar").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(2000)
    if on_paso: on_paso("Consulta ejecutada")

    # ── Cambiar valor ──
    # Se usa el placeholder "Valor" del primer resultado; funciona para cualquier variable
    celda_valor = frame2.get_by_placeholder("Valor").first
    celda_valor.click(click_count=3)
    celda_valor.fill(valor)
    pagina.wait_for_timeout(500)
    if on_paso: on_paso(f"Valor '{valor}' ingresado")

    # Clic fuera del input para disparar el guardado
    frame2.locator("html").click()
    pagina.wait_for_timeout(1000)

    # ── Esperar confirmación y capturar screenshot ──
    screenshot = None
    guardado_ok = False
    try:
        frame2.get_by_text("La variable se actualizo correctamente", exact=False).wait_for(
            state="visible", timeout=8000
        )
        guardado_ok = True
        if on_paso: on_paso("✓ Variable actualizada correctamente")
        screenshot = capturar(pagina)
    except Exception:
        # Intentar también en el contexto principal
        try:
            pagina.get_by_text("La variable se actualizo correctamente", exact=False).wait_for(
                state="visible", timeout=4000
            )
            guardado_ok = True
            if on_paso: on_paso("✓ Variable actualizada correctamente")
            screenshot = capturar(pagina)
        except Exception:
            if on_paso: on_paso("✗ No se detectó confirmación de guardado")

    if not guardado_ok:
        return {
            "prueba":       "CambioRangoFechas",
            "estado":       "fail",
            "dato_entrada": f"{variable} = {valor}",
            "esperado":     "La variable se actualizo correctamente",
            "obtenido":     "No apareció mensaje de confirmación",
            "screenshot":   capturar(pagina),
        }

    return {
        "prueba":       "CambioRangoFechas",
        "estado":       "ok",
        "dato_entrada": f"{variable} = {valor}",
        "esperado":     "La variable se actualizo correctamente",
        "obtenido":     f"'{variable}' actualizado a '{valor}'",
        "screenshot":   screenshot,
    }
