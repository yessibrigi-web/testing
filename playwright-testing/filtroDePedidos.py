import re
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

    print("Iniciando sesión...")
    pagina.locator("button:visible").nth(0).click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(5000)

    # === SELECCIONAR EMPRESA ===
    print(f"Seleccionando empresa: {EMPRESA}...")
    pagina.locator("#ddlEmpresa").select_option(label=EMPRESA)
    pagina.wait_for_timeout(3000)

    # === INGRESAR (empresa/sucursal) ===
    print("Haciendo click en Ingresar...")
    boton_ingresar = pagina.locator("button:has-text('Ingresar'), input[value='Ingresar'], a:has-text('Ingresar'), :text('Ingresar')").first
    boton_ingresar.wait_for(state="visible", timeout=10000)
    boton_ingresar.click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(5000)

    # === NAVEGAR A PEDIDOS PROYECTO ===
    print("Navegando a ADPRO > Almacén > Pedidos > Pedidos proyecto...")
    pagina.locator("text=ADPRO").first.wait_for(state="visible", timeout=10000)
    pagina.locator("text=ADPRO").first.click()
    pagina.wait_for_timeout(2000)

    pagina.locator("text=Almacén").first.wait_for(state="visible", timeout=10000)
    pagina.locator("text=Almacén").first.click()
    pagina.wait_for_timeout(2000)

    pagina.locator("text=Pedidos").first.wait_for(state="visible", timeout=10000)
    pagina.locator("text=Pedidos").first.click()
    pagina.wait_for_timeout(2000)

    pagina.locator("text=Pedidos proyecto").last.wait_for(state="visible", timeout=10000)
    pagina.locator("text=Pedidos proyecto").last.click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(8000)

    # === OBTENER EL IFRAME DONDE ESTÁ LA TABLA ===
    frame = pagina.frames[1]

    # === PRUEBA: FILTRO DE PEDIDOS ===
    print("Iniciando prueba de filtro de pedidos...")

    # 1. Leer el primer pedido de la tabla (ej: "Pedido No. 30-109")
    primer_pedido = frame.locator("text=/Pedido No\\./").first
    primer_pedido.wait_for(state="visible", timeout=15000)
    texto_pedido = primer_pedido.inner_text()
    print(f"Pedido encontrado en tabla: {texto_pedido}")

    # Extraer el número completo (ej: "Pedido No. 30-109" -> "30-109")
    match = re.search(r"Pedido No\.\s*(.+)", texto_pedido)
    numero_pedido = match.group(1).strip() if match else texto_pedido
    print(f"Número de pedido a filtrar: {numero_pedido}")

    # 2. Click en botón "Filtrar" para abrir el drawer
    print("Abriendo filtro...")
    frame.locator("text=Filtrar").first.wait_for(state="visible", timeout=10000)
    frame.locator("text=Filtrar").first.click()
    pagina.wait_for_timeout(3000)

    # 3. Escribir el número en el input "Ingresar Pedido No."
    print(f"Escribiendo número de pedido: {numero_pedido}")
    input_pedido = frame.get_by_placeholder("Ingresar Pedido No.")
    input_pedido.wait_for(state="visible", timeout=10000)
    input_pedido.click()
    input_pedido.fill(numero_pedido)
    pagina.wait_for_timeout(1000)

    # 4. Click en botón "Consultar"
    print("Haciendo click en Consultar...")
    frame.locator("button:has-text('Consultar')").first.wait_for(state="visible", timeout=10000)
    frame.locator("button:has-text('Consultar')").first.click()
    pagina.wait_for_timeout(8000)

    # 5. Captura después de filtrar
    pagina.screenshot(path="filtro_resultado.png")
    print("Captura tomada: filtro_resultado.png")

    # 6. Verificar si la tabla tiene datos después de filtrar
    pedidos_visibles = frame.locator("text=/Pedido No\\./").all()
    cantidad_resultados = sum(1 for p in pedidos_visibles if p.is_visible())

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    es_ok = cantidad_resultados > 0
    resultado = "OK" if es_ok else "X"

    # 7. Generar reporte HTML
    with open("reporte_template.html", "r", encoding="utf-8") as f:
        template = f.read()

    total = 1
    exitosas = 1 if es_ok else 0
    fallidas = 0 if es_ok else 1
    porcentaje = round((exitosas / total) * 100)

    estado_class = "ok" if es_ok else "fail"
    estado_icono = (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>'
        if es_ok else
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
    )
    estado_texto = "Aprobada" if es_ok else "Fallida"
    resultado_obtenido = f"{cantidad_resultados} registro(s) en la tabla" if es_ok else "Sin resultados en la tabla"

    fila = f"""
                    <tr>
                        <td style="font-weight:600;color:var(--gray-500)">1</td>
                        <td><strong>Filtro de pedidos por numero</strong></td>
                        <td><span class="mono">{numero_pedido}</span></td>
                        <td>La tabla muestra solo el pedido filtrado</td>
                        <td>{resultado_obtenido}</td>
                        <td><span class="status-badge {estado_class}">{estado_icono} {estado_texto}</span></td>
                    </tr>"""

    pasos = ""
    pasos_lista = [
        ("Login", f"Ingreso con usuario <strong>{USUARIO}</strong>"),
        ("Empresa", f"Seleccion de empresa <strong>{EMPRESA}</strong>"),
        ("Navegacion", "Ruta: ADPRO &rarr; Almacen &rarr; Pedidos &rarr; Pedidos proyecto"),
        ("Lectura", f"Se tomo el primer pedido de la tabla: <strong>{texto_pedido}</strong>"),
        ("Filtro", f"Se abrio el drawer de filtro y se ingreso el numero <strong>{numero_pedido}</strong>"),
        ("Consulta", "Se hizo click en el boton <strong>Consultar</strong>"),
        ("Validacion", f"Se verifico la tabla: <strong>{resultado_obtenido}</strong>"),
    ]
    for i, (titulo, desc) in enumerate(pasos_lista, 1):
        pasos += f"""
                <div class="step">
                    <div class="step-number">{i}</div>
                    <div class="step-text"><strong>{titulo}:</strong> {desc}</div>
                </div>"""

    url_base = "www4.sincoerp.com"
    html = template.replace("{{FECHA}}", fecha)
    html = html.replace("{{TOTAL}}", str(total))
    html = html.replace("{{EXITOSAS}}", str(exitosas))
    html = html.replace("{{FALLIDAS}}", str(fallidas))
    html = html.replace("{{PORCENTAJE}}", str(porcentaje))
    html = html.replace("{{PROGRESS_CLASS}}", "success" if es_ok else "danger")
    html = html.replace("{{EMPRESA}}", EMPRESA)
    html = html.replace("{{USUARIO}}", USUARIO)
    html = html.replace("{{URL}}", url_base)
    html = html.replace("{{FILAS_TABLA}}", fila)
    html = html.replace("{{PASOS}}", pasos)

    with open("resultado_filtroDePedidos.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nResultado: {resultado}")
    print("Reporte guardado en: resultado_filtroDePedidos.html")

    pagina.wait_for_timeout(3000)
    navegador.close()
