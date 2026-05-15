"""
server.py - Servidor Flask para Dashboard de Pruebas SINCO ERP
Login via Torre.html con dropdowns: Cliente → Entorno → Base de datos → Ejecutar

OPTIMIZADO v3: Login vía Playwright headless (una sola vez, ~3s),
luego SignalR HTTP puro para cargar todos los datos.
Dropdowns instantáneos desde memoria.
"""

import os
import re
import sys
import json
import unicodedata
import uuid
import time
import base64
import importlib
import threading
import traceback
from datetime import datetime

import requests as http_requests
from requests_ntlm import HttpNtlmAuth
from flask import Flask, jsonify, request, Response, send_from_directory
from playwright.sync_api import sync_playwright

app = Flask(__name__, static_folder=".", static_url_path="")

CONFIG = {
    "usuario":   "yessica.olaya",
    "password":  "Jeronimo2026",
    "url_torre": "https://core.sincoerp.com/SincoSoporte/Torre.html",
    "api_base":  "https://core.sincoerp.com/SincoSoporte",
}

SESIONES      = {}
SESIONES_LOCK = threading.Lock()

# Suprimir warnings de SSL
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ─────────────────────────────────────────────
# CLIENTE API SINCO (Login Playwright + SignalR HTTP)
# ─────────────────────────────────────────────

class SincoAPI:
    """Login con Playwright (maneja encriptación AES del cliente),
    luego usa HTTP puro para SignalR. Cachea todo en memoria."""

    def __init__(self, api_base, usuario, password, url_torre):
        self.api_base  = api_base.rstrip("/")
        self.usuario   = usuario
        self.password  = password
        self.url_torre = url_torre

        self.session = http_requests.Session()
        self.session.verify = False

        self.connection_token = None
        self.msg_id           = 0
        self._usuario_dominio = ""
        self._equipo          = ""
        self._equipo_id       = 0

        self._clientes  = []
        self._entornos  = []
        self._cargado   = False
        self._lock      = threading.Lock()

    # ── Login vía Playwright (captura cookies + datos de autenticación) ──

    def _login_via_playwright(self):
        """Abre Torre.html con Playwright headless, hace login,
        intercepta la respuesta de /API/Trabajadores/Validar para obtener
        los datos de autenticación, y transfiere las cookies a requests."""

        login_data = {}

        def capturar_login_response(response):
            """Intercepta la respuesta del API de login."""
            if "/API/Trabajadores/Validar" in response.url and response.status == 200:
                try:
                    login_data["response"] = response.json()
                except Exception:
                    pass

        print("  [API] Abriendo Torre.html (Playwright headless)...")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(ignore_https_errors=True)
            pagina  = context.new_page()

            # Interceptar respuesta del login
            pagina.on("response", capturar_login_response)

            # Hacer login en Torre.html (la página encripta el password con AES)
            pagina.goto(self.url_torre)
            pagina.wait_for_load_state("networkidle")
            pagina.get_by_role("textbox", name="UsuarioWindows").fill(self.usuario)
            pagina.get_by_role("textbox", name="Contraseña").fill(self.password)
            pagina.get_by_role("button", name="Ingresar con Windows").click()
            pagina.wait_for_load_state("networkidle")

            # Esperar a que la respuesta de login sea interceptada
            for _ in range(30):  # máximo 6 segundos
                if "response" in login_data:
                    break
                pagina.wait_for_timeout(200)

            # Dar un momento extra para que se establezcan todas las cookies
            pagina.wait_for_timeout(1000)

            # Transferir cookies del navegador a la sesión de requests
            cookies = context.cookies()
            for cookie in cookies:
                self.session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie.get("domain", ""),
                    path=cookie.get("path", "/"),
                )

            browser.close()

        # Extraer datos del login interceptado
        if "response" not in login_data:
            raise Exception("No se pudo interceptar la respuesta de login")

        data = login_data["response"]
        trabajador = data.get("trabajador", {})
        self._usuario_dominio = trabajador.get("UsuarioDominio", "")
        self._equipo          = trabajador.get("EquipoTrabajo", "")
        self._equipo_id       = trabajador.get("EquipoTrabajo_Id", 0)
        self._usuario_login   = trabajador.get("UsuarioLogin", "admin")

        print(f"  [API] Login exitoso: {trabajador.get('NombreCompleto', self.usuario)}")
        print(f"  [API] Cookies transferidas a HTTP ({len(cookies)} cookies)")

    # ── SignalR vía HTTP puro ──

    def _signalr_negotiate(self):
        params = {
            "clientProtocol": "1.5",
            "UserName": self._usuario_dominio,
            "EquipoTrabajo": self._equipo,
            "AppEmpresa": "sincosoporte",
            "connectionData": json.dumps([
                {"name": "myhub"},
                {"name": "releasemanager"}
            ]),
            "_": str(int(time.time() * 1000)),
        }
        url = f"{self.api_base}/API/signalr/negotiate"
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self.connection_token = data["ConnectionToken"]
        print(f"  [API] SignalR negociado (ConnectionId: {data.get('ConnectionId', '?')[:8]}...)")

    def _signalr_start(self):
        params = self._signalr_params()
        params["_"] = str(int(time.time() * 1000))
        url = f"{self.api_base}/API/signalr/start"
        resp = self.session.get(url, params=params, timeout=30)
        resp.raise_for_status()

    def _signalr_params(self):
        return {
            "transport": "serverSentEvents",
            "clientProtocol": "1.5",
            "UserName": self._usuario_dominio,
            "EquipoTrabajo": self._equipo,
            "AppEmpresa": "sincosoporte",
            "connectionToken": self.connection_token,
            "connectionData": json.dumps([
                {"name": "myhub"},
                {"name": "releasemanager"}
            ]),
        }

    def _signalr_send(self, hub, method, args=None):
        self.msg_id += 1
        payload = json.dumps({
            "H": hub,
            "M": method,
            "A": args or [],
            "I": self.msg_id,
        })
        url = f"{self.api_base}/API/signalr/send"
        resp = self.session.post(
            url,
            params=self._signalr_params(),
            data={"data": payload},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if "R" in data:
            return data["R"]
        return data

    # ── Conectar y cargar datos ──

    def conectar_y_cargar(self):
        with self._lock:
            if self._cargado:
                return

            t0 = time.time()
            print("  [API] Conectando a SINCO Soporte...")

            # Paso 1: Login vía Playwright (solo si no hay sesión)
            if not self._usuario_dominio:
                self._login_via_playwright()
            else:
                print("  [API] Sesión de login ya existe, reutilizando...")

            # Paso 2: SignalR vía HTTP puro (con reintentos)
            for intento in range(3):
                try:
                    self._signalr_negotiate()
                    self._signalr_start()
                    break
                except Exception as e:
                    print(f"  [API] SignalR intento {intento+1}/3 falló: {e}")
                    if intento == 2:
                        raise
                    time.sleep(2)
                    # Reintentar login si el negotiate falla
                    if intento == 1:
                        print("  [API] Re-login...")
                        self._login_via_playwright()

            # Paso 3: Cargar todos los datos de una vez
            print("  [API] Cargando clientes...")
            self._clientes = self._signalr_send("clientes", "GetClientes") or []
            print(f"  [API] → {len(self._clientes)} clientes")

            print("  [API] Cargando entornos...")
            self._entornos = self._signalr_send("entornos", "GetEntornos") or []
            print(f"  [API] → {len(self._entornos)} entornos")

            elapsed = time.time() - t0
            self._cargado = True
            print(f"  [API] ✓ Datos listos en {elapsed:.1f}s — dropdowns instantáneos")

    def recargar(self):
        with self._lock:
            self._cargado = False
        self.conectar_y_cargar()

    # ── Consultas (filtro local, instantáneo) ──

    def buscar_clientes(self, q):
        self.conectar_y_cargar()
        q_lower = q.lower()
        resultados = []
        for c in self._clientes:
            nombre = c.get("Cliente", "")
            if q_lower in nombre.lower():
                resultados.append({
                    "id":     nombre,
                    "nombre": nombre,
                    "nit":    c.get("Nit", ""),
                    "ciudad": c.get("Ciudad", ""),
                    "id_cliente": c.get("IdCliente"),
                })
        return resultados[:50]

    def _normalizar(self, texto):
        sin_tildes = unicodedata.normalize('NFD', texto)
        sin_tildes = ''.join(c for c in sin_tildes if unicodedata.category(c) != 'Mn')
        return re.sub(r'[.\s]+', ' ', sin_tildes.lower()).strip()

    def obtener_entornos(self, cliente_nombre):
        self.conectar_y_cargar()
        cliente_norm = self._normalizar(cliente_nombre)

        # Extraer palabras clave del nombre del cliente (las más significativas)
        palabras_cliente = [p for p in cliente_norm.split() if len(p) > 2]

        entornos = []
        for e in self._entornos:
            nombre_entorno_cliente = self._normalizar(e.get("NombreCliente", ""))

            # Match: al menos 70% de las palabras del cliente aparecen en NombreCliente del entorno
            if not nombre_entorno_cliente:
                continue
            coincidencias = sum(1 for p in palabras_cliente if p in nombre_entorno_cliente)
            if coincidencias < len(palabras_cliente) * 0.7:
                continue

            nombre = e.get("Nombre", "")
            tipo = e.get("Tipo", "Otro")

            if "PRBINT" in nombre or "PRB" in nombre:
                tipo = "Pruebas"
            elif "REPLICA_" in nombre or "Replica_" in nombre:
                tipo = "Réplica"

            nombre_display = re.sub(r'^REPLICA_', '', nombre, flags=re.IGNORECASE)
            nombre_display = re.sub(r'_PRBINT$', '', nombre_display, flags=re.IGNORECASE)

            entornos.append({
                "id":     nombre,
                "nombre": f"{tipo} — {nombre_display}",
                "tipo":   tipo,
                "url":    e.get("URL", ""),
                "id_entorno": e.get("Id"),
            })

        return entornos

    def obtener_bases(self, cliente_nombre, entorno_nombre):
        self.conectar_y_cargar()

        for e in self._entornos:
            if e.get("Nombre", "") == entorno_nombre:
                bases = []
                for bd in e.get("BasesDatos", []):
                    nombre_bd = bd.get("Nombre", bd.get("Catalogo", ""))
                    nombre_bd = re.sub(r'^REPLICA\s+', '', nombre_bd, flags=re.IGNORECASE)
                    nombre_bd = re.sub(r'^PRUEBAS\s+', '', nombre_bd, flags=re.IGNORECASE)
                    bases.append({
                        "id":       bd.get("Id", ""),
                        "catalogo": bd.get("Catalogo", ""),
                        "nombre":   nombre_bd,
                        "tipo":     "Principal" if bd.get("Principal") else "Secundaria",
                    })
                return bases

        return []

    # ── Login directo al entorno ERP (Chrome off-screen + form POST) ──

    def obtener_key_login(self):
        """Llama obtenerKeyLoginCentralizado via SignalR para generar la key en el servidor."""
        self.conectar_y_cargar()
        resultado = self._signalr_send(
            "myhub", "obtenerKeyLoginCentralizado", [self._usuario_dominio]
        )
        print(f"  [API] obtenerKeyLoginCentralizado → {len(resultado) if isinstance(resultado, list) else '?'} entornos")
        return resultado

    def _obtener_key_via_torre(self):
        """Abre Torre.html mínimamente (headless) para obtener user_central_key."""
        key = None
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(ignore_https_errors=True)
            pagina = context.new_page()

            pagina.goto(self.url_torre)
            pagina.wait_for_load_state("networkidle")
            pagina.get_by_role("textbox", name="UsuarioWindows").fill(self.usuario)
            pagina.get_by_role("textbox", name="Contraseña").fill(self.password)
            pagina.get_by_role("button", name="Ingresar con Windows").click()
            pagina.wait_for_load_state("networkidle")
            pagina.wait_for_timeout(2000)

            # Esperar a que user_central_key esté disponible
            for _ in range(20):
                key = pagina.evaluate("() => window.user_central_key || null")
                if key:
                    break
                pagina.wait_for_timeout(300)

            browser.close()

        return key

    def login_entorno_chrome(self, entorno_url, bd_id="", bd_catalogo="", bd_nombre="",
                              on_progreso=None):
        """
        Login al entorno ERP usando Chrome off-screen (~12s).
        1. Abre Torre en Chrome (necesario para NTLM), hace login (~6s)
        2. Lee user_central_key (ya disponible post-login)
        3. Crea form POST directo a Login.aspx (sin navegar UI de Torre)
        4. Sigue redirects hasta Seleccion_iv.aspx → selecciona empresa
        Retorna (url_final, storage_state).
        """
        t0 = time.time()

        login_url = entorno_url
        if not login_url.endswith("Login.aspx"):
            login_url = re.sub(r'/V3/Marco/.*$', '/V3/Marco/Login.aspx', login_url)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=False,
                channel="chrome",
                args=["--window-position=-32000,-32000", "--window-size=1,1"],
            )
            context = browser.new_context(ignore_https_errors=True)
            pagina = context.new_page()

            # ── Paso 1: Login en Torre (obtiene NTLM + keyC) ──
            if on_progreso:
                on_progreso("Login en Torre...")
            print(f"  [LOGIN] Abriendo Torre...")
            pagina.goto(self.url_torre)
            pagina.wait_for_load_state("networkidle")
            pagina.get_by_role("textbox", name="UsuarioWindows").fill(self.usuario)
            pagina.get_by_role("textbox", name="Contraseña").fill(self.password)
            pagina.get_by_role("button", name="Ingresar con Windows").click()
            pagina.wait_for_load_state("networkidle")
            pagina.wait_for_timeout(2000)

            # ── Paso 2: Leer key (ya disponible tras login) ──
            key_c = None
            for _ in range(20):
                key_c = pagina.evaluate("() => window.user_central_key || null")
                if key_c:
                    break
                pagina.wait_for_timeout(300)

            if not key_c:
                raise Exception("No se pudo obtener user_central_key tras login en Torre")

            # Leer también usuario_dominio y usuario_login del JS
            usu_dominio = pagina.evaluate(
                "() => window.trabajador ? window.trabajador.UsuarioDominio : null"
            ) or self._usuario_dominio or f"sinco\\{self.usuario}"
            usu_login = pagina.evaluate(
                "() => window.trabajador ? window.trabajador.UsuarioLogin : null"
            ) or self._usuario_login or "admin"

            print(f"  [LOGIN] keyC: {key_c[:20]}... usuDom: {usu_dominio} usuLogin: {usu_login}")
            print(f"  [LOGIN] Torre login OK ({time.time()-t0:.1f}s)")

            # ── Paso 3: Form POST directo a Login.aspx (como hace Torre) ──
            if on_progreso:
                on_progreso("Ingresando al entorno...")

            # Escapar backslashes para JS
            usu_dominio_js = usu_dominio.replace("\\", "\\\\")

            # Crear form y abrir popup (exactamente como Torre)
            with pagina.expect_popup(timeout=30000) as popup_info:
                pagina.evaluate(f"""() => {{
                    const form = document.createElement('form');
                    form.method = 'post';
                    form.action = '{login_url}';
                    form.target = '_blank';

                    const fields = {{
                        'keyC': '{key_c}',
                        'ingreso': '0',
                        'usuDominio': '{usu_dominio_js}',
                        'usuario': '{usu_login}'
                    }};

                    for (const [name, value] of Object.entries(fields)) {{
                        const input = document.createElement('input');
                        input.type = 'hidden';
                        input.name = name;
                        input.value = value;
                        form.appendChild(input);
                    }}

                    document.body.appendChild(form);
                    form.submit();
                }}""")

            popup = popup_info.value

            # Esperar los saltos: Login.aspx → Seleccion.aspx → Seleccion_iv.aspx
            try:
                popup.wait_for_url("**/Seleccion_iv.aspx", timeout=30000)
            except Exception:
                pass
            popup.wait_for_load_state("networkidle")
            popup.wait_for_timeout(1500)

            url_actual = popup.url
            print(f"  [LOGIN] Popup en: {url_actual}")

            # ── Paso 4: Seleccionar empresa si estamos en Seleccion ──
            if "Seleccion" in url_actual and (bd_id or bd_catalogo or bd_nombre):
                if on_progreso:
                    on_progreso("Seleccionando empresa...")
                popup.locator("#ddlEmpresa").wait_for(state="visible", timeout=15000)
                popup.wait_for_timeout(500)
                seleccionada = seleccionar_empresa_dropdown(popup, bd_id, bd_catalogo, bd_nombre)
                print(f"  [LOGIN] Empresa: {seleccionada}")

                popup.get_by_role("button", name="Ingresar").click()
                popup.wait_for_url("**/Default_iv.aspx", timeout=30000)
                popup.wait_for_load_state("networkidle")
                popup.wait_for_timeout(1500)
            elif "Seleccion" in url_actual:
                # Sin BD seleccionada, usar la primera empresa y darle Ingresar
                if on_progreso:
                    on_progreso("Ingresando con empresa por defecto...")
                popup.locator("#ddlEmpresa").wait_for(state="visible", timeout=15000)
                popup.get_by_role("button", name="Ingresar").click()
                popup.wait_for_url("**/Default_iv.aspx", timeout=30000)
                popup.wait_for_load_state("networkidle")
                popup.wait_for_timeout(1500)

            url_erp = popup.url
            estado_sesion = context.storage_state()

            elapsed = time.time() - t0
            print(f"  [LOGIN] OK: {url_erp}")
            print(f"  [LOGIN] {len(estado_sesion.get('cookies',[]))} cookies en {elapsed:.1f}s")

            browser.close()

        return url_erp, estado_sesion


# Instancia global
sinco_api = SincoAPI(
    api_base=CONFIG["api_base"],
    usuario=CONFIG["usuario"],
    password=CONFIG["password"],
    url_torre=CONFIG["url_torre"],
)


# ─────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────

def capturar_screenshot(pagina):
    try:
        return base64.b64encode(pagina.screenshot(type="png")).decode("utf-8")
    except Exception:
        return None


def descubrir_pruebas():
    pruebas = []
    carpeta = os.path.join(os.path.dirname(__file__), "pruebas")
    if not os.path.isdir(carpeta):
        return pruebas
    for archivo in sorted(os.listdir(carpeta)):
        if archivo.startswith("_") or not archivo.endswith(".py"):
            continue
        ruta = os.path.join(carpeta, archivo)
        with open(ruta, encoding="utf-8") as f:
            contenido = f.read()
        if "def ejecutar(" in contenido:
            nombre_id = archivo.replace(".py", "")
            match = re.search(r'Prueba:\s*(.+)', contenido)
            nombre_display = match.group(1).strip() if match else nombre_id
            match_mod = re.search(r'Módulo:\s*(.+)', contenido)
            modulo = match_mod.group(1).strip() if match_mod else "Sin categoría"
            pruebas.append({"id": nombre_id, "nombre": nombre_display, "modulo": modulo})
    return pruebas


def hacer_login_torre(pagina):
    """Login en Torre.html (usado solo por _ejecutar_prueba)."""
    pagina.goto(CONFIG["url_torre"])
    pagina.wait_for_load_state("networkidle")
    pagina.get_by_role("textbox", name="UsuarioWindows").fill(CONFIG["usuario"])
    pagina.get_by_role("textbox", name="Contraseña").fill(CONFIG["password"])
    pagina.get_by_role("button", name="Ingresar con Windows").click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(2000)
    pagina.get_by_title("Master").get_by_role("img").click()
    pagina.wait_for_timeout(1000)


def buscar_y_seleccionar_cliente(pagina, cliente):
    """Busca y selecciona un cliente en Torre.html (usado solo por _ejecutar_prueba)."""
    pagina.get_by_title("Clientes", exact=True).locator("path").click()
    pagina.wait_for_timeout(1500)
    palabras = cliente.split()[:2]
    pagina.locator("#listWidgetClientes").get_by_role("textbox").fill(" ".join(palabras))
    pagina.wait_for_timeout(2000)
    pagina.get_by_role("option").locator("div").filter(
        has_text=palabras[0]
    ).nth(1).click()
    pagina.wait_for_timeout(1500)


def seleccionar_empresa_dropdown(pagina, bd_id, bd_catalogo, bd_nombre):
    """Selecciona una empresa en #ddlEmpresa.
    NOTA: Todos los <option> tienen value='1', así que se selecciona por label (texto).
    Prioridad: nombre exacto → case-insensitive → sin prefijo REPLICA → parcial → palabras.
    """
    # Obtener todas las opciones del dropdown
    opciones = pagina.locator("#ddlEmpresa option").all()
    labels = []
    for opt in opciones:
        text = opt.text_content().strip()
        if text:
            labels.append(text)

    print(f"  [MATCH] bd_nombre='{bd_nombre}' ({len(labels)} opciones)")

    def seleccionar(texto_label):
        pagina.locator("#ddlEmpresa").select_option(label=texto_label)

    # 1. Match por nombre exacto
    if bd_nombre:
        for text in labels:
            if text == bd_nombre:
                seleccionar(text)
                return f"(nombre exacto) {text}"

    # 2. Match case-insensitive
    if bd_nombre:
        bd_lower = bd_nombre.lower()
        for text in labels:
            if text.lower() == bd_lower:
                seleccionar(text)
                return f"(case-insensitive) {text}"

    # 3. Limpiar prefijo REPLICA del nombre y comparar
    if bd_nombre:
        bd_limpio = re.sub(r'^REPLICA[_ ]*', '', bd_nombre, flags=re.IGNORECASE).strip()
        bd_limpio_lower = bd_limpio.lower()
        for text in labels:
            if text.lower() == bd_limpio_lower:
                seleccionar(text)
                return f"(sin prefijo) {text}"

        # 4. Contención parcial
        for text in labels:
            text_lower = text.lower()
            if bd_limpio_lower in text_lower or text_lower in bd_limpio_lower:
                seleccionar(text)
                return f"(parcial) {text}"

        # 5. Palabras clave (60%+ coincidencia)
        palabras_bd = [p for p in bd_limpio_lower.split() if len(p) > 2]
        mejor_match, mejor_score = None, 0
        for text in labels:
            text_lower = text.lower()
            coincidencias = sum(1 for p in palabras_bd if p in text_lower)
            score = coincidencias / max(len(palabras_bd), 1)
            if score > mejor_score:
                mejor_score = score
                mejor_match = text
        if mejor_match and mejor_score >= 0.6:
            seleccionar(mejor_match)
            return f"(palabras {mejor_score:.0%}) {mejor_match}"

    print(f"  [MATCH] NO se encontró match. Opciones: {labels[:5]}")
    raise Exception(f"No se encontró la empresa en el dropdown. Nombre={bd_nombre}. Opciones: {labels[:5]}")


# ─────────────────────────────────────────────
# ENDPOINTS DROPDOWNS (VÍA API — INSTANTÁNEOS)
# ─────────────────────────────────────────────

@app.route("/torre/clientes")
def get_clientes():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    try:
        return jsonify(sinco_api.buscar_clientes(q))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/torre/entornos")
def get_entornos():
    cliente = request.args.get("cliente", "").strip()
    if not cliente:
        return jsonify([])
    try:
        return jsonify(sinco_api.obtener_entornos(cliente))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/torre/bases")
def get_bases():
    cliente    = request.args.get("cliente", "").strip()
    entorno_id = request.args.get("entorno_id", "").strip()
    if not cliente or not entorno_id:
        return jsonify([])
    try:
        return jsonify(sinco_api.obtener_bases(cliente, entorno_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# ENDPOINTS PRINCIPALES
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "dashboard.html")


@app.route("/config")
def get_config():
    return jsonify({"usuario": CONFIG["usuario"]})


@app.route("/debug/ingresar")
def debug_ingresar():
    """Captura TODOS los saltos, redirects, navegaciones y requests del popup al Ingresar."""
    cliente = request.args.get("cliente", "").strip()
    entorno_id = request.args.get("entorno_id", "").strip()
    if not cliente or not entorno_id:
        return jsonify({"error": "Usa ?cliente=X&entorno_id=Y"})

    peticiones = []
    navegaciones = []   # URLs por las que pasa el popup (saltos)
    redirects = []      # Redirects HTTP (301, 302, etc.)

    def capturar_request(req):
        info = {
            "method": req.method,
            "url": req.url,
            "resource_type": req.resource_type,
            "is_navigation": req.is_navigation_request(),
            "redirected_from": req.redirected_from.url if req.redirected_from else None,
            "post_data": req.post_data[:500] if req.post_data else None,
        }
        peticiones.append(info)
        if req.is_navigation_request():
            navegaciones.append({
                "url": req.url,
                "method": req.method,
                "redirected_from": req.redirected_from.url if req.redirected_from else None,
            })

    def capturar_response(resp):
        for p in peticiones:
            if p["url"] == resp.url and "status" not in p:
                p["status"] = resp.status
                p["status_text"] = resp.status_text
                # Capturar header Location en redirects
                location = resp.headers.get("location", "")
                if location:
                    p["redirect_location"] = location
                if resp.status in (301, 302, 303, 307, 308):
                    redirects.append({
                        "from": resp.url,
                        "to": location,
                        "status": resp.status,
                    })
                break

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--window-position=-32000,-32000", "--window-size=1,1"],
        )
        context = browser.new_context(ignore_https_errors=True)
        pagina = context.new_page()

        # Login Torre
        hacer_login_torre(pagina)
        buscar_y_seleccionar_cliente(pagina, cliente)

        # Seleccionar entorno
        pagina.locator(".contenedor-opcion > .siguienteIcon").first.click()
        pagina.wait_for_timeout(2000)
        pagina.get_by_role("option", name=f"_ {entorno_id}").get_by_role("img").nth(2).click()
        pagina.wait_for_timeout(1500)

        # Activar interceptación ANTES de hacer clic en Ingresar
        pagina.on("request", capturar_request)
        pagina.on("response", capturar_response)

        # Clic en Ingresar
        with pagina.expect_popup() as popup_info:
            pagina.locator("section").filter(
                has_text=re.compile(r"^IngresarAbrir entorno$")
            ).first.click()

        popup = popup_info.value

        # Interceptar también las peticiones del popup
        popup.on("request", capturar_request)
        popup.on("response", capturar_response)

        # Rastrear CADA cambio de URL en el popup
        url_changes = [{"url": popup.url, "momento": "popup_inicial"}]

        def on_frame_nav(frame):
            if frame == popup.main_frame:
                url_changes.append({"url": frame.url, "momento": "frame_navigated"})

        popup.on("framenavigated", on_frame_nav)

        popup.wait_for_load_state("networkidle")
        popup.wait_for_timeout(3000)

        url_changes.append({"url": popup.url, "momento": "final"})

        # Capturar título y contenido básico de la página final
        titulo_final = popup.title()
        url_final = popup.url

        browser.close()

    # Filtrar requests de navegación (los saltos)
    nav_requests = [p for p in peticiones if p.get("is_navigation")]

    # Filtrar requests relevantes (no assets)
    relevantes = [p for p in peticiones if not any(
        ext in p["url"].lower() for ext in ['.css', '.js', '.png', '.jpg', '.gif', '.ico', '.woff', '.svg']
    )]

    return jsonify({
        "resumen": {
            "url_final": url_final,
            "titulo_final": titulo_final,
            "total_peticiones": len(peticiones),
            "total_navegaciones": len(nav_requests),
            "total_redirects": len(redirects),
        },
        "saltos_url_popup": url_changes,
        "redirects_http": redirects,
        "navegaciones": nav_requests,
        "peticiones_relevantes": relevantes,
    })


@app.route("/pruebas")
def get_pruebas():
    return jsonify(descubrir_pruebas())


@app.route("/torre/debug")
def debug_cliente():
    """Endpoint de diagnóstico para ver datos crudos de un cliente."""
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify({"error": "Usa ?q=nombre para buscar"})

    sinco_api.conectar_y_cargar()

    # Buscar cliente
    cliente_match = None
    for c in sinco_api._clientes:
        if q in c.get("Cliente", "").lower():
            cliente_match = c
            break

    if not cliente_match:
        return jsonify({"error": f"No se encontró cliente con '{q}'"})

    id_cliente = cliente_match.get("IdCliente")

    # Buscar entornos por EmpresaId == IdCliente
    entornos_por_empresa = [e for e in sinco_api._entornos if e.get("EmpresaId") == id_cliente]

    # Buscar entornos por NombreCliente (alternativo)
    nombre_cliente = cliente_match.get("Cliente", "")
    entornos_por_nombre = [e for e in sinco_api._entornos if nombre_cliente.lower() in e.get("NombreCliente", "").lower()]

    # Buscar entornos por nombre del entorno o cualquier campo que contenga el query
    entornos_por_texto = []
    for e in sinco_api._entornos:
        e_str = json.dumps(e, ensure_ascii=False).lower()
        if q in e_str:
            entornos_por_texto.append({
                k: e.get(k) for k in ["Id", "Nombre", "NombreCliente", "EmpresaId", "Tipo", "URL"]
            })

    return jsonify({
        "cliente": {
            "IdCliente": id_cliente,
            "Cliente": nombre_cliente,
            "Nit": cliente_match.get("Nit"),
        },
        "entornos_por_EmpresaId": [{"Id": e.get("Id"), "Nombre": e.get("Nombre"), "EmpresaId": e.get("EmpresaId"), "NombreCliente": e.get("NombreCliente")} for e in entornos_por_empresa],
        "entornos_por_NombreCliente": [{"Id": e.get("Id"), "Nombre": e.get("Nombre"), "EmpresaId": e.get("EmpresaId"), "NombreCliente": e.get("NombreCliente")} for e in entornos_por_nombre],
        "entornos_por_texto_libre": entornos_por_texto[:20],
        "total_entornos_EmpresaId": len(entornos_por_empresa),
        "total_entornos_NombreCliente": len(entornos_por_nombre),
        "total_entornos_texto": len(entornos_por_texto),
    })


@app.route("/torre/reset", methods=["POST"])
def reset_torre():
    """Fuerza recarga de datos desde la API."""
    try:
        sinco_api.recargar()
        return jsonify({"ok": True, "mensaje": "Datos recargados desde la API"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# ENDPOINTS EDITOR DE CÓDIGO
# ─────────────────────────────────────────────

@app.route("/prueba/codigo")
def get_codigo():
    """Lee el código fuente de una prueba."""
    prueba_id = request.args.get("id", "").strip()
    if not prueba_id:
        return jsonify({"error": "Falta el parámetro id"}), 400
    ruta = os.path.join(os.path.dirname(__file__), "pruebas", f"{prueba_id}.py")
    if not os.path.isfile(ruta):
        return jsonify({"error": f"No existe {prueba_id}.py"}), 404
    with open(ruta, encoding="utf-8") as f:
        codigo = f.read()
    return jsonify({"id": prueba_id, "codigo": codigo})


@app.route("/prueba/codigo", methods=["POST"])
def guardar_codigo():
    """Guarda el código fuente de una prueba existente."""
    data = request.get_json()
    prueba_id = data.get("id", "").strip()
    codigo = data.get("codigo", "")
    if not prueba_id:
        return jsonify({"error": "Falta el parámetro id"}), 400
    ruta = os.path.join(os.path.dirname(__file__), "pruebas", f"{prueba_id}.py")
    if not os.path.isfile(ruta):
        return jsonify({"error": f"No existe {prueba_id}.py"}), 404
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(codigo)
    return jsonify({"ok": True, "mensaje": f"{prueba_id}.py guardado"})


@app.route("/prueba/nueva", methods=["POST"])
def crear_prueba():
    """Crea una nueva prueba con la plantilla base."""
    data = request.get_json()
    nombre_archivo = data.get("nombre", "").strip()
    modulo = data.get("modulo", "Sin categoría").strip()
    nombre_display = data.get("display", nombre_archivo).strip()

    if not nombre_archivo:
        return jsonify({"error": "Falta el nombre del archivo"}), 400

    # Limpiar nombre (solo alfanuméricos y _)
    nombre_limpio = re.sub(r'[^a-zA-Z0-9_]', '', nombre_archivo)
    if not nombre_limpio:
        return jsonify({"error": "Nombre inválido"}), 400

    ruta = os.path.join(os.path.dirname(__file__), "pruebas", f"{nombre_limpio}.py")
    if os.path.isfile(ruta):
        return jsonify({"error": f"{nombre_limpio}.py ya existe"}), 409

    plantilla = f'''"""
Prueba: {nombre_display}
Módulo: {modulo}
"""


def ejecutar(pagina, frame, on_paso=None):
    # --- Tu código de prueba aquí ---

    if on_paso:
        on_paso("Paso 1")

    # Ejemplo: pagina.get_by_role("button", name="Guardar").click()

    return {{
        "prueba": "{nombre_display}",
        "estado": "ok",
        "dato_entrada": "-",
        "esperado": "Flujo completo sin errores",
        "obtenido": "Flujo completado",
    }}
'''
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(plantilla)

    return jsonify({"ok": True, "id": nombre_limpio, "mensaje": f"{nombre_limpio}.py creado"})


@app.route("/prueba/eliminar", methods=["POST"])
def eliminar_prueba():
    """Elimina una prueba."""
    data = request.get_json()
    prueba_id = data.get("id", "").strip()
    if not prueba_id:
        return jsonify({"error": "Falta el parámetro id"}), 400
    ruta = os.path.join(os.path.dirname(__file__), "pruebas", f"{prueba_id}.py")
    if not os.path.isfile(ruta):
        return jsonify({"error": f"No existe {prueba_id}.py"}), 404
    os.remove(ruta)
    return jsonify({"ok": True, "mensaje": f"{prueba_id}.py eliminado"})


@app.route("/grabar", methods=["POST"])
def grabar():
    """Lanza Playwright Codegen autenticado en el entorno via HTTP+NTLM directo."""
    import subprocess
    data = request.get_json() or {}
    cliente      = data.get("cliente", "").strip()
    entorno_id   = data.get("entorno_id", "").strip()
    entorno_url  = data.get("entorno_url", "").strip()
    bd_id        = data.get("bd_id", "")
    bd_catalogo  = data.get("bd_catalogo", "").strip()
    bd_nombre    = data.get("bd_nombre", "").strip()

    if not cliente or not entorno_id:
        return jsonify({"error": "Selecciona cliente y entorno antes de grabar"}), 400
    if not entorno_url:
        return jsonify({"error": "No se encontró la URL del entorno"}), 400

    def _grabar_bg():
        try:
            print(f"  [GRABAR] Login via Chrome (mismo navegador)...")

            login_url_g = entorno_url
            if not login_url_g.endswith("Login.aspx"):
                login_url_g = re.sub(r'/V3/Marco/.*$', '/V3/Marco/Login.aspx', login_url_g)

            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=False,
                    channel="chrome",
                )
                context = browser.new_context(ignore_https_errors=True)
                pagina_torre = context.new_page()

                # Login en Torre
                print(f"  [GRABAR] Login en Torre...")
                pagina_torre.goto(sinco_api.url_torre)
                pagina_torre.wait_for_load_state("networkidle")
                pagina_torre.get_by_role("textbox", name="UsuarioWindows").fill(sinco_api.usuario)
                pagina_torre.get_by_role("textbox", name="Contraseña").fill(sinco_api.password)
                pagina_torre.get_by_role("button", name="Ingresar con Windows").click()
                pagina_torre.wait_for_load_state("networkidle")
                pagina_torre.wait_for_timeout(2000)

                # Leer key
                key_c = None
                for _ in range(20):
                    key_c = pagina_torre.evaluate("() => window.user_central_key || null")
                    if key_c:
                        break
                    pagina_torre.wait_for_timeout(300)

                if not key_c:
                    raise Exception("No se pudo obtener user_central_key")

                usu_dominio = pagina_torre.evaluate(
                    "() => window.trabajador ? window.trabajador.UsuarioDominio : null"
                ) or sinco_api._usuario_dominio or f"sinco\\{sinco_api.usuario}"
                usu_login = pagina_torre.evaluate(
                    "() => window.trabajador ? window.trabajador.UsuarioLogin : null"
                ) or getattr(sinco_api, '_usuario_login', 'admin') or "admin"

                print(f"  [GRABAR] keyC: {key_c[:20]}...")

                # Form POST directo
                usu_dominio_js = usu_dominio.replace("\\", "\\\\")
                with pagina_torre.expect_popup(timeout=30000) as popup_info:
                    pagina_torre.evaluate(f"""() => {{
                        const form = document.createElement('form');
                        form.method = 'post';
                        form.action = '{login_url_g}';
                        form.target = '_blank';
                        const fields = {{
                            'keyC': '{key_c}',
                            'ingreso': '0',
                            'usuDominio': '{usu_dominio_js}',
                            'usuario': '{usu_login}'
                        }};
                        for (const [name, value] of Object.entries(fields)) {{
                            const input = document.createElement('input');
                            input.type = 'hidden';
                            input.name = name;
                            input.value = value;
                            form.appendChild(input);
                        }}
                        document.body.appendChild(form);
                        form.submit();
                    }}""")

                popup = popup_info.value
                try:
                    popup.wait_for_url("**/Seleccion_iv.aspx", timeout=30000)
                except Exception:
                    pass
                popup.wait_for_load_state("networkidle")
                popup.wait_for_timeout(1500)

                url_actual = popup.url
                print(f"  [GRABAR] Popup en: {url_actual}")

                # Seleccionar empresa
                if "Seleccion" in url_actual:
                    popup.locator("#ddlEmpresa").wait_for(state="visible", timeout=15000)
                    popup.wait_for_timeout(500)
                    if bd_id or bd_catalogo or bd_nombre:
                        seleccionar_empresa_dropdown(popup, bd_id, bd_catalogo, bd_nombre)
                    popup.get_by_role("button", name="Ingresar").click()
                    popup.wait_for_url("**/Default_iv.aspx", timeout=30000)
                    popup.wait_for_load_state("networkidle")
                    popup.wait_for_timeout(1500)

                # Cerrar pestaña de Torre
                try:
                    pagina_torre.close()
                except Exception:
                    pass

                print(f"  [GRABAR] ERP listo: {popup.url}")
                print(f"  [GRABAR] Abriendo Inspector (page.pause)...")
                print(f"  [GRABAR] Usa el Inspector para grabar acciones.")

                # page.pause() abre Playwright Inspector en la sesión autenticada
                popup.pause()

                # Cuando el usuario cierra el Inspector, cerramos el browser
                browser.close()
                print(f"  [GRABAR] Sesión cerrada")

        except Exception as e:
            print(f"  [GRABAR] Error: {e}")
            traceback.print_exc()

    threading.Thread(target=_grabar_bg, daemon=True).start()
    return jsonify({"ok": True, "mensaje": "Abriendo Chrome con Inspector (login directo)..."})


@app.route("/ejecutar", methods=["POST"])
def ejecutar():
    data         = request.get_json()
    prueba_id    = data.get("prueba", "").strip()
    cliente      = data.get("cliente", "").strip()
    entorno_id   = data.get("entorno_id", "").strip()
    entorno_tipo = data.get("entorno_tipo", "").strip()
    entorno_url  = data.get("entorno_url", "").strip()
    bd_id        = data.get("bd_id", "").strip()
    bd_catalogo  = data.get("bd_catalogo", "").strip()
    bd_nombre    = data.get("bd_nombre", "").strip()
    parametros   = data.get("parametros", {}) or {}

    if not prueba_id:
        return jsonify({"error": "No se especificó una prueba"}), 400
    if not cliente:
        return jsonify({"error": "Debes seleccionar un cliente"}), 400
    if not entorno_id:
        return jsonify({"error": "Debes seleccionar un entorno"}), 400
    if not entorno_url:
        return jsonify({"error": "No se encontró la URL del entorno"}), 400

    session_id = str(uuid.uuid4())
    with SESIONES_LOCK:
        SESIONES[session_id] = {"eventos": [], "done": False}

    cfg = {
        "cliente":      cliente,
        "entorno_id":   entorno_id,
        "entorno_tipo": entorno_tipo,
        "entorno_url":  entorno_url,
        "bd_id":        bd_id,
        "bd_catalogo":  bd_catalogo,
        "bd_nombre":    bd_nombre,
        "parametros":   parametros,
    }

    hilo = threading.Thread(
        target=_ejecutar_prueba,
        args=(session_id, prueba_id, cfg),
        daemon=True
    )
    hilo.start()
    return jsonify({"session_id": session_id})


def _ejecutar_prueba(session_id, prueba_id, cfg):

    def emit(ev):
        with SESIONES_LOCK:
            if session_id in SESIONES:
                SESIONES[session_id]["eventos"].append(ev)

    def progreso(paso, total, nombre, desc, pct, pag=None):
        emit({
            "tipo": "progreso", "paso": paso, "total": total,
            "nombre": nombre, "descripcion": desc, "porcentaje": pct,
            "screenshot": capturar_screenshot(pag) if pag else None,
        })

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pruebas"))
        modulo = importlib.import_module(prueba_id)
        importlib.reload(modulo)

        progreso(1, 5, "Iniciando", "Autenticando en Torre...", 5)

        # ═══════════════════════════════════════════════════
        # TODO EN UN SOLO NAVEGADOR: Login Torre + Form POST + Prueba
        # Evita transferir NTLM entre sesiones de browser
        # ═══════════════════════════════════════════════════

        entorno_url = cfg["entorno_url"]
        login_url = entorno_url
        if not login_url.endswith("Login.aspx"):
            login_url = re.sub(r'/V3/Marco/.*$', '/V3/Marco/Login.aspx', login_url)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=False,
                channel="chrome",
            )
            context = browser.new_context(ignore_https_errors=True)
            pagina = context.new_page()

            # ── Paso 1: Login en Torre (~6s) ──
            progreso(2, 5, "Autenticando", "Login en Torre...", 15)
            print(f"  [PRUEBA] Abriendo Torre...")
            t0 = time.time()
            pagina.goto(sinco_api.url_torre)
            pagina.wait_for_load_state("networkidle")
            pagina.get_by_role("textbox", name="UsuarioWindows").fill(sinco_api.usuario)
            pagina.get_by_role("textbox", name="Contraseña").fill(sinco_api.password)
            pagina.get_by_role("button", name="Ingresar con Windows").click()
            pagina.wait_for_load_state("networkidle")
            pagina.wait_for_timeout(2000)

            # ── Paso 2: Leer key (disponible tras login) ──
            key_c = None
            for _ in range(20):
                key_c = pagina.evaluate("() => window.user_central_key || null")
                if key_c:
                    break
                pagina.wait_for_timeout(300)

            if not key_c:
                raise Exception("No se pudo obtener user_central_key tras login en Torre")

            usu_dominio = pagina.evaluate(
                "() => window.trabajador ? window.trabajador.UsuarioDominio : null"
            ) or sinco_api._usuario_dominio or f"sinco\\{sinco_api.usuario}"
            usu_login = pagina.evaluate(
                "() => window.trabajador ? window.trabajador.UsuarioLogin : null"
            ) or getattr(sinco_api, '_usuario_login', 'admin') or "admin"

            print(f"  [PRUEBA] keyC: {key_c[:20]}... ({time.time()-t0:.1f}s)")
            progreso(2, 5, "Autenticando", "Ingresando al entorno...", 30)

            # ── Paso 3: Form POST directo a Login.aspx (como hace Torre) ──
            usu_dominio_js = usu_dominio.replace("\\", "\\\\")

            with pagina.expect_popup(timeout=30000) as popup_info:
                pagina.evaluate(f"""() => {{
                    const form = document.createElement('form');
                    form.method = 'post';
                    form.action = '{login_url}';
                    form.target = '_blank';

                    const fields = {{
                        'keyC': '{key_c}',
                        'ingreso': '0',
                        'usuDominio': '{usu_dominio_js}',
                        'usuario': '{usu_login}'
                    }};

                    for (const [name, value] of Object.entries(fields)) {{
                        const input = document.createElement('input');
                        input.type = 'hidden';
                        input.name = name;
                        input.value = value;
                        form.appendChild(input);
                    }}

                    document.body.appendChild(form);
                    form.submit();
                }}""")

            popup = popup_info.value

            # Esperar saltos: Login.aspx → Seleccion.aspx → Seleccion_iv.aspx
            try:
                popup.wait_for_url("**/Seleccion_iv.aspx", timeout=30000)
            except Exception:
                pass
            popup.wait_for_load_state("networkidle")
            popup.wait_for_timeout(1500)

            url_actual = popup.url
            print(f"  [PRUEBA] Popup en: {url_actual}")

            # ── Paso 4: Seleccionar empresa si corresponde ──
            bd_id = cfg.get("bd_id", "")
            bd_catalogo = cfg.get("bd_catalogo", "")
            bd_nombre = cfg.get("bd_nombre", "")

            if "Seleccion" in url_actual:
                progreso(3, 5, "Seleccionando empresa", "Eligiendo empresa...", 50)
                popup.locator("#ddlEmpresa").wait_for(state="visible", timeout=15000)
                popup.wait_for_timeout(500)

                if bd_id or bd_catalogo or bd_nombre:
                    seleccionada = seleccionar_empresa_dropdown(popup, bd_id, bd_catalogo, bd_nombre)
                    print(f"  [PRUEBA] Empresa: {seleccionada}")

                popup.get_by_role("button", name="Ingresar").click()
                popup.wait_for_url("**/Default_iv.aspx", timeout=30000)
                popup.wait_for_load_state("networkidle")
                popup.wait_for_timeout(1500)
            elif "Default" in url_actual:
                print(f"  [PRUEBA] Directo en Default (sin Seleccion)")
            elif "Login" in url_actual:
                raise Exception(f"Autenticación falló - quedó en: {url_actual}")

            # ── Cerrar pestaña de Torre (ya no la necesitamos) ──
            try:
                pagina.close()
            except Exception:
                pass

            url_erp = popup.url
            elapsed = time.time() - t0
            print(f"  [PRUEBA] Login OK: {url_erp} ({elapsed:.1f}s)")

            progreso(4, 5, "Login exitoso", f"Dentro de {cfg['entorno_tipo']}", 80, popup)

            # ═══════════════════════════════════════════════════
            # FASE 2: Ejecutar prueba en el MISMO navegador
            # ═══════════════════════════════════════════════════
            paso_num = [4]

            def callback_paso(desc):
                paso_num[0] += 1
                pct = min(80 + int((paso_num[0] / 20) * 18), 97)
                emit({
                    "tipo": "progreso", "paso": paso_num[0], "total": 20,
                    "nombre": desc, "descripcion": desc, "porcentaje": pct,
                    "screenshot": capturar_screenshot(popup),
                })

            # Pasar `parametros` al módulo solo si su firma lo acepta
            # (mantiene compatibilidad con pruebas viejas que no lo declaran)
            import inspect as _inspect
            _sig = _inspect.signature(modulo.ejecutar).parameters
            _kwargs = {"on_paso": callback_paso}
            if "parametros" in _sig or any(
                p.kind == _inspect.Parameter.VAR_KEYWORD for p in _sig.values()
            ):
                _kwargs["parametros"] = cfg.get("parametros", {}) or {}
            resultado = modulo.ejecutar(popup, None, **_kwargs)

            exito = resultado.get("estado") == "ok"
            emit({
                "tipo":         "resultado",
                "prueba":       resultado.get("prueba", prueba_id),
                "estado":       resultado.get("estado", "ok"),
                "dato_entrada": resultado.get("dato_entrada", "-"),
                "esperado":     resultado.get("esperado", "Flujo completo sin errores"),
                "obtenido":     resultado.get("obtenido",
                                "Flujo completado" if exito else "Error en el flujo"),
                "empresa":      cfg["cliente"],
                "usuario":      CONFIG["usuario"],
                "fecha":        datetime.now().strftime("%d/%m/%Y %H:%M"),
                "entorno":      cfg["entorno_tipo"],
                "bd":           cfg.get("bd_nombre", ""),
            })

            emit({"tipo": "fin", "exito": exito})
            browser.close()

    except Exception as e:
        emit({"tipo": "error", "mensaje": str(e)})
        emit({"tipo": "error", "mensaje": traceback.format_exc()})
        emit({"tipo": "fin",   "exito": False})
    finally:
        with SESIONES_LOCK:
            if session_id in SESIONES:
                SESIONES[session_id]["done"] = True


@app.route("/stream/<session_id>")
def stream(session_id):
    def generar():
        ultimo = 0
        inicio = time.time()
        while time.time() - inicio < 300:
            with SESIONES_LOCK:
                sesion = SESIONES.get(session_id)
                if not sesion:
                    break
                nuevos = sesion["eventos"][ultimo:]
                ultimo = len(sesion["eventos"])
                done   = sesion["done"]
            for ev in nuevos:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            if done and not nuevos:
                break
            time.sleep(0.3)
        with SESIONES_LOCK:
            SESIONES.pop(session_id, None)

    return Response(generar(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    print("=" * 50)
    print("  SINCO ERP - Dashboard de Pruebas")
    print("  http://localhost:5000")
    print("=" * 50)

    # Pre-cargar datos al iniciar (en background)
    def _precarga():
        try:
            sinco_api.conectar_y_cargar()
        except Exception as e:
            print(f"  [API] Error en precarga: {e}")
            print(f"  [API] Los datos se cargarán en la primera consulta")

    threading.Thread(target=_precarga, daemon=True).start()

    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
