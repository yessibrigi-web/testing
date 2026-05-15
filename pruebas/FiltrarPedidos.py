"""
Prueba: Filtrar Pedidos
Módulo: Compras
"""
import re


def ejecutar(pagina, frame, on_paso=None):
    """
    Ejecuta la prueba 'Filtrarpedidos'.
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
    frame.get_by_role("button", name="Filtrar").click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Filtrar")
    frame.get_by_role("combobox", name="Buscar por insumo").click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Buscar por insumo")
    frame.get_by_role("combobox", name="Buscar por insumo").fill("_")
    pagina.wait_for_timeout(1000)
    frame.get_by_role("option", name="- EQUIPO DE TOPOGRAFIA.").locator("span").click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("- EQUIPO DE TOPOGRAFIA.")
    frame.get_by_role("button", name="Consultar").click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Consultar")
    frame.get_by_text("Total registros:").click(force=True)
    pagina.wait_for_timeout(3000)
    if on_paso: on_paso("Total registros:")

    return {
        "prueba": "Filtrarpedidos",
        "estado": "ok",
    }
