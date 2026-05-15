"""
Diagnóstico COMPLETO del flujo de Torre.html → ERP
Captura TODA la información necesaria para entender y replicar
el proceso de autenticación sin necesidad del navegador.

Ejecutar: python debug_torre_completo.py
"""

import json
import time
import re
import sys
from datetime import datetime
from playwright.sync_api import sync_playwright

CONFIG = {
    "usuario":   "yessica.olaya",
    "password":  "Jeronimo2026",
    "url_torre": "https://core.sincoerp.com/SincoSoporte/Torre.html",
}

# ─── Datos que vamos recolectando ───
INFORME = {
    "timestamp": datetime.now().isoformat(),
    "fases": {},
}


def fase(nombre):
    """Registra una nueva fase en el informe."""
    print(f"\n{'='*60}")
    print(f"  FASE: {nombre}")
    print(f"{'='*60}")
    INFORME["fases"][nombre] = {}
    return INFORME["fases"][nombre]


def main():
    # Preguntar qué cliente y entorno usar
    cliente = input("Cliente (nombre parcial, ej: Rizek): ").strip()
    entorno_id = input("Entorno ID (ej: SincoConsRizek_PRBINT): ").strip()

    if not cliente or not entorno_id:
        print("ERROR: necesitas proporcionar cliente y entorno")
        sys.exit(1)

    todas_requests = []
    todas_responses = {}

    def capturar_request(req):
        info = {
            "timestamp": time.time(),
            "method": req.method,
            "url": req.url,
            "resource_type": req.resource_type,
            "is_navigation": req.is_navigation_request(),
            "redirected_from": req.redirected_from.url if req.redirected_from else None,
            "headers": dict(req.headers),
            "post_data": req.post_data[:2000] if req.post_data else None,
        }
        todas_requests.append(info)

    def capturar_response(resp):
        try:
            todas_responses[resp.url] = {
                "status": resp.status,
                "status_text": resp.status_text,
                "headers": dict(resp.headers),
                "body_preview": None,
            }
            # Capturar body de respuestas de API/HTML (no assets)
            ct = resp.headers.get("content-type", "")
            if any(t in ct for t in ["json", "html", "text", "form"]):
                try:
                    todas_responses[resp.url]["body_preview"] = resp.text()[:3000]
                except Exception:
                    pass
        except Exception:
            pass

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--window-position=-32000,-32000", "--window-size=1,1"],
        )
        context = browser.new_context(ignore_https_errors=True)
        pagina = context.new_page()

        # Interceptar TODO desde el inicio
        pagina.on("request", capturar_request)
        pagina.on("response", capturar_response)

        # ══════════════════════════════════════════════
        # FASE 1: CARGAR TORRE.HTML
        # ══════════════════════════════════════════════
        f = fase("1_cargar_torre")
        t0 = time.time()
        pagina.goto(CONFIG["url_torre"])
        pagina.wait_for_load_state("networkidle")
        f["duracion_seg"] = round(time.time() - t0, 2)
        f["url"] = pagina.url
        f["titulo"] = pagina.title()
        f["cookies_pre_login"] = context.cookies()
        print(f"  URL: {pagina.url}")
        print(f"  Cookies: {len(f['cookies_pre_login'])}")
        print(f"  Duración: {f['duracion_seg']}s")

        # ══════════════════════════════════════════════
        # FASE 2: LOGIN (usuario + password → Ingresar con Windows)
        # ══════════════════════════════════════════════
        f = fase("2_login")
        t0 = time.time()

        # Capturar qué JS hace Torre con las credenciales
        # Antes del login, extraer la función de encriptación
        try:
            encrypt_func = pagina.evaluate("""() => {
                // Buscar funciones de encriptación en el scope global
                const resultado = {};
                if (typeof CryptoJS !== 'undefined') resultado.cryptojs = true;
                if (typeof AES !== 'undefined') resultado.aes = true;
                // Buscar en los scripts cargados
                const scripts = Array.from(document.scripts).map(s => s.src);
                resultado.scripts = scripts.filter(s => s.includes('crypto') || s.includes('aes') || s.includes('encrypt'));
                // Buscar la función de login
                if (typeof Ingresar === 'function') resultado.ingresar = Ingresar.toString().substring(0, 500);
                if (typeof Login === 'function') resultado.login = Login.toString().substring(0, 500);
                if (typeof validarLogin === 'function') resultado.validarLogin = validarLogin.toString().substring(0, 500);
                // Buscar cualquier función global que mencione encrypt/AES
                const globalFuncs = Object.keys(window).filter(k => typeof window[k] === 'function');
                resultado.funciones_globales = globalFuncs.filter(f =>
                    f.toLowerCase().includes('encrypt') ||
                    f.toLowerCase().includes('login') ||
                    f.toLowerCase().includes('ingresar') ||
                    f.toLowerCase().includes('aes') ||
                    f.toLowerCase().includes('validar')
                );
                return resultado;
            }""")
            f["encriptacion_js"] = encrypt_func
            print(f"  Funciones encontradas: {json.dumps(encrypt_func, indent=2)}")
        except Exception as e:
            f["encriptacion_js_error"] = str(e)

        # Llenar credenciales
        pagina.get_by_role("textbox", name="UsuarioWindows").fill(CONFIG["usuario"])
        pagina.get_by_role("textbox", name="Contraseña").fill(CONFIG["password"])

        # Capturar el estado del formulario antes de enviar
        try:
            form_state = pagina.evaluate("""() => {
                const inputs = Array.from(document.querySelectorAll('input'));
                return inputs.map(i => ({
                    name: i.name || i.id,
                    type: i.type,
                    value: i.value ? i.value.substring(0, 100) : '',
                }));
            }""")
            f["form_inputs_pre_submit"] = form_state
        except Exception:
            pass

        # Marcar requests antes del clic para identificar las del login
        n_requests_antes = len(todas_requests)

        pagina.get_by_role("button", name="Ingresar con Windows").click()
        pagina.wait_for_load_state("networkidle")
        pagina.wait_for_timeout(2000)

        f["duracion_seg"] = round(time.time() - t0, 2)

        # Requests generadas por el login
        login_requests = todas_requests[n_requests_antes:]
        f["requests_login"] = []
        for r in login_requests:
            if r["resource_type"] in ("document", "xhr", "fetch"):
                entry = {
                    "method": r["method"],
                    "url": r["url"],
                    "type": r["resource_type"],
                    "post_data": r["post_data"],
                }
                # Agregar response si existe
                if r["url"] in todas_responses:
                    entry["response_status"] = todas_responses[r["url"]]["status"]
                    entry["response_body"] = todas_responses[r["url"]].get("body_preview", "")[:500]
                f["requests_login"].append(entry)
                print(f"  → {r['method']} {r['url'][:80]} [{todas_responses.get(r['url'], {}).get('status', '?')}]")

        f["cookies_post_login"] = context.cookies()
        f["url_post_login"] = pagina.url
        print(f"  Cookies post-login: {len(f['cookies_post_login'])}")
        print(f"  Duración: {f['duracion_seg']}s")

        # ══════════════════════════════════════════════
        # FASE 3: SELECCIONAR MASTER
        # ══════════════════════════════════════════════
        f = fase("3_master")
        t0 = time.time()
        pagina.get_by_title("Master").get_by_role("img").click()
        pagina.wait_for_timeout(1000)
        f["duracion_seg"] = round(time.time() - t0, 2)
        print(f"  Duración: {f['duracion_seg']}s")

        # ══════════════════════════════════════════════
        # FASE 4: BUSCAR Y SELECCIONAR CLIENTE
        # ══════════════════════════════════════════════
        f = fase("4_seleccionar_cliente")
        t0 = time.time()
        n_requests_antes = len(todas_requests)

        pagina.get_by_title("Clientes", exact=True).locator("path").click()
        pagina.wait_for_timeout(1500)
        palabras = cliente.split()[:2]
        pagina.locator("#listWidgetClientes").get_by_role("textbox").fill(" ".join(palabras))
        pagina.wait_for_timeout(2000)
        pagina.get_by_role("option").locator("div").filter(
            has_text=palabras[0]
        ).nth(1).click()
        pagina.wait_for_timeout(1500)

        f["duracion_seg"] = round(time.time() - t0, 2)

        # Requests de selección de cliente
        cliente_requests = todas_requests[n_requests_antes:]
        f["requests"] = []
        for r in cliente_requests:
            if r["resource_type"] in ("xhr", "fetch"):
                f["requests"].append({
                    "method": r["method"],
                    "url": r["url"],
                    "post_data": r["post_data"],
                })
                print(f"  → {r['method']} {r['url'][:80]}")
        print(f"  Duración: {f['duracion_seg']}s")

        # ══════════════════════════════════════════════
        # FASE 5: SELECCIONAR ENTORNO
        # ══════════════════════════════════════════════
        f = fase("5_seleccionar_entorno")
        t0 = time.time()
        n_requests_antes = len(todas_requests)

        pagina.locator(".contenedor-opcion > .siguienteIcon").first.click()
        pagina.wait_for_timeout(2000)
        pagina.get_by_role("option", name=f"_ {entorno_id}").get_by_role("img").nth(2).click()
        pagina.wait_for_timeout(1500)

        f["duracion_seg"] = round(time.time() - t0, 2)

        # Requests de selección de entorno
        entorno_requests = todas_requests[n_requests_antes:]
        f["requests"] = []
        for r in entorno_requests:
            if r["resource_type"] in ("xhr", "fetch"):
                f["requests"].append({
                    "method": r["method"],
                    "url": r["url"],
                    "post_data": r["post_data"],
                })
                print(f"  → {r['method']} {r['url'][:80]}")
        print(f"  Duración: {f['duracion_seg']}s")

        # Capturar cookies antes de Ingresar
        f["cookies_pre_ingresar"] = context.cookies()

        # ══════════════════════════════════════════════
        # FASE 6: INGRESAR AL ENTORNO (EL MOMENTO CLAVE)
        # ══════════════════════════════════════════════
        f = fase("6_ingresar_entorno")
        t0 = time.time()
        n_requests_antes = len(todas_requests)

        # Capturar qué hace el JS del botón Ingresar
        try:
            boton_info = pagina.evaluate("""() => {
                // Buscar el botón o link de Ingresar
                const elements = document.querySelectorAll('section, a, button');
                const results = [];
                for (const el of elements) {
                    if (el.textContent && el.textContent.includes('Ingresar')) {
                        results.push({
                            tag: el.tagName,
                            id: el.id,
                            className: el.className,
                            onclick: el.onclick ? el.onclick.toString().substring(0, 500) : null,
                            href: el.href || null,
                            innerHTML: el.innerHTML.substring(0, 500),
                        });
                    }
                }
                return results;
            }""")
            f["boton_ingresar_info"] = boton_info
            for b in boton_info:
                print(f"  Botón: <{b['tag']}> onclick={b.get('onclick', 'N/A')[:100]}")
                if b.get('href'):
                    print(f"         href={b['href']}")
        except Exception as e:
            f["boton_info_error"] = str(e)

        # Capturar el form HTML si hay uno
        try:
            form_info = pagina.evaluate("""() => {
                const forms = document.querySelectorAll('form');
                return Array.from(forms).map(f => ({
                    id: f.id,
                    action: f.action,
                    method: f.method,
                    target: f.target,
                    innerHTML_preview: f.innerHTML.substring(0, 1000),
                    inputs: Array.from(f.querySelectorAll('input, select, textarea')).map(i => ({
                        name: i.name,
                        type: i.type,
                        value: i.value ? i.value.substring(0, 200) : '',
                    })),
                }));
            }""")
            f["formularios_pagina"] = form_info
            for fm in form_info:
                print(f"  Form: action={fm['action'][:100]} method={fm['method']} target={fm['target']}")
                for inp in fm.get("inputs", []):
                    val_preview = inp['value'][:50] + "..." if len(inp.get('value', '')) > 50 else inp.get('value', '')
                    print(f"    → {inp['name']}: [{inp['type']}] = {val_preview}")
        except Exception as e:
            f["form_error"] = str(e)

        # Hacer clic en Ingresar y capturar popup
        url_changes = []
        popup_requests = []

        with pagina.expect_popup() as popup_info:
            pagina.locator("section").filter(
                has_text=re.compile(r"^IngresarAbrir entorno$")
            ).first.click()

        popup = popup_info.value
        url_changes.append({"url": popup.url, "momento": "popup_inicial", "time": time.time()})
        print(f"  Popup abierto en: {popup.url}")

        def on_popup_request(req):
            popup_requests.append({
                "timestamp": time.time(),
                "method": req.method,
                "url": req.url,
                "resource_type": req.resource_type,
                "is_navigation": req.is_navigation_request(),
                "headers": {k: v for k, v in req.headers.items() if k.lower() in [
                    'authorization', 'cookie', 'content-type', 'referer', 'origin',
                    'www-authenticate', 'x-requested-with'
                ]},
                "post_data": req.post_data[:2000] if req.post_data else None,
            })

        popup_responses = {}
        def on_popup_response(resp):
            try:
                info = {
                    "status": resp.status,
                    "headers": {k: v for k, v in resp.headers.items() if k.lower() in [
                        'set-cookie', 'location', 'www-authenticate', 'content-type',
                        'x-aspnet-version', 'server'
                    ]},
                }
                if resp.status in (301, 302, 303, 307, 308):
                    info["redirect_to"] = resp.headers.get("location", "")
                ct = resp.headers.get("content-type", "")
                if "html" in ct:
                    try:
                        info["html_preview"] = resp.text()[:1000]
                    except:
                        pass
                popup_responses[resp.url] = info
            except:
                pass

        popup.on("request", on_popup_request)
        popup.on("response", on_popup_response)

        def on_frame_nav(frame):
            if frame == popup.main_frame:
                url_changes.append({
                    "url": frame.url,
                    "momento": "frame_navigated",
                    "time": time.time()
                })
                print(f"  → Salto a: {frame.url}")

        popup.on("framenavigated", on_frame_nav)

        popup.wait_for_load_state("networkidle")
        popup.wait_for_timeout(5000)

        url_changes.append({"url": popup.url, "momento": "final", "time": time.time()})
        f["duracion_seg"] = round(time.time() - t0, 2)
        f["saltos_url"] = url_changes
        f["url_final"] = popup.url
        f["titulo_final"] = popup.title()

        # Cookies finales (del contexto completo)
        f["cookies_finales"] = context.cookies()

        # Requests del popup (solo las interesantes)
        f["popup_requests"] = [r for r in popup_requests
                               if r["resource_type"] in ("document", "xhr", "fetch")
                               or r["is_navigation"]]

        # Responses del popup
        f["popup_responses"] = popup_responses

        # HTML de la página final
        try:
            f["html_final"] = popup.content()[:3000]
        except:
            pass

        print(f"\n  URL final: {popup.url}")
        print(f"  Título: {popup.title()}")
        print(f"  Cookies totales: {len(f['cookies_finales'])}")
        print(f"  Duración: {f['duracion_seg']}s")

        # Requests del popup detalladas
        print(f"\n  Popup requests ({len(f['popup_requests'])}):")
        for r in f["popup_requests"]:
            resp = popup_responses.get(r["url"], {})
            print(f"    [{r['method']}] {r['url'][:80]} → {resp.get('status', '?')}")
            if r.get("headers"):
                for k, v in r["headers"].items():
                    print(f"      {k}: {v[:80]}")
            if r.get("post_data"):
                print(f"      POST: {r['post_data'][:200]}")

        browser.close()

    # ══════════════════════════════════════════════
    # GUARDAR INFORME COMPLETO
    # ══════════════════════════════════════════════
    output_file = "debug_torre_informe.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(INFORME, f, indent=2, default=str, ensure_ascii=False)
    print(f"\n{'='*60}")
    print(f"  INFORME GUARDADO: {output_file}")
    print(f"{'='*60}")

    # También guardar un resumen legible
    resumen_file = "debug_torre_resumen.txt"
    with open(resumen_file, "w", encoding="utf-8") as f:
        f.write("RESUMEN DEL FLUJO DE TORRE\n")
        f.write("=" * 60 + "\n\n")

        for nombre, data in INFORME["fases"].items():
            f.write(f"\n{'─'*40}\n")
            f.write(f"FASE: {nombre}\n")
            f.write(f"{'─'*40}\n")
            if "duracion_seg" in data:
                f.write(f"Duración: {data['duracion_seg']}s\n")
            if "url" in data:
                f.write(f"URL: {data['url']}\n")
            if "url_final" in data:
                f.write(f"URL final: {data['url_final']}\n")
            if "saltos_url" in data:
                f.write("Saltos:\n")
                for s in data["saltos_url"]:
                    f.write(f"  {s['momento']}: {s['url']}\n")
            if "requests_login" in data:
                f.write("Requests de login:\n")
                for r in data["requests_login"]:
                    f.write(f"  {r['method']} {r['url']}\n")
                    if r.get("post_data"):
                        f.write(f"    POST: {r['post_data'][:300]}\n")
                    if r.get("response_body"):
                        f.write(f"    RESP: {r['response_body'][:300]}\n")
            if "formularios_pagina" in data:
                f.write("Formularios:\n")
                for fm in data["formularios_pagina"]:
                    f.write(f"  Form: action={fm['action']} method={fm['method']} target={fm['target']}\n")
                    for inp in fm.get("inputs", []):
                        f.write(f"    {inp['name']}: [{inp['type']}] = {inp.get('value', '')[:100]}\n")
            if "cookies_finales" in data:
                f.write(f"Cookies ({len(data['cookies_finales'])}):\n")
                for c in data["cookies_finales"]:
                    f.write(f"  {c['name']}={c['value'][:50]}... domain={c.get('domain','')} path={c.get('path','')}\n")
            f.write("\n")

    print(f"  RESUMEN GUARDADO: {resumen_file}")


if __name__ == "__main__":
    main()
