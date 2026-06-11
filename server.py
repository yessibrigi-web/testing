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
import sqlite3
from datetime import datetime

import requests as http_requests
from flask import Flask, jsonify, request, Response, send_from_directory, session
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = os.environ.get("FLASK_SECRET", "sinco-dashboard-secret-2024")

CONFIG = {
    "usuario":   "yessica.olaya",
    "password":  "Jeronimo2026",
    "url_torre": "https://core.sincoerp.com/SincoSoporte/Torre.html",
    "api_base":  "https://core.sincoerp.com/SincoSoporte",
}

SESIONES      = {}
SESIONES_LOCK = threading.Lock()

# ─────────────────────────────────────────────
# BASE DE DATOS DE MÉTRICAS
# ─────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "metricas.db")


def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS resultados (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha        TEXT    NOT NULL,
                prueba       TEXT    NOT NULL,
                modulo       TEXT    DEFAULT '',
                estado       TEXT    NOT NULL,
                dato_entrada TEXT    DEFAULT '',
                esperado     TEXT    DEFAULT '',
                obtenido     TEXT    DEFAULT '',
                cliente      TEXT    DEFAULT '',
                entorno      TEXT    DEFAULT '',
                bd           TEXT    DEFAULT '',
                usuario      TEXT    DEFAULT '',
                duracion_s   REAL    DEFAULT 0,
                addon        TEXT    DEFAULT ''
            )
        """)
        con.commit()


def guardar_resultado_db(row):
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.execute("""
                INSERT INTO resultados
                (fecha, prueba, modulo, estado, dato_entrada, esperado, obtenido,
                 cliente, entorno, bd, usuario, duracion_s, addon)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                row["fecha"], row["prueba"], row.get("modulo", ""),
                row["estado"], row.get("dato_entrada", ""), row.get("esperado", ""),
                row.get("obtenido", ""), row.get("cliente", ""), row.get("entorno", ""),
                row.get("bd", ""), row.get("usuario", ""),
                row.get("duracion_s", 0), row.get("addon", ""),
            ))
            con.commit()
    except Exception as e:
        print(f"  [DB] Error guardando resultado: {e}")


init_db()


# ─────────────────────────────────────────────
# VALIDACIÓN DE ADDON EN PRUEBAS
# ─────────────────────────────────────────────

PRUEBAS_INSTALACION_ADDON = {"InstalarAddon", "FlujoCompleto_Addon"}


def _es_entorno_pruebas(entorno_tipo: str) -> bool:
    """Devuelve True si el entorno es de pruebas/QA (no producción)."""
    t = entorno_tipo.upper()
    return any(kw in t for kw in ("PRUEBA", "QA", "TEST", "REPLICA", "SANDBOX"))


def verificar_addon_en_pruebas(cliente: str, entorno_tipo: str, addon_num: str) -> dict:
    """Consulta metricas.db para determinar si el addon ya fue instalado
    exitosamente en el entorno indicado para ese cliente.

    Retorna un dict con:
        instalado      bool   — True si hay registro ok o auditoría
        tiene_auditoria bool  — True si existe cualquier registro previo
        tiene_ok       bool  — True si hay al menos un resultado 'ok'
        registros      list  — registros relevantes encontrados
    """
    addon_limpio = str(addon_num).strip().lstrip("+")
    if not addon_limpio:
        return {"instalado": False, "tiene_auditoria": False, "tiene_ok": False, "registros": []}

    try:
        with sqlite3.connect(DB_PATH) as con:
            con.row_factory = sqlite3.Row
            cur = con.execute("""
                SELECT fecha, prueba, estado, entorno, addon, obtenido
                FROM   resultados
                WHERE  cliente = ?
                  AND  addon   = ?
                  AND  (prueba LIKE '%Instalar Addon%' OR prueba LIKE '%Flujo Addon%')
                ORDER  BY fecha DESC
                LIMIT  20
            """, (cliente, addon_limpio))
            rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"  [VERIFICAR] Error consultando DB: {e}")
        rows = []

    # Filtrar al entorno específico (si hay datos con entorno) pero también
    # incluir registros sin entorno (compatibilidad con registros antiguos)
    entorno_norm = entorno_tipo.upper()
    relevantes = [
        r for r in rows
        if (not r.get("entorno")) or (entorno_norm in r["entorno"].upper()) or (r["entorno"].upper() in entorno_norm)
    ]

    tiene_ok       = any(r["estado"] == "ok" for r in relevantes)
    tiene_auditoria = bool(relevantes)
    instalado      = tiene_ok or tiene_auditoria

    return {
        "instalado":       instalado,
        "tiene_auditoria": tiene_auditoria,
        "tiene_ok":        tiene_ok,
        "registros":       relevantes,
    }


def registrar_verificacion(cliente: str, entorno_tipo: str, bd_nombre: str,
                            addon_num: str, resultado_verificacion: dict):
    """Guarda trazabilidad de la verificación en metricas.db."""
    instalado = resultado_verificacion.get("instalado", False)
    guardar_resultado_db({
        "fecha":        datetime.now().isoformat(),
        "prueba":       "Verificación Addon",
        "modulo":       "Addons",
        "estado":       "advertencia" if instalado else "verificado",
        "dato_entrada": addon_num,
        "esperado":     "Addon no instalado en pruebas",
        "obtenido":     (
            "Addon ya instalado en pruebas — se bloqueó instalación duplicada"
            if instalado else
            "Addon no encontrado en pruebas — instalación permitida"
        ),
        "cliente":      cliente,
        "entorno":      entorno_tipo,
        "bd":           bd_nombre,
        "usuario":      CONFIG["usuario"],
        "duracion_s":   0,
        "addon":        addon_num,
    })


# Suprimir warnings de SSL
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ─────────────────────────────────────────────
# HELPERS DE NORMALIZACIÓN DE NOMBRES
# Compartidos entre SincoAPI (lookup de clientes/entornos/BD) y
# seleccionar_empresa_dropdown (matching de empresas en el ERP).
# ─────────────────────────────────────────────

def canonicalizar_iniciales(texto):
    """Colapsa secuencias de tokens de una sola letra alfabética en un único token.

    Sirve para que 'S.A.S' (que tras normalizar queda como 's a s') matchee
    contra 'SAS' (que queda 'sas') — son la misma forma societaria escrita
    con/sin puntos. Mismo principio para 'J Y P' ↔ 'JYP', 'L T D A' ↔ 'LTDA'.

    Tokens de UN solo carácter en secuencia aislada (ej. 'y' como conector
    entre dos palabras largas) NO se colapsan — solo se colapsan secuencias
    de 2+ iniciales contiguas.
    """
    tokens = texto.split()
    if not tokens:
        return texto
    result = []
    buffer = []
    for t in tokens:
        if len(t) == 1 and t.isalpha():
            buffer.append(t)
        else:
            if len(buffer) >= 2:
                result.append(''.join(buffer))
            elif buffer:
                result.extend(buffer)
            buffer = []
            result.append(t)
    if len(buffer) >= 2:
        result.append(''.join(buffer))
    elif buffer:
        result.extend(buffer)
    return ' '.join(result)


def normalizar(texto):
    sin_tildes = unicodedata.normalize('NFD', texto)
    sin_tildes = ''.join(c for c in sin_tildes if unicodedata.category(c) != 'Mn')
    # Reemplazar cualquier carácter que no sea letra, dígito o espacio por un
    # espacio — así las comas, guiones, paréntesis, etc. no rompen el match
    # entre nombres que SINCO guarda con/sin esa puntuación.
    # Ejemplo: "INTERVENTORIA, DISEÑOS Y CONTRATOS S.A.S"
    #          → "interventoria  disenos y contratos s a s"
    #          → canonicalizar → "interventoria disenos y contratos sas"
    base = re.sub(r'[^a-z0-9 ]', ' ', sin_tildes.lower())
    base = re.sub(r' +', ' ', base).strip()
    return canonicalizar_iniciales(base)


def strip_estado_legal(texto):
    """Quita sufijos de estado legal colombiano al final del nombre.

    Ejemplo: 'EMPRESA S.A. EN REORGANIZACIÓN' → 'EMPRESA S.A.'
    SINCO suele guardar el nombre del entorno sin estos sufijos, mientras
    que en el listado de clientes sí aparecen — esto causa que el match
    falle aunque sea la misma empresa.
    """
    estados = [
        r'EN\s+REORGANIZACI[OÓ]N',
        r'EN\s+LIQUIDACI[OÓ]N',
        r'EN\s+CONCORDATO',
        r'EN\s+INTERVENCI[OÓ]N',
        r'EN\s+ACUERDO\s+DE\s+REESTRUCTURACI[OÓ]N',
    ]
    patron = r'(?:\s+|\s*[-/]\s*)(?:' + '|'.join(estados) + r')\s*\.?\s*$'
    return re.sub(patron, '', texto, flags=re.IGNORECASE).strip()


def strip_prefijos(texto):
    """Quita prefijos REPLICA / PRUEBA(S) / CONSULTA - del inicio del nombre.

    Aplica de izquierda a derecha cuantas veces sea necesario. Acepta tanto
    PRUEBA (singular) como PRUEBAS (plural) — SINCO usa ambas formas:
    - 'REPLICA CASAHIDALGO CONSTRUCTORES S.A.S.' → 'CASAHIDALGO CONSTRUCTORES S.A.S.'
    - 'REPLICA CONSULTA - HIDALGO E HIDALGO COLOMBIA S.A.S' → 'HIDALGO E HIDALGO COLOMBIA S.A.S'
    - 'PRUEBAS BOGOTA LIMPIA SAS ESP' → 'BOGOTA LIMPIA SAS ESP'
    - 'PRUEBA HIDALGO E HIDALGO S.A.S' → 'HIDALGO E HIDALGO S.A.S'
    """
    return re.sub(
        r'^\s*(?:(?:REPLICA|PRUEBAS?|CONSULTA)\s+(?:-\s+)?)+',
        '',
        texto,
        flags=re.IGNORECASE,
    ).strip()


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
        primero = []   # empieza con el query
        resto   = []   # contiene el query en el medio
        for c in self._clientes:
            nombre = c.get("Cliente", "")
            nombre_lower = nombre.lower()
            if q_lower not in nombre_lower:
                continue
            entrada = {
                "id":         nombre,
                "nombre":     nombre,
                "nit":        c.get("Nit", ""),
                "ciudad":     c.get("Ciudad", ""),
                "id_cliente": c.get("IdCliente"),
            }
            if nombre_lower.startswith(q_lower):
                primero.append(entrada)
            else:
                resto.append(entrada)
        return (primero + resto)[:50]

    def obtener_entornos(self, cliente_nombre):
        self.conectar_y_cargar()

        # Alias manual: permite corregir desajustes de nombre entre clientes y entornos en Torre
        _alias_path = os.path.join(os.path.dirname(__file__), "clientes_alias.json")
        try:
            with open(_alias_path, encoding="utf-8") as _f:
                _alias = json.load(_f)
            if cliente_nombre in _alias:
                cliente_nombre = _alias[cliente_nombre]
                print(f"  [API] alias aplicado → '{cliente_nombre}'")
        except Exception:
            pass

        cliente_norm = normalizar(cliente_nombre)
        cliente_sin_estado_norm = normalizar(strip_estado_legal(cliente_nombre))

        # IdCliente del cliente seleccionado (para fallback por EmpresaId)
        id_cliente_seleccionado = None
        for c in self._clientes:
            if c.get("Cliente", "") == cliente_nombre:
                id_cliente_seleccionado = c.get("IdCliente")
                break

        # Filtrado por NombreCliente del entorno, normalizado y SIN el prefijo
        # "REPLICA " / "PRUEBAS " que SINCO antepone en entornos no-productivos.
        #
        # IMPORTANTE: NO se usa IdCliente == EmpresaId porque son IDs distintos
        # y además SINCO recicla EmpresaId entre clientes (ej. IdCliente=320 de
        # REDES Y EDIFICACIONES → entornos EmpresaId=320 de CONSORCIO MORENO
        # TAFURT). La única relación confiable es el nombre embebido en
        # NombreCliente del entorno.
        #
        # Casos de matching contra cada "candidato" del cliente (nombre completo
        # y nombre sin sufijo de estado legal "EN REORGANIZACIÓN" / "EN
        # LIQUIDACIÓN" / etc.):
        #
        # A) Exacto — JYP, OTACC, CONALTURA:
        #    Cliente: "CONSTRUCTORA J Y P S.A.S."
        #    Entorno: "CONSTRUCTORA J Y P S.A.S"
        #    Normalizan iguales.
        #
        # B) Entorno es prefijo del cliente (cliente con razón social adicional)
        #    — INTRAMAQ: cliente "INGENIERIA TRANSPORTE Y MAQUINARIA S.A.S.
        #    INTRAMAQ S.A.S." vs entorno "INGENIERIA TRANSPORTE Y MAQUINARIA
        #    S.A.S.".
        #
        # C) Cliente tiene sufijo de estado legal — REDES: cliente "REDES Y
        #    EDIFICACIONES S.A. EN REORGANIZACIÓN" se reduce a "REDES Y
        #    EDIFICACIONES S.A." y queda como prefijo del entorno "REDES Y
        #    EDIFICACIONES S A R&E S A".
        #
        # D) Cliente es prefijo del entorno (entorno con alias/sufijo adicional)
        #    — combinado con C: el candidato sin estado legal cabe como prefijo
        #    del NombreCliente del entorno.
        #
        # Las reglas de prefijo (B y D) solo aplican si NINGÚN otro cliente
        # reclama exactamente el nombre del entorno como suyo — evita robarle
        # entornos al "dueño correcto" cuando exista.
        clientes_norm_set = {
            normalizar(c.get("Cliente", ""))
            for c in self._clientes
            if c.get("Cliente")
        }

        candidatos = {cliente_norm}
        # Solo agregamos el candidato sin estado legal si no colisiona con otro
        # cliente real del sistema (que ya reclamaría sus propios entornos).
        if (cliente_sin_estado_norm
                and cliente_sin_estado_norm != cliente_norm
                and cliente_sin_estado_norm not in clientes_norm_set):
            candidatos.add(cliente_sin_estado_norm)

        def _check_match(nombre_a_comparar_norm):
            """True si nombre_a_comparar_norm coincide con algún candidato del cliente.

            Aplica exacto + prefijo bidireccional con la salvaguarda de
            'no robarle entornos a otro cliente que reclame el nombre exacto'.
            """
            if not nombre_a_comparar_norm:
                return False
            for candidato in candidatos:
                if nombre_a_comparar_norm == candidato:
                    return True
                if (candidato.startswith(nombre_a_comparar_norm + " ")
                        and nombre_a_comparar_norm not in clientes_norm_set):
                    return True
                if (nombre_a_comparar_norm.startswith(candidato + " ")
                        and nombre_a_comparar_norm not in clientes_norm_set):
                    return True
            return False

        # Pase 1: matching directo por NombreCliente (Canal 1) o BasesDatos (Canal 2)
        entornos_match_ids = set()
        entornos_seleccionados = []
        # Para transitividad multi-tenant: cuando un cliente se identifica vía una
        # BD dentro de un entorno multi-tenant, agregamos también los OTROS entornos
        # del mismo SINCO Customer (mismo EmpresaId) cuyo Nombre comparte la raíz —
        # cubre el caso del entorno de Pruebas que no tiene BD específica del cliente.
        empresas_canal2 = set()
        bases_nombres_canal2 = set()

        for e in self._entornos:
            match_canal = None

            # Canal 1 — NombreCliente del entorno (caso mono-tenant: JYP, INTRAMAQ,
            # REDES, OTACC, etc.)
            nombre_e_raw = e.get("NombreCliente", "") or ""
            if nombre_e_raw:
                nombre_e_limpio = strip_estado_legal(strip_prefijos(nombre_e_raw))
                nombre_e_norm = normalizar(nombre_e_limpio)
                if _check_match(nombre_e_norm):
                    match_canal = 1

            # Canal 2 — BasesDatos del entorno (caso multi-tenant: el entorno
            # SincoHidalgo aloja BDs de varios clientes; CASAHIDALGO se identifica
            # vía su BD 'CASAHIDALGO CONSTRUCTORES S.A.S.' dentro de ese entorno).
            if match_canal is None:
                for bd in (e.get("BasesDatos") or []):
                    bd_nombre_raw = bd.get("Nombre") or ""
                    if not bd_nombre_raw:
                        continue
                    bd_limpio = strip_estado_legal(strip_prefijos(bd_nombre_raw))
                    bd_norm = normalizar(bd_limpio)
                    if _check_match(bd_norm):
                        match_canal = 2
                        break

            if match_canal is None:
                continue

            entorno_id = e.get("Id")
            if entorno_id not in entornos_match_ids:
                entornos_match_ids.add(entorno_id)
                entornos_seleccionados.append(e)

            if match_canal == 2:
                emp_id = e.get("EmpresaId")
                if emp_id is not None:
                    empresas_canal2.add(emp_id)
                # Nombre base = Nombre del entorno sin prefijo REPLICA_
                base = re.sub(r'^REPLICA_', '', e.get("Nombre") or "", flags=re.IGNORECASE).lower()
                if base:
                    bases_nombres_canal2.add(base)

        # Pase 1b: fallback por EmpresaId == IdCliente cuando nombre no coincide.
        # Caso PULSO PROYECTOS TEMATICOS S.A.S. (cliente) vs
        # PULSO PROMOTORA TEMATICA S.A.S. (entorno) — nombres distintos en Torre.
        # Solo se aplica si los canales 1 y 2 no encontraron ningún entorno.
        # Doble verificación: EmpresaId + al menos la primera palabra del cliente
        # debe aparecer en el NombreCliente del entorno (evita falsos positivos por
        # reciclaje de IDs en SINCO).

        # Pase 2: transitividad multi-tenant (solo si hubo match Canal 2).
        # Incluir entornos con el mismo EmpresaId cuyo Nombre base comparte raíz
        # con alguno de los entornos directamente matched. Ej: SincoHidalgo_PRBINT
        # entra porque su base 'sincohidalgo_prbint' empieza con 'sincohidalgo'.
        # SincoCASSEPCNC NO entra porque su base no comienza así.
        if empresas_canal2 and bases_nombres_canal2:
            for e in self._entornos:
                if e.get("Id") in entornos_match_ids:
                    continue
                if e.get("EmpresaId") not in empresas_canal2:
                    continue
                base_e = re.sub(r'^REPLICA_', '', e.get("Nombre") or "", flags=re.IGNORECASE).lower()
                if not base_e:
                    continue
                if any(base_e.startswith(b) for b in bases_nombres_canal2):
                    entornos_match_ids.add(e.get("Id"))
                    entornos_seleccionados.append(e)

        # Pase 3: formato de salida
        entornos = []
        for e in entornos_seleccionados:
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

        print(f"  [API] obtener_entornos: '{cliente_nombre}' → {len(entornos)} entornos")
        return entornos

    def obtener_bases(self, cliente_nombre, entorno_nombre):
        self.conectar_y_cargar()

        for e in self._entornos:
            if e.get("Nombre", "") == entorno_nombre:
                bases = []
                for bd in e.get("BasesDatos", []):
                    nombre_bd = bd.get("Nombre", bd.get("Catalogo", ""))
                    # Limpiar prefijos REPLICA / PRUEBAS / CONSULTA - para display
                    nombre_bd = strip_prefijos(nombre_bd)
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

            # Mover popup fuera de pantalla (NTLM requiere headless=False pero no tiene que ser visible)
            try:
                popup.evaluate("window.moveTo(-32000, -32000); window.resizeTo(1, 1);")
            except Exception:
                pass

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
    Prioridad: nombre exacto → case-insensitive → normalizado (sin prefijos
    REPLICA/PRUEBA(S)/CONSULTA, sin sufijos de estado legal, con iniciales
    colapsadas tipo 'S A S' → 'sas') → parcial normalizado → palabras normalizadas.
    """
    # El <select> se rellena de forma asíncrona vía API
    # (GET /V3/API/Cliente/{id}/Empresas); al cargar muestra un único
    # <option> "Cargando...". Esperar a que aparezcan opciones reales antes
    # de leerlas. 30 s es el mismo bucket usado en wait_for_url para popups,
    # adecuado para esperas que cuelgan de un fetch HTTP del ERP.
    READY_SCRIPT = """() => {
        const sel = document.querySelector('#ddlEmpresa');
        if (!sel) return false;
        const opts = Array.from(sel.options).map(o => (o.textContent || '').trim()).filter(Boolean);
        return opts.length > 0 && !opts.every(t => /^cargando/i.test(t));
    }"""
    try:
        pagina.wait_for_function(READY_SCRIPT, timeout=30000)
    except PlaywrightTimeoutError:
        # El dropdown se quedó en 'Cargando...' — algunos entornos lentos (p.ej.
        # Constructora Capital pruebas) no completan la llamada AJAX a tiempo.
        # Reintentar: recargar la página y esperar otros 45 s antes de fallar.
        print("  [MATCH] #ddlEmpresa sigue en 'Cargando...' tras 30s; recargando y reintentando...")
        pagina.reload(wait_until="networkidle")
        pagina.wait_for_timeout(2000)
        try:
            pagina.wait_for_function(READY_SCRIPT, timeout=45000)
        except PlaywrightTimeoutError:
            # Capturar estado del navegador para el mensaje de error.
            estado = pagina.evaluate("""() => {
                const sel = document.querySelector('#ddlEmpresa');
                return {
                    url: location.href,
                    title: document.title,
                    opts: sel ? Array.from(sel.options).map(o => (o.textContent || '').trim()).filter(Boolean) : null,
                };
            }""")
            opts_reales = [t for t in (estado.get("opts") or []) if not re.match(r'^cargando', t, re.IGNORECASE)]
            if not opts_reales:
                raise Exception(
                    f"Timeout esperando empresas en #ddlEmpresa (30s+45s con recarga). "
                    f"URL={estado.get('url')} Title={estado.get('title')} "
                    f"Opciones actuales: {estado.get('opts')}"
                )
            print(f"  [MATCH] wait expiró pero el dropdown ya tiene {len(opts_reales)} opciones tras recarga; continuando.")
        else:
            print("  [MATCH] Dropdown cargado correctamente tras recarga.")

    opciones = pagina.locator("#ddlEmpresa option").all()
    labels = []
    for opt in opciones:
        text = opt.text_content().strip()
        if text and not re.match(r'^cargando', text, re.IGNORECASE):
            labels.append(text)

    print(f"  [MATCH] bd_nombre='{bd_nombre}' ({len(labels)} opciones)")

    def seleccionar(texto_label):
        pagina.locator("#ddlEmpresa").select_option(label=texto_label)

    if not bd_nombre:
        raise Exception(f"bd_nombre vacío; no se puede elegir empresa. Opciones: {labels[:5]}")

    # 1. Match por nombre exacto (crudo)
    for text in labels:
        if text == bd_nombre:
            seleccionar(text)
            return f"(nombre exacto) {text}"

    # 2. Match case-insensitive (crudo)
    bd_lower = bd_nombre.lower()
    for text in labels:
        if text.lower() == bd_lower:
            seleccionar(text)
            return f"(case-insensitive) {text}"

    # Normalización compartida para tiers 3–5: quita prefijos PRUEBA(S)/REPLICA/
    # CONSULTA, quita sufijos de estado legal, colapsa 'S A S' → 'sas', baja a
    # minúsculas y quita tildes. Así 'CONSTRUCTORA CAPITAL BOGOTA S A S' del
    # dashboard matchea contra 'PRUEBAS CONSTRUCTORA CAPITAL BOGOTA' del ERP.
    def _clave(s):
        return normalizar(strip_estado_legal(strip_prefijos(s)))

    bd_clave = _clave(bd_nombre)
    opciones_clave = [(text, _clave(text)) for text in labels]

    # 3. Match exacto sobre clave normalizada
    for text, clave in opciones_clave:
        if clave and clave == bd_clave:
            seleccionar(text)
            return f"(normalizado) {text}"

    # 4. Contención parcial sobre claves normalizadas
    if bd_clave:
        for text, clave in opciones_clave:
            if clave and (bd_clave in clave or clave in bd_clave):
                seleccionar(text)
                return f"(parcial) {text}"

    # 5. Score por palabras sobre clave normalizada (60%+ coincidencia)
    palabras_bd = [p for p in bd_clave.split() if len(p) > 2]
    mejor_match, mejor_score = None, 0
    for text, clave in opciones_clave:
        coincidencias = sum(1 for p in palabras_bd if p in clave)
        score = coincidencias / max(len(palabras_bd), 1)
        if score > mejor_score:
            mejor_score = score
            mejor_match = text
    if mejor_match and mejor_score >= 0.6:
        seleccionar(mejor_match)
        return f"(palabras {mejor_score:.0%}) {mejor_match}"

    claves_log = [c for _, c in opciones_clave[:5]]
    print(f"  [MATCH] NO se encontró match. bd_clave='{bd_clave}' Opciones: {labels[:5]} Claves: {claves_log}")
    raise Exception(
        f"No se encontró la empresa en el dropdown. "
        f"Nombre={bd_nombre} bd_clave={bd_clave!r}. "
        f"Opciones: {labels[:5]} Claves: {claves_log}"
    )


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


@app.route("/login", methods=["POST"])
def login():
    """Guarda las credenciales del usuario en la sesión Flask."""
    data = request.get_json(force=True) or {}
    usuario  = (data.get("usuario")  or "").strip()
    password = (data.get("password") or "").strip()
    if not usuario or not password:
        return jsonify({"error": "Usuario y contraseña son obligatorios"}), 400
    session["usuario"]  = usuario
    session["password"] = password
    print(f"  [LOGIN] Sesión iniciada para: {usuario}")
    return jsonify({"ok": True, "usuario": usuario})


@app.route("/logout", methods=["POST"])
def logout():
    """Cierra la sesión activa."""
    usuario = session.get("usuario", "—")
    session.clear()
    print(f"  [LOGIN] Sesión cerrada para: {usuario}")
    return jsonify({"ok": True})


@app.route("/config")
def get_config():
    usuario = session.get("usuario") or CONFIG["usuario"]
    return jsonify({"usuario": usuario, "autenticado": "usuario" in session})


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

    def _resumen_entorno(e):
        return {
            "Id": e.get("Id"),
            "Nombre": e.get("Nombre"),
            "NombreCliente": e.get("NombreCliente"),
            "EmpresaId": e.get("EmpresaId"),
            "Tipo": e.get("Tipo"),
            "URL": e.get("URL"),
            "BasesDatos": [
                {
                    "Id": bd.get("Id"),
                    "Nombre": bd.get("Nombre"),
                    "Catalogo": bd.get("Catalogo"),
                    "Principal": bd.get("Principal"),
                }
                for bd in (e.get("BasesDatos") or [])
            ],
        }

    # Buscar entornos por nombre del entorno o cualquier campo que contenga el query
    entornos_por_texto = []
    for e in sinco_api._entornos:
        e_str = json.dumps(e, ensure_ascii=False).lower()
        if q in e_str:
            entornos_por_texto.append(_resumen_entorno(e))

    return jsonify({
        "cliente": {
            "IdCliente": id_cliente,
            "Cliente": nombre_cliente,
            "Nit": cliente_match.get("Nit"),
        },
        "entornos_por_EmpresaId": [_resumen_entorno(e) for e in entornos_por_empresa],
        "entornos_por_NombreCliente": [_resumen_entorno(e) for e in entornos_por_nombre],
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


def _normalizar_script_grabado(codigo_codegen: str):
    """
    Toma la salida cruda de `playwright codegen` y devuelve solo el cuerpo
    de acciones limpio (sin imports, sin sync_playwright, sin browser launch,
    sin primer goto, con `page` → `pagina`). Retorna None si no hay acciones.
    """
    patrones_skip = [
        r'^\s*browser\s*=\s*playwright',
        r'^\s*context\s*=\s*browser\.new_context',
        r'^\s*page\s*=\s*context\.new_page',
        r'^\s*context\.close\(\)',
        r'^\s*browser\.close\(\)',
        r'^\s*with sync_playwright',
        r'^\s*run\(playwright\)',
        r'^\s*from playwright',
        r'^\s*import ',
        r'^\s*def run\(',
    ]
    lineas_limpias = []
    primer_goto_visto = False
    for linea in codigo_codegen.split('\n'):
        if any(re.match(p, linea) for p in patrones_skip):
            continue
        if not primer_goto_visto and re.match(r'^\s*page\.goto\(', linea):
            primer_goto_visto = True
            continue
        lineas_limpias.append(linea)

    cuerpo = '\n'.join(lineas_limpias)
    cuerpo = re.sub(r'\bpage\b', 'pagina', cuerpo)

    lineas_no_vacias = [l for l in cuerpo.split('\n') if l.strip()]
    if not lineas_no_vacias:
        return None

    indent_min = min(len(l) - len(l.lstrip()) for l in lineas_no_vacias)
    cuerpo_normalizado = '\n'.join(
        ('    ' + l[indent_min:]) if l.strip() else ''
        for l in cuerpo.split('\n')
    )
    return cuerpo_normalizado.strip('\n')


def _envolver_en_plantilla(cuerpo: str, nombre_display: str, modulo: str) -> str:
    """Envuelve el cuerpo de acciones en la plantilla estándar del proyecto."""
    return f'''"""
Prueba: {nombre_display}
Módulo: {modulo}
"""


def ejecutar(pagina, frame, on_paso=None):
    # --- Código grabado con Playwright Codegen ---

{cuerpo}

    return {{
        "prueba": "{nombre_display}",
        "estado": "ok",
        "dato_entrada": "-",
        "esperado": "Flujo completo sin errores",
        "obtenido": "Flujo completado",
    }}
'''


@app.route("/grabar", methods=["POST"])
def grabar():
    """Graba una prueba con Playwright Codegen y genera el archivo automáticamente."""
    import subprocess
    import tempfile
    data = request.get_json() or {}
    cliente        = data.get("cliente", "").strip()
    entorno_id     = data.get("entorno_id", "").strip()
    entorno_url    = data.get("entorno_url", "").strip()
    bd_id          = data.get("bd_id", "")
    bd_catalogo    = data.get("bd_catalogo", "").strip()
    bd_nombre      = data.get("bd_nombre", "").strip()
    nombre         = data.get("nombre", "").strip()
    nombre_display = data.get("display", "").strip() or nombre
    modulo         = data.get("modulo", "Sin categoría").strip()

    if not cliente or not entorno_id:
        return jsonify({"error": "Selecciona cliente y entorno antes de grabar"}), 400
    if not entorno_url:
        return jsonify({"error": "No se encontró la URL del entorno"}), 400
    if not nombre:
        return jsonify({"error": "Falta el nombre de la prueba a grabar"}), 400

    nombre_limpio = re.sub(r'[^a-zA-Z0-9_]', '', nombre)
    if not nombre_limpio:
        return jsonify({"error": "Nombre inválido"}), 400

    ruta_final = os.path.join(os.path.dirname(__file__), "pruebas", f"{nombre_limpio}.py")
    if os.path.isfile(ruta_final):
        return jsonify({"error": f"{nombre_limpio}.py ya existe"}), 409

    # Capturar credenciales en el contexto de request antes de entrar al hilo
    _usu_grabar = session.get("usuario")  or sinco_api.usuario
    _pwd_grabar = session.get("password") or sinco_api.password

    def _grabar_bg():
        storage_path = os.path.join(tempfile.gettempdir(), f"yom_storage_{nombre_limpio}.json")
        output_path  = os.path.join(tempfile.gettempdir(), f"yom_codegen_{nombre_limpio}.py")
        try:
            print(f"  [GRABAR] Login para grabación de '{nombre_limpio}'...")

            login_url_g = entorno_url
            if not login_url_g.endswith("Login.aspx"):
                login_url_g = re.sub(r'/V3/Marco/.*$', '/V3/Marco/Login.aspx', login_url_g)

            url_grabacion = None
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=False, channel="chrome")
                context = browser.new_context(ignore_https_errors=True)
                pagina_torre = context.new_page()

                print(f"  [GRABAR] Login en Torre...")
                pagina_torre.goto(sinco_api.url_torre)
                pagina_torre.wait_for_load_state("networkidle")
                pagina_torre.get_by_role("textbox", name="UsuarioWindows").fill(_usu_grabar)
                pagina_torre.get_by_role("textbox", name="Contraseña").fill(_pwd_grabar)
                pagina_torre.get_by_role("button", name="Ingresar con Windows").click()
                pagina_torre.wait_for_load_state("networkidle")
                pagina_torre.wait_for_timeout(2000)

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

                # Mover popup fuera de pantalla (NTLM requiere headless=False pero no tiene que ser visible)
                try:
                    popup.evaluate("window.moveTo(-32000, -32000); window.resizeTo(1, 1);")
                except Exception:
                    pass

                try:
                    popup.wait_for_url("**/Seleccion_iv.aspx", timeout=30000)
                except Exception:
                    pass
                popup.wait_for_load_state("networkidle")
                popup.wait_for_timeout(1500)

                if "Seleccion" in popup.url:
                    popup.locator("#ddlEmpresa").wait_for(state="visible", timeout=15000)
                    if bd_id or bd_catalogo or bd_nombre:
                        seleccionar_empresa_dropdown(popup, bd_id, bd_catalogo, bd_nombre)
                    popup.get_by_role("button", name="Ingresar").click()
                    popup.wait_for_url("**/Default_iv.aspx", timeout=30000)
                    popup.wait_for_load_state("networkidle")
                    popup.wait_for_timeout(1500)

                try:
                    pagina_torre.close()
                except Exception:
                    pass

                url_grabacion = popup.url
                print(f"  [GRABAR] ERP listo: {url_grabacion}")
                print(f"  [GRABAR] Guardando sesión en {storage_path}...")
                context.storage_state(path=storage_path)
                browser.close()

            print(f"  [GRABAR] Lanzando Playwright Codegen — al cerrar Inspector se guardará {nombre_limpio}.py")
            cmd = [
                sys.executable, "-m", "playwright", "codegen",
                "--target=python",
                "--channel=chrome",
                f"--load-storage={storage_path}",
                f"--output={output_path}",
                url_grabacion,
            ]
            subprocess.run(cmd, check=False)

            if not os.path.isfile(output_path):
                print(f"  [GRABAR] Codegen no generó archivo (usuario canceló)")
                return

            with open(output_path, encoding="utf-8") as f:
                codigo_raw = f.read()

            cuerpo = _normalizar_script_grabado(codigo_raw)
            if not cuerpo:
                print(f"  [GRABAR] Grabación vacía — no se crea archivo")
                return

            contenido = _envolver_en_plantilla(cuerpo, nombre_display, modulo)
            with open(ruta_final, "w", encoding="utf-8") as f:
                f.write(contenido)
            print(f"  [GRABAR] Prueba guardada en {ruta_final}")

        except Exception as e:
            print(f"  [GRABAR] Error: {e}")
            traceback.print_exc()
        finally:
            for p in (storage_path, output_path):
                try:
                    if os.path.isfile(p):
                        os.remove(p)
                except Exception:
                    pass

    threading.Thread(target=_grabar_bg, daemon=True).start()
    return jsonify({
        "ok": True,
        "mensaje": f"Grabando — al cerrar el Inspector se creará {nombre_limpio}.py automáticamente",
        "nombre": nombre_limpio,
    })


@app.route("/verificar_addon", methods=["POST"])
def verificar_addon():
    """Consulta si un addon ya está instalado en el entorno de pruebas de un cliente.

    Body JSON:
        cliente      str  — nombre del cliente
        entorno_tipo str  — tipo de entorno (Pruebas, Producción, etc.)
        bd_nombre    str  — nombre de la base de datos (para trazabilidad)
        addon        str  — número de addon (ej: "142", "-142")

    Responde con el formato estándar de validación de instalación.
    """
    data         = request.get_json() or {}
    cliente      = data.get("cliente", "").strip()
    entorno_tipo = data.get("entorno_tipo", "").strip()
    bd_nombre    = data.get("bd_nombre", "").strip()
    addon_raw    = str(data.get("addon", "142")).strip().lstrip("+") or "142"

    if not cliente:
        return jsonify({"error": "Debes seleccionar un cliente"}), 400

    verificacion = verificar_addon_en_pruebas(cliente, entorno_tipo, addon_raw)
    instalado    = verificacion["instalado"]

    if instalado:
        ultimo = verificacion["registros"][0] if verificacion["registros"] else {}
        estado_msg = (
            f"Alerta: el addon ya se encuentra instalado en pruebas. "
            f"Verifique si corresponde realizar el despliegue a producción."
        )
        ultimo_registro = (
            f"Último registro: {ultimo.get('fecha','–')[:10]} | "
            f"Estado: {ultimo.get('estado','–')} | {ultimo.get('obtenido','–')}"
            if ultimo else "Sin detalle disponible"
        )
    else:
        estado_msg      = "Instalación permitida en pruebas."
        ultimo_registro = "Sin registros previos en pruebas."

    respuesta = {
        "cliente":            cliente,
        "addon":              addon_raw,
        "entorno_consultado": entorno_tipo or "Pruebas",
        "instalado":          instalado,
        "tiene_auditoria":    verificacion["tiene_auditoria"],
        "tiene_ok":           verificacion["tiene_ok"],
        "estado_mensaje":     estado_msg,
        "ultimo_registro":    ultimo_registro,
        "registros":          verificacion["registros"],
    }
    return jsonify(respuesta)


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

    # Capturar credenciales aquí (contexto de request) antes de lanzar el hilo,
    # porque Flask session no es accesible fuera del contexto de petición HTTP.
    cfg = {
        "cliente":      cliente,
        "entorno_id":   entorno_id,
        "entorno_tipo": entorno_tipo,
        "entorno_url":  entorno_url,
        "bd_id":        bd_id,
        "bd_catalogo":  bd_catalogo,
        "bd_nombre":    bd_nombre,
        "parametros":   parametros,
        "usu":          session.get("usuario")  or sinco_api.usuario,
        "pwd":          session.get("password") or sinco_api.password,
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

        _t_inicio = time.time()
        _docstring = getattr(modulo, '__doc__', '') or ''
        _mm = re.search(r'Módulo:\s*(.+)', _docstring)
        _test_modulo = _mm.group(1).strip() if _mm else ''
        _addon = str((cfg.get("parametros") or {}).get("addon", "") or "").strip()

        # ═══════════════════════════════════════════════════
        # GUARDIA: verificar addon antes de abrir el navegador
        # Aplica solo a pruebas de instalación de addon en entorno de pruebas
        # ═══════════════════════════════════════════════════
        if prueba_id in PRUEBAS_INSTALACION_ADDON and _addon and _es_entorno_pruebas(cfg.get("entorno_tipo", "")):
            addon_limpio = _addon.lstrip("+").lstrip("-")
            _verificacion = verificar_addon_en_pruebas(cfg["cliente"], cfg.get("entorno_tipo", ""), addon_limpio)

            if _verificacion["instalado"]:
                _ult = _verificacion["registros"][0] if _verificacion["registros"] else {}
                _msg_alerta = (
                    f"⚠️  ALERTA: El addon {_addon} ya se encuentra instalado en pruebas para {cfg['cliente']}. "
                    f"Si las validaciones del cliente ya fueron completadas y aprobadas, "
                    f"se puede proceder con la instalación en PRODUCCIÓN."
                )
                _detalle = (
                    f"Último registro: {_ult.get('fecha','–')[:19]} | "
                    f"Estado: {_ult.get('estado','–')} | {_ult.get('obtenido','–')}"
                    if _ult else ""
                )
                registrar_verificacion(
                    cfg["cliente"], cfg.get("entorno_tipo", ""),
                    cfg.get("bd_nombre", ""), addon_limpio, _verificacion,
                )
                emit({
                    "tipo":         "resultado",
                    "prueba":       f"Verificación Addon {_addon}",
                    "estado":       "advertencia",
                    "dato_entrada": _addon,
                    "esperado":     "Addon no instalado en pruebas",
                    "obtenido":     _msg_alerta,
                    "empresa":      cfg["cliente"],
                    "usuario":      CONFIG["usuario"],
                    "fecha":        datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "entorno":      cfg.get("entorno_tipo", ""),
                    "bd":           cfg.get("bd_nombre", ""),
                    "detalle":      _detalle,
                    "resumen": {
                        "cliente":            cfg["cliente"],
                        "addon":              _addon,
                        "entorno_consultado": cfg.get("entorno_tipo", "Pruebas"),
                        "estado_mensaje":     (
                            f"Alerta: el addon ya se encuentra instalado en pruebas. "
                            f"Verifique si corresponde realizar el despliegue a producción."
                        ),
                    },
                })
                emit({"tipo": "fin", "exito": False})
                return  # Abortar — no se abre navegador ni se instala

            # Addon NO encontrado → informar que procede
            registrar_verificacion(
                cfg["cliente"], cfg.get("entorno_tipo", ""),
                cfg.get("bd_nombre", ""), addon_limpio, _verificacion,
            )
            emit({
                "tipo":         "progreso",
                "paso":         0,
                "total":        5,
                "nombre":       "Verificación OK",
                "descripcion":  (
                    f"✅ Addon {_addon} no instalado en pruebas para {cfg['cliente']}. "
                    f"Instalación permitida."
                ),
                "porcentaje":   3,
                "screenshot":   None,
            })

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
            pagina.get_by_role("textbox", name="UsuarioWindows").fill(cfg["usu"])
            pagina.get_by_role("textbox", name="Contraseña").fill(cfg["pwd"])
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
            _res_obtenido = resultado.get("obtenido",
                            "Flujo completado" if exito else "Error en el flujo")
            emit({
                "tipo":         "resultado",
                "prueba":       resultado.get("prueba", prueba_id),
                "estado":       resultado.get("estado", "ok"),
                "dato_entrada": resultado.get("dato_entrada", "-"),
                "esperado":     resultado.get("esperado", "Flujo completo sin errores"),
                "obtenido":     _res_obtenido,
                "empresa":      cfg["cliente"],
                "usuario":      CONFIG["usuario"],
                "fecha":        datetime.now().strftime("%d/%m/%Y %H:%M"),
                "entorno":      cfg["entorno_tipo"],
                "bd":           cfg.get("bd_nombre", ""),
            })
            guardar_resultado_db({
                "fecha":        datetime.now().isoformat(),
                "prueba":       resultado.get("prueba", prueba_id),
                "modulo":       _test_modulo,
                "estado":       resultado.get("estado", "ok"),
                "dato_entrada": resultado.get("dato_entrada", "-"),
                "esperado":     resultado.get("esperado", ""),
                "obtenido":     _res_obtenido,
                "cliente":      cfg["cliente"],
                "entorno":      cfg["entorno_tipo"],
                "bd":           cfg.get("bd_nombre", ""),
                "usuario":      CONFIG["usuario"],
                "duracion_s":   round(time.time() - _t_inicio, 1),
                "addon":        _addon,
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


# ─────────────────────────────────────────────
# ENDPOINTS DE MÉTRICAS
# ─────────────────────────────────────────────

def _build_filtros(req):
    """Construye cláusula WHERE + lista de params desde los query args de la petición."""
    clauses, params = [], []

    fecha_desde = req.args.get("fecha_desde", "").strip()
    fecha_hasta = req.args.get("fecha_hasta", "").strip()
    dias        = req.args.get("dias", "").strip()
    cliente_f   = req.args.get("cliente", "").strip()
    prueba_f    = req.args.get("prueba", "").strip()
    modulo_f    = req.args.get("modulo", "").strip()
    estado_f    = req.args.get("estado", "").strip()
    entorno_f   = req.args.get("entorno", "").strip()
    addon_f     = req.args.get("addon", "").strip()

    # Rango de fechas: rango explícito tiene prioridad sobre el período rápido
    if fecha_desde:
        clauses.append("fecha >= ?")
        params.append(fecha_desde)
    elif dias and dias.isdigit() and int(dias) < 9000:
        clauses.append("fecha >= datetime('now', ?)")
        params.append(f"-{dias} days")

    if fecha_hasta:
        clauses.append("fecha <= ?")
        params.append(fecha_hasta + "T23:59:59")

    if cliente_f:
        clauses.append("cliente = ?");   params.append(cliente_f)
    if prueba_f:
        clauses.append("prueba = ?");    params.append(prueba_f)
    if modulo_f:
        clauses.append("modulo = ?");    params.append(modulo_f)
    if estado_f in ("ok", "fail"):
        clauses.append("estado = ?");    params.append(estado_f)
    if entorno_f:
        clauses.append("entorno LIKE ?"); params.append(f"%{entorno_f}%")
    if addon_f:
        clauses.append("addon = ?");     params.append(addon_f)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _awhere(where, extra):
    """Añade una condición AND a una cláusula WHERE ya construida."""
    return f"{where} AND {extra}" if where else f"WHERE {extra}"


@app.route("/metricas/opciones")
def metricas_opciones():
    """Valores distintos de cada columna para poblar los dropdowns de filtro."""
    with sqlite3.connect(DB_PATH) as con:
        def col(sql):
            return [r[0] for r in con.execute(sql).fetchall() if r[0]]
        return jsonify({
            "clientes": col("SELECT DISTINCT cliente FROM resultados WHERE cliente!='' ORDER BY cliente"),
            "pruebas":  col("SELECT DISTINCT prueba  FROM resultados                   ORDER BY prueba"),
            "modulos":  col("SELECT DISTINCT modulo  FROM resultados WHERE modulo !='' ORDER BY modulo"),
            "entornos": col("SELECT DISTINCT entorno FROM resultados WHERE entorno!='' ORDER BY entorno"),
            "addons":   col("SELECT DISTINCT addon   FROM resultados WHERE addon  !='' ORDER BY addon"),
        })


@app.route("/metricas/historial")
def metricas_historial():
    """Registros individuales paginados con todos los filtros activos."""
    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(100, max(1, int(request.args.get("per_page", 25))))
    offset   = (page - 1) * per_page
    where, params = _build_filtros(request)

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        total = con.execute(
            f"SELECT COUNT(*) FROM resultados {where}", params
        ).fetchone()[0]
        filas = con.execute(f"""
            SELECT id, fecha, prueba, modulo, estado, dato_entrada, obtenido,
                   cliente, entorno, bd, usuario, duracion_s, addon
            FROM resultados {where}
            ORDER BY fecha DESC LIMIT ? OFFSET ?
        """, params + [per_page, offset]).fetchall()
        return jsonify({
            "total":    total,
            "page":     page,
            "per_page": per_page,
            "pages":    max(1, (total + per_page - 1) // per_page),
            "datos":    [dict(r) for r in filas],
        })


@app.route("/metricas/resumen")
def metricas_resumen():
    where, params = _build_filtros(request)
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        agg = con.execute(f"""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN estado='ok'   THEN 1 ELSE 0 END) as ok,
                   SUM(CASE WHEN estado='fail' THEN 1 ELSE 0 END) as fail,
                   ROUND(AVG(CASE WHEN duracion_s>0 THEN duracion_s END),1) as dur
            FROM resultados {where}
        """, params).fetchone()
        total = agg["total"] or 0
        if total == 0:
            return jsonify({"total": 0, "ok": 0, "fail": 0, "tasa": 0,
                            "peor_prueba": None, "duracion_prom": 0})
        peor = con.execute(f"""
            SELECT prueba, COUNT(*) as cnt FROM resultados
            {_awhere(where, "estado='fail'")}
            GROUP BY prueba ORDER BY cnt DESC LIMIT 1
        """, params).fetchone()
        ok = agg["ok"] or 0
        return jsonify({
            "total": total, "ok": ok, "fail": agg["fail"] or 0,
            "tasa":  round(ok / total * 100, 1),
            "peor_prueba":   dict(peor) if peor else None,
            "duracion_prom": agg["dur"] or 0,
        })


@app.route("/metricas/tendencia")
def metricas_tendencia():
    where, params = _build_filtros(request)
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        filas = con.execute(f"""
            SELECT substr(fecha,1,10) as dia,
                   SUM(CASE WHEN estado='ok'   THEN 1 ELSE 0 END) as ok,
                   SUM(CASE WHEN estado='fail' THEN 1 ELSE 0 END) as fail,
                   COUNT(*) as total
            FROM resultados {where}
            GROUP BY dia ORDER BY dia
        """, params).fetchall()
        return jsonify([dict(r) for r in filas])


@app.route("/metricas/por_prueba")
def metricas_por_prueba():
    where, params = _build_filtros(request)
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        filas = con.execute(f"""
            SELECT prueba, modulo,
                   SUM(CASE WHEN estado='ok'   THEN 1 ELSE 0 END) as ok,
                   SUM(CASE WHEN estado='fail' THEN 1 ELSE 0 END) as fail,
                   COUNT(*) as total,
                   ROUND(AVG(CASE WHEN duracion_s>0 THEN duracion_s END),1) as duracion_prom
            FROM resultados {where}
            GROUP BY prueba ORDER BY fail DESC, total DESC
        """, params).fetchall()
        return jsonify([dict(r) for r in filas])


@app.route("/metricas/por_cliente")
def metricas_por_cliente():
    where, params = _build_filtros(request)
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        filas = con.execute(f"""
            SELECT cliente,
                   SUM(CASE WHEN estado='ok'   THEN 1 ELSE 0 END) as ok,
                   SUM(CASE WHEN estado='fail' THEN 1 ELSE 0 END) as fail,
                   COUNT(*) as total
            FROM resultados {_awhere(where, "cliente!=''")}
            GROUP BY cliente ORDER BY total DESC
        """, params).fetchall()
        return jsonify([dict(r) for r in filas])


@app.route("/metricas/errores")
def metricas_errores():
    n = int(request.args.get("n", 15))
    where, params = _build_filtros(request)
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        filas = con.execute(f"""
            SELECT obtenido, prueba, COUNT(*) as ocurrencias,
                   MAX(fecha) as ultima_vez
            FROM resultados
            {_awhere(where, "estado='fail' AND obtenido!='' AND obtenido IS NOT NULL")}
            GROUP BY obtenido, prueba ORDER BY ocurrencias DESC LIMIT ?
        """, params + [n]).fetchall()
        return jsonify([dict(r) for r in filas])


@app.route("/metricas/addons")
def metricas_addons():
    where, params = _build_filtros(request)
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        filas = con.execute(f"""
            SELECT addon,
                   SUM(CASE WHEN estado='ok'   THEN 1 ELSE 0 END) as ok,
                   SUM(CASE WHEN estado='fail' THEN 1 ELSE 0 END) as fail,
                   COUNT(*) as total
            FROM resultados {_awhere(where, "addon!='' AND addon IS NOT NULL")}
            GROUP BY addon ORDER BY fail DESC, total DESC
        """, params).fetchall()
        return jsonify([dict(r) for r in filas])


@app.route("/metricas/cobertura_addons")
def metricas_cobertura_addons():
    """Matriz de cobertura: por cliente muestra si addon 142/143 fue instalado
    en Pruebas y/o Producción.
    Cada celda: {ok, advertencia, intentos, ultima_fecha}
      ok=True         → al menos un estado='ok' (instalación exitosa nueva)
      advertencia=True → addon ya estaba instalado cuando se verificó (también cuenta como presente)
    """

    ADDONS_TARGET  = {"142", "143"}
    KW_PRUEBAS     = ("PRUEBA", "QA", "TEST", "REPLICA", "SANDBOX")
    # estados que confirman que el addon ESTÁ instalado
    ESTADOS_OK     = {"ok", "advertencia"}
    # estados que solo indican intentos (no confirman presencia del addon)
    ESTADOS_FALLO  = {"fail", "error"}

    def tipo_entorno(entorno: str) -> str:
        t = (entorno or "").upper()
        return "pruebas" if any(kw in t for kw in KW_PRUEBAS) else "produccion"

    def addon_norm(raw: str) -> str:
        return raw.replace("-", "").replace(" ", "").strip()

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        filas = con.execute("""
            SELECT cliente, addon, entorno, estado,
                   MAX(fecha) as ultima_fecha,
                   COUNT(*)   as intentos
            FROM resultados
            WHERE cliente != ''
              AND addon    != ''
              AND addon IS NOT NULL
            GROUP BY cliente, addon, entorno, estado
            ORDER BY cliente, addon, entorno
        """).fetchall()

    clientes: dict = {}
    for r in filas:
        an = addon_norm(r["addon"])
        if an not in ADDONS_TARGET:
            continue
        cli    = r["cliente"]
        tipo   = tipo_entorno(r["entorno"])
        key    = f"a{an}_{tipo}"
        estado = r["estado"]

        if cli not in clientes:
            clientes[cli] = {"cliente": cli}

        if key not in clientes[cli]:
            clientes[cli][key] = {
                "ok": False, "advertencia": False,
                "intentos": 0, "ultima_fecha": None
            }

        clientes[cli][key]["intentos"] += r["intentos"]
        if estado == "ok":
            clientes[cli][key]["ok"] = True
        elif estado == "advertencia":
            clientes[cli][key]["advertencia"] = True
        fecha_actual = clientes[cli][key]["ultima_fecha"]
        if r["ultima_fecha"] and (not fecha_actual or r["ultima_fecha"] > fecha_actual):
            clientes[cli][key]["ultima_fecha"] = r["ultima_fecha"]

    resultado = sorted(clientes.values(), key=lambda x: x["cliente"].upper())
    return jsonify(resultado)


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
