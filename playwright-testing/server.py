import os
import re
import json
import queue
import base64
import threading
import importlib
from datetime import datetime
from flask import Flask, Response, send_file, jsonify, request
from playwright.sync_api import sync_playwright

app = Flask(__name__)

eventos = {}

USUARIO = "office"
PASSWORD = "Office123"
EMPRESA = "SincoPlus Pruebas Módulos"
URL_BASE = "https://www4.sincoerp.com/SincoPlusPruebasModulos2022/V3/Marco/Seleccion_iv.aspx"
PRUEBAS_DIR = os.path.join(os.path.dirname(__file__), "pruebas")


def enviar_evento(session_id, tipo, data):
    if session_id in eventos:
        eventos[session_id].put(json.dumps({"tipo": tipo, **data}))


def descubrir_pruebas():
    """Escanea la carpeta pruebas/ y retorna lista de pruebas disponibles."""
    pruebas = []
    if not os.path.isdir(PRUEBAS_DIR):
        return pruebas
    for archivo in sorted(os.listdir(PRUEBAS_DIR)):
        if archivo.endswith(".py") and archivo != "__init__.py":
            prueba_id = archivo[:-3]
            # Leer el docstring del archivo para obtener el nombre
            ruta = os.path.join(PRUEBAS_DIR, archivo)
            nombre = prueba_id.replace("_", " ").title()
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    contenido = f.read()
                match = re.search(r'Prueba:\s*(.+)', contenido)
                if match:
                    nombre = match.group(1).strip()
            except Exception:
                pass
            pruebas.append({"id": prueba_id, "nombre": nombre})
    return pruebas


def cargar_prueba(prueba_id):
    """Importa dinámicamente un modulo de prueba."""
    modulo = importlib.import_module(f"pruebas.{prueba_id}")
    importlib.reload(modulo)
    return modulo


def ejecutar_prueba_generica(session_id, usuario, password, empresa, url_base, prueba_id):
    """Runner genérico: login + navegacion + ejecuta la prueba grabada."""
    paso_actual = 0
    total_pasos = 9

    def captura(pagina):
        buf = pagina.screenshot()
        return base64.b64encode(buf).decode("utf-8")

    def paso(nombre, descripcion, screenshot_b64=None):
        nonlocal paso_actual
        paso_actual += 1
        porcentaje = round((paso_actual / total_pasos) * 100)
        data = {
            "paso": paso_actual,
            "total": total_pasos,
            "porcentaje": porcentaje,
            "nombre": nombre,
            "descripcion": descripcion,
        }
        if screenshot_b64:
            data["screenshot"] = screenshot_b64
        enviar_evento(session_id, "progreso", data)

    try:
        modulo = cargar_prueba(prueba_id)
    except Exception as e:
        enviar_evento(session_id, "error", {"mensaje": f"No se pudo cargar la prueba '{prueba_id}': {e}"})
        enviar_evento(session_id, "fin", {"exito": False})
        return

    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch(headless=True)
            pagina = navegador.new_page()

            # Paso 1: Abrir SINCO
            pagina.goto(url_base)
            pagina.wait_for_load_state("networkidle")
            paso("Conexion", "Pagina de SINCO cargada", captura(pagina))

            # Paso 2: Credenciales
            pagina.locator("input:visible").nth(0).click()
            pagina.keyboard.type(usuario)
            pagina.locator("input:visible").nth(1).click()
            pagina.keyboard.type(password)
            paso("Credenciales", f"Usuario {usuario} ingresado", captura(pagina))

            # Paso 3: Login
            pagina.locator("button:visible").nth(0).click()
            pagina.wait_for_load_state("networkidle")
            pagina.wait_for_timeout(5000)
            paso("Login", "Sesion iniciada correctamente", captura(pagina))

            # Paso 4: Empresa
            pagina.locator("#ddlEmpresa").select_option(label=empresa)
            pagina.wait_for_timeout(3000)
            paso("Empresa", f"Empresa seleccionada: {empresa}", captura(pagina))

            # Paso 5: Ingresar
            boton = pagina.locator("button:has-text('Ingresar'), input[value='Ingresar'], a:has-text('Ingresar'), :text('Ingresar')").first
            boton.wait_for(state="visible", timeout=10000)
            boton.click()
            pagina.wait_for_load_state("networkidle")
            pagina.wait_for_timeout(5000)
            paso("Ingresar", "Ingreso al sistema completado", captura(pagina))

            # Paso 6: Screenshot antes de la prueba
            paso("Inicio prueba", f"Ejecutando prueba: {prueba_id}", captura(pagina))

            # Contar pasos dinamicos del test para calcular el progreso total
            import inspect
            source = inspect.getsource(modulo.ejecutar)
            pasos_dinamicos = source.count("if on_paso:")
            total_pasos = 6 + pasos_dinamicos + 1  # 6 fijos + dinamicos + validacion

            # Callback para capturar screenshot en cada accion del test
            def on_paso_test(descripcion):
                paso(f"Prueba: {descripcion}", f"Accion completada: {descripcion}", captura(pagina))

            # Paso 7..N: Ejecutar la prueba grabada (navegacion + acciones)
            resultado = modulo.ejecutar(pagina, None, on_paso=on_paso_test)

            # Paso final: Validacion
            paso("Validacion", "Prueba finalizada", captura(pagina))

            navegador.close()

        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        resultado_evento = {
            "prueba": resultado.get("prueba", prueba_id),
            "dato_entrada": resultado.get("dato_entrada", "-"),
            "esperado": resultado.get("esperado", "Ejecucion sin errores"),
            "obtenido": resultado.get("obtenido", "Prueba completada correctamente"),
            "estado": resultado.get("estado", "ok"),
            "fecha": fecha,
            "empresa": empresa,
            "usuario": usuario,
        }
        enviar_evento(session_id, "resultado", resultado_evento)
        enviar_evento(session_id, "fin", {"exito": resultado.get("estado") == "ok"})

    except Exception as e:
        enviar_evento(session_id, "error", {"mensaje": str(e)})
        enviar_evento(session_id, "fin", {"exito": False})


@app.route("/")
def index():
    return send_file("dashboard.html")


@app.route("/config")
def config():
    return jsonify({
        "usuario": USUARIO,
        "password": PASSWORD,
        "empresa": EMPRESA,
        "url": URL_BASE,
    })


@app.route("/clientes")
def listar_clientes():
    ruta = os.path.join(os.path.dirname(__file__), "clientes.json")
    if not os.path.exists(ruta):
        return jsonify([])
    with open(ruta, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/pruebas")
def listar_pruebas_endpoint():
    return jsonify(descubrir_pruebas())


@app.route("/ejecutar", methods=["POST"])
def ejecutar():
    data = request.get_json() or {}
    usuario = data.get("usuario", USUARIO)
    password = data.get("password", PASSWORD)
    empresa = data.get("empresa", EMPRESA)
    url_base = data.get("url", URL_BASE)
    prueba_id = data.get("prueba")

    if not prueba_id:
        return jsonify({"error": "Falta el campo 'prueba'"}), 400

    # Verificar que la prueba existe
    pruebas = [p["id"] for p in descubrir_pruebas()]
    if prueba_id not in pruebas:
        return jsonify({"error": f"Prueba '{prueba_id}' no encontrada"}), 404

    session_id = str(datetime.now().timestamp())
    eventos[session_id] = queue.Queue()
    hilo = threading.Thread(
        target=ejecutar_prueba_generica,
        args=(session_id, usuario, password, empresa, url_base, prueba_id),
        daemon=True,
    )
    hilo.start()
    return jsonify({"session_id": session_id})


@app.route("/stream/<session_id>")
def stream(session_id):
    def generar():
        q = eventos.get(session_id)
        if not q:
            return
        while True:
            try:
                data = q.get(timeout=120)
                yield f"data: {data}\n\n"
                parsed = json.loads(data)
                if parsed["tipo"] == "fin":
                    del eventos[session_id]
                    break
            except queue.Empty:
                yield "data: {\"tipo\": \"ping\"}\n\n"

    return Response(generar(), mimetype="text/event-stream")


if __name__ == "__main__":
    print("Servidor iniciado en http://localhost:5050")
    app.run(debug=False, port=5050)
