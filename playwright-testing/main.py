from playwright.sync_api import sync_playwright

USUARIO = "admin"
PASSWORD = "Admin123"

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=False)
    pagina = navegador.new_page()

    print("Abriendo SINCO...")
    pagina.goto("https://desarrollo.sincoerp.com/SincoOk/V3/Marco/Default_iv.aspx")
    pagina.wait_for_load_state("networkidle")

    print("Ingresando credenciales...")
    pagina.locator("input:visible").nth(0).click()
    pagina.keyboard.type(USUARIO)

    pagina.locator("input:visible").nth(1).click()
    pagina.keyboard.type(PASSWORD)

    print("Iniciando sesión...")
    pagina.locator("button:visible").nth(0).click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(5000)
    pagina.screenshot(path="paso1_despues_login.png")
    print("Captura tomada: paso1_despues_login.png")

    # Click en botón "Ingresar" (selección de empresa/sucursal)
    print("Haciendo click en Ingresar...")
    boton_ingresar = pagina.locator("button:has-text('Ingresar'), input[value='Ingresar'], a:has-text('Ingresar'), :text('Ingresar')").first
    boton_ingresar.wait_for(state="visible", timeout=10000)
    boton_ingresar.click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(5000)
    pagina.screenshot(path="paso2_despues_ingresar.png")
    print("Captura tomada: paso2_despues_ingresar.png")

    # Navegar a ADPRO > Almacén > Pedidos > Pedidos proyecto
    print("Navegando a ADPRO...")
    pagina.locator("text=ADPRO").first.wait_for(state="visible", timeout=10000)
    pagina.locator("text=ADPRO").first.click()
    pagina.wait_for_timeout(2000)

    print("Navegando a Almacén...")
    pagina.locator("text=Almacén").first.wait_for(state="visible", timeout=10000)
    pagina.locator("text=Almacén").first.click()
    pagina.wait_for_timeout(2000)

    print("Navegando a Pedidos...")
    pagina.locator("text=Pedidos").first.wait_for(state="visible", timeout=10000)
    pagina.locator("text=Pedidos").first.click()
    pagina.wait_for_timeout(2000)

    print("Navegando a Pedidos proyecto...")
    pagina.locator("text=Pedidos proyecto").last.wait_for(state="visible", timeout=10000)
    pagina.locator("text=Pedidos proyecto").last.click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(5000)
    pagina.screenshot(path="paso3_pedidos_proyecto.png")
    print("Captura tomada: paso3_pedidos_proyecto.png")

    pagina.wait_for_timeout(5000)
    navegador.close()
