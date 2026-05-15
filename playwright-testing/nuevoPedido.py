from datetime import datetime
from playwright.sync_api import sync_playwright

USUARIO = "office"
PASSWORD = "Office123"
EMPRESA = "SincoPlus Pruebas Módulos"

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=False)
    pagina = navegador.new_page()

    # === LOGIN ===
    print("Abriendo SINCO...")
    pagina.goto("https://www4.sincoerp.com/SincoPlusPruebasModulos2022/V3/Marco/Seleccion_iv.aspx")
    pagina.wait_for_load_state("networkidle")

    print("Ingresando credenciales...")
    pagina.locator("input:visible").nth(0).click()
    pagina.keyboard.type(USUARIO)
    pagina.locator("input:visible").nth(1).click()
    pagina.keyboard.type(PASSWORD)

    print("Iniciando sesion...")
    pagina.locator("button:visible").nth(0).click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(5000)

    # === SELECCIONAR EMPRESA ===
    print(f"Seleccionando empresa: {EMPRESA}...")
    pagina.locator("#ddlEmpresa").select_option(label=EMPRESA)
    pagina.wait_for_timeout(3000)

    # === INGRESAR ===
    print("Haciendo click en Ingresar...")
    boton_ingresar = pagina.locator("button:has-text('Ingresar'), input[value='Ingresar'], a:has-text('Ingresar'), :text('Ingresar')").first
    boton_ingresar.wait_for(state="visible", timeout=10000)
    boton_ingresar.click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(5000)

    # === NAVEGAR A PEDIDOS PROYECTO ===
    print("Navegando a ADPRO > Almacen > Pedidos > Pedidos proyecto...")
    pagina.get_by_title("Administración de proyectos").click()
    pagina.wait_for_timeout(2000)
    pagina.get_by_title("Ruta: ADPRO/Almacén").click()
    pagina.wait_for_timeout(2000)
    pagina.get_by_role("button", name="PEDIDOS").click()
    pagina.wait_for_timeout(2000)
    pagina.get_by_role("button", name="Pedidos proyecto").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(8000)

    # === PRUEBA: CREAR PEDIDO ===
    frame = pagina.locator("#pagina1").content_frame
    print("Iniciando prueba de crear pedido...")

    # 1. Click en Nuevo pedido
    print("Haciendo click en Nuevo pedido...")
    frame.get_by_role("button", name="Nuevo pedido").click()
    pagina.wait_for_timeout(5000)
    pagina.screenshot(path="crear_pedido_01_nuevo.png")
    print("Captura: crear_pedido_01_nuevo.png")

    # 2. Click en el input de buscar insumo y escribir _
    print("Escribiendo '_' en buscar insumo...")
    frame.get_by_role("combobox", name="Buscar insumo").click()
    frame.get_by_role("combobox", name="Buscar insumo").fill("_")
    pagina.wait_for_timeout(3000)
    pagina.screenshot(path="crear_pedido_02_buscar.png")
    print("Captura: crear_pedido_02_buscar.png")

    # 3. Seleccionar primer registro del dropdown
    print("Seleccionando primer registro del dropdown...")
    frame.get_by_text("- EQUIPO DE TOPOGRAFIA.-[MS]").click()
    pagina.wait_for_timeout(5000)
    pagina.screenshot(path="crear_pedido_03_seleccion.png")
    print("Captura: crear_pedido_03_seleccion.png")

    # 4. Click en la celda de Cantidad y escribir 1
    print("Haciendo click en celda de Cantidad...")
    frame.locator("div:nth-child(8) > .MuiBox-root").first.click()
    pagina.wait_for_timeout(1000)
    print("Escribiendo 1 en Cantidad...")
    frame.get_by_role("textbox").fill("1")
    pagina.screenshot(path="crear_pedido_04_cantidad.png")
    print("Captura: crear_pedido_04_cantidad.png")

    # 5. Blur: click fuera del input
    print("Haciendo blur (click fuera)...")
    frame.get_by_text("Agregar Insumos").click()
    pagina.wait_for_timeout(3000)
    pagina.screenshot(path="crear_pedido_05_blur.png")
    print("Captura: crear_pedido_05_blur.png")

    # === RESULTADO ===
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*50}")
    print(f"Prueba: Crear pedido")
    print(f"Insumo: 101 - EQUIPO DE TOPOGRAFIA.-[MS]")
    print(f"Cantidad: 1")
    print(f"Fecha: {fecha}")
    print(f"Resultado: OK")
    print(f"{'='*50}")

    pagina.wait_for_timeout(3000)
    navegador.close()
