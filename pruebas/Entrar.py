"""
Prueba: Entrar by CC
Módulo: Compras
"""


def ejecutar(pagina, frame, on_paso=None):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://core.sincoerp.com/SincoSoporte/Torre.html")
    
    page.get_by_title("Master").get_by_role("img").click()
    page.get_by_title("Clientes").locator("path").click()
    page.locator("#listWidgetClientes").get_by_role("textbox").click()
    page.locator("#listWidgetClientes").get_by_role("textbox").fill("conal")
    page.get_by_text("CONALTURA CONSTRUCCION Y VIVIENDA S.A.S.").click()
    page.get_by_text("Entornos").click()
    page.get_by_text("REPLICA_SincoConaltura").click()
    with page.expect_popup() as page1_info:
        page.get_by_text("Ingresar", exact=True).click()
    page1 = page1_info.value

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)