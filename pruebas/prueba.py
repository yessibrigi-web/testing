"""
Prueba: prueba
Módulo: Inventarios
"""


def ejecutar(pagina, frame, on_paso=None):
    # --- Tu código de prueba aquí ---

    if on_paso:
        on_paso("Paso 1")

    # Ejemplo: pagina.get_by_role("button", name="Guardar").click()

    return {
        "prueba": "prueba",
        "estado": "ok",
        "dato_entrada": "-",
        "esperado": "Flujo completo sin errores",
        "obtenido": "Flujo completado",
    }
