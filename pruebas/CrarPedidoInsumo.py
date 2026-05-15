"""
Prueba: Crear Pedido Insumo
Módulo: Compras
"""
import re


def ejecutar(pagina, frame, on_paso=None):
    """
    Ejecuta la prueba 'Crarpedidoinsumo'.
    Recibe la pagina ya logueada en SINCO (despues de seleccionar empresa).
    La prueba incluye la navegacion al modulo correspondiente.
    on_paso: callback opcional para reportar progreso con screenshot.
    Retorna dict con el resultado.
    """
    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_load_state('networkidle')
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("ADPRO")
    pagina.get_by_role("button", name="Almacén").click()
    pagina.wait_for_load_state('networkidle')
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("Almacén")
    pagina.get_by_role("button", name="PEDIDOS").click()
    pagina.wait_for_load_state('networkidle')
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("PEDIDOS")
    pagina.get_by_role("button", name="Pedidos proyecto").click()
    pagina.wait_for_load_state('networkidle')
    pagina.wait_for_timeout(500)
    if on_paso: on_paso("Pedidos proyecto")
    frame = pagina.locator("#pagina1").content_frame
    frame.get_by_role("button", name="Nuevo pedido").click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Nuevo pedido")
    frame.get_by_role("combobox", name="Buscar insumo").click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Buscar insumo")
    frame.get_by_role("combobox", name="Buscar insumo").fill("_")
    pagina.wait_for_timeout(1000)
    frame.get_by_text("1008 - TOPE PUERTA CON").click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("1008 - TOPE PUERTA CON")
    frame.get_by_role("combobox", name="Buscar actividad...").click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Buscar actividad...")
    frame.get_by_role("combobox", name="Buscar actividad...").fill("_")
    pagina.wait_for_timeout(1000)
    frame.get_by_text("1.001 - LOCALIZACION Y").click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("1.001 - LOCALIZACION Y")
    frame.get_by_role("button", name="Agregar").click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Agregar")
    frame.get_by_role("row").last.get_by_role("gridcell").last.click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Accion")
    frame.get_by_role("textbox").fill("1")
    pagina.wait_for_timeout(1000)
    frame.locator("div").filter(has_text=re.compile(r"^Agregar InsumosBuscar insumoBuscar insumo$")).first.click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Accion")
    frame.get_by_role("heading", name="Guardado exitoso").click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Guardado exitoso")

    return {
        "prueba": "Crarpedidoinsumo",
        "estado": "ok",
    }
