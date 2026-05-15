"""
Prueba: Prueba Control
Módulo: Control
"""



def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page.get_by_title("Administración de proyectos").locator("#textomodulo").click()
    page.get_by_role("button", name="Control").click()
    page.get_by_role("button", name="Control del proyecto").click()
    page.locator("#pagina1").content_frame.get_by_role("button", name="Generar control").click()
    page.locator("#pagina1").content_frame.get_by_role("button", name="Aceptar").click()
    page.locator("#pagina1").content_frame.get_by_role("button", name="Consultar").click()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)