"""
Intercepta el formulario dinámico que Torre.js crea al hacer clic en "Ingresar al entorno".
Captura los campos POST, la URL destino, y todo lo necesario para replicar sin navegador.

Ejecutar: python debug_interceptar_form.py
"""

import json
import time
import re
from playwright.sync_api import sync_playwright

CONFIG = {
    "usuario":   "yessica.olaya",
    "password":  "Jeronimo2026",
    "url_torre": "https://core.sincoerp.com/SincoSoporte/Torre.html",
}


def main():
    cliente = input("Cliente (nombre parcial, ej: Rizek): ").strip()
    entorno_id = input("Entorno ID (ej: SincoConsRizek_PRBINT): ").strip()

    if not cliente or not entorno_id:
        print("ERROR: necesitas proporcionar cliente y entorno")
        return

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--window-position=-32000,-32000", "--window-size=1,1"],
        )
        context = browser.new_context(ignore_https_errors=True)
        pagina = context.new_page()

        # ── Login en Torre ──
        print("[1] Cargando Torre...")
        pagina.goto(CONFIG["url_torre"])
        pagina.wait_for_load_state("networkidle")

        print("[2] Login...")
        pagina.get_by_role("textbox", name="UsuarioWindows").fill(CONFIG["usuario"])
        pagina.get_by_role("textbox", name="Contraseña").fill(CONFIG["password"])
        pagina.get_by_role("button", name="Ingresar con Windows").click()
        pagina.wait_for_load_state("networkidle")
        pagina.wait_for_timeout(2000)

        # ── Capturar tokenAuth y datos de login ──
        print("[3] Extrayendo datos de sesión de Torre...")
        torre_data = pagina.evaluate("""() => {
            const result = {};
            // Buscar en localStorage
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                result['ls_' + key] = localStorage.getItem(key);
            }
            // Buscar en sessionStorage
            for (let i = 0; i < sessionStorage.length; i++) {
                const key = sessionStorage.key(i);
                result['ss_' + key] = sessionStorage.getItem(key);
            }
            // Buscar variables globales relevantes
            const globalVars = ['token', 'tokenAuth', 'usuario', 'trabajador',
                               'conexion', 'connection', 'hub', 'keyLogin',
                               'datosLogin', 'datosUsuario', 'llaveLogin',
                               'keyLoginCentralizado', 'loginKey', 'accessToken'];
            for (const v of globalVars) {
                if (window[v] !== undefined) {
                    try {
                        result['global_' + v] = JSON.stringify(window[v]).substring(0, 500);
                    } catch(e) {
                        result['global_' + v] = String(window[v]).substring(0, 500);
                    }
                }
            }
            return result;
        }""")
        print(f"  Datos de sesión Torre: {json.dumps(torre_data, indent=2)}")

        # ── Seleccionar Master, Cliente, Entorno ──
        print("[4] Seleccionando Master...")
        pagina.get_by_title("Master").get_by_role("img").click()
        pagina.wait_for_timeout(1000)

        print("[5] Seleccionando cliente...")
        pagina.get_by_title("Clientes", exact=True).locator("path").click()
        pagina.wait_for_timeout(1500)
        palabras = cliente.split()[:2]
        pagina.locator("#listWidgetClientes").get_by_role("textbox").fill(" ".join(palabras))
        pagina.wait_for_timeout(2000)
        pagina.get_by_role("option").locator("div").filter(
            has_text=palabras[0]
        ).nth(1).click()
        pagina.wait_for_timeout(1500)

        print("[6] Seleccionando entorno...")
        pagina.locator(".contenedor-opcion > .siguienteIcon").first.click()
        pagina.wait_for_timeout(2000)
        pagina.get_by_role("option", name=f"_ {entorno_id}").get_by_role("img").nth(2).click()
        pagina.wait_for_timeout(1500)

        # ══════════════════════════════════════════════
        # INTERCEPTAR: Monkey-patch ANTES de clic en Ingresar
        # ══════════════════════════════════════════════
        print("[7] Instalando interceptores JS...")

        pagina.evaluate("""() => {
            // Interceptar window.open
            window.__intercepted = { forms: [], windowOpens: [], formSubmits: [] };

            const origOpen = window.open;
            window.open = function(...args) {
                window.__intercepted.windowOpens.push({
                    url: args[0],
                    target: args[1],
                    features: args[2],
                    timestamp: Date.now()
                });
                console.log('INTERCEPTED window.open:', args[0]);
                return origOpen.apply(this, args);
            };

            // Interceptar document.createElement para capturar forms dinámicos
            const origCreate = document.createElement.bind(document);
            document.createElement = function(tag) {
                const el = origCreate(tag);
                if (tag.toLowerCase() === 'form') {
                    // Observar cuando se configure el form
                    const origSubmit = el.submit.bind(el);
                    el.submit = function() {
                        const formData = {
                            action: el.action,
                            method: el.method,
                            target: el.target,
                            enctype: el.enctype,
                            inputs: [],
                            timestamp: Date.now()
                        };
                        const inputs = el.querySelectorAll('input, textarea, select');
                        inputs.forEach(inp => {
                            formData.inputs.push({
                                name: inp.name,
                                type: inp.type,
                                value: inp.value
                            });
                        });
                        window.__intercepted.formSubmits.push(formData);
                        console.log('INTERCEPTED form.submit:', JSON.stringify(formData));
                        return origSubmit();
                    };
                    window.__intercepted.forms.push({tag, timestamp: Date.now()});
                }
                return el;
            };

            // Interceptar HTMLFormElement.prototype.submit
            const origProtoSubmit = HTMLFormElement.prototype.submit;
            HTMLFormElement.prototype.submit = function() {
                const formData = {
                    action: this.action,
                    method: this.method,
                    target: this.target,
                    enctype: this.enctype,
                    inputs: [],
                    timestamp: Date.now()
                };
                const inputs = this.querySelectorAll('input, textarea, select');
                inputs.forEach(inp => {
                    formData.inputs.push({
                        name: inp.name,
                        type: inp.type,
                        value: inp.value
                    });
                });
                window.__intercepted.formSubmits.push(formData);
                console.log('INTERCEPTED proto.submit:', JSON.stringify(formData));
                return origProtoSubmit.call(this);
            };

            // Interceptar fetch y XMLHttpRequest
            const origFetch = window.fetch;
            window.fetch = function(...args) {
                window.__intercepted.fetches = window.__intercepted.fetches || [];
                window.__intercepted.fetches.push({
                    url: args[0],
                    options: args[1] ? JSON.stringify(args[1]).substring(0, 500) : null,
                    timestamp: Date.now()
                });
                return origFetch.apply(this, args);
            };
        }""")

        # También capturar console.log
        console_msgs = []
        pagina.on("console", lambda msg: console_msgs.append({
            "type": msg.type,
            "text": msg.text,
            "timestamp": time.time()
        }))

        # ══════════════════════════════════════════════
        # CLIC EN INGRESAR
        # ══════════════════════════════════════════════
        print("[8] Haciendo clic en 'Ingresar al entorno'...")

        # Capturar request del popup
        popup_nav_request = []
        def on_request(req):
            if req.is_navigation_request():
                popup_nav_request.append({
                    "method": req.method,
                    "url": req.url,
                    "post_data": req.post_data[:5000] if req.post_data else None,
                    "headers": dict(req.headers),
                })
        pagina.on("request", on_request)

        try:
            with pagina.expect_popup(timeout=15000) as popup_info:
                pagina.locator("section").filter(
                    has_text=re.compile(r"^IngresarAbrir entorno$")
                ).first.click()

            popup = popup_info.value

            # Capturar requests del popup
            def on_popup_request(req):
                if req.is_navigation_request() or req.resource_type in ("document", "xhr"):
                    popup_nav_request.append({
                        "source": "popup",
                        "method": req.method,
                        "url": req.url,
                        "post_data": req.post_data[:5000] if req.post_data else None,
                        "headers": {k:v for k,v in req.headers.items()
                                   if k.lower() in ['content-type', 'authorization', 'cookie', 'referer']},
                    })

            popup.on("request", on_popup_request)
            popup.wait_for_load_state("networkidle")
            popup.wait_for_timeout(3000)

            print(f"  Popup URL: {popup.url}")
            print(f"  Popup título: {popup.title()}")

        except Exception as e:
            print(f"  Popup error: {e}")

        # ══════════════════════════════════════════════
        # RECOGER DATOS INTERCEPTADOS
        # ══════════════════════════════════════════════
        print("\n[9] Recogiendo datos interceptados...")

        intercepted = pagina.evaluate("() => window.__intercepted")

        # Extraer también variables JS que Torre pudo haber seteado
        print("[10] Extrayendo variables JS post-Ingresar...")
        post_vars = pagina.evaluate("""() => {
            const result = {};
            // Buscar todas las variables globales que no son built-in
            const builtins = new Set(['window','self','document','name','location',
                'customElements','history','navigation','locationbar','menubar',
                'personalbar','scrollbars','statusbar','toolbar','status','closed',
                'frames','length','top','opener','parent','frameElement','navigator',
                'origin','external','screen','visualViewport','innerWidth','innerHeight',
                'outerWidth','outerHeight','devicePixelRatio','screenLeft','screenTop',
                'screenX','screenY','pageXOffset','pageYOffset','scrollX','scrollY',
                'chrome','caches','cookieStore','onpointerrawupdate','speechSynthesis',
                'isSecureContext','crossOriginIsolated','scheduler','alert','atob','blur',
                'btoa','cdc_adoQpoasnfa76pfcZLmcfl_Array','cdc_adoQpoasnfa76pfcZLmcfl_JSON',
                'cdc_adoQpoasnfa76pfcZLmcfl_Object','cdc_adoQpoasnfa76pfcZLmcfl_Promise',
                'cdc_adoQpoasnfa76pfcZLmcfl_Proxy','cdc_adoQpoasnfa76pfcZLmcfl_Symbol',
                'clearInterval','clearTimeout','close','confirm','createImageBitmap',
                'fetch','find','focus','getComputedStyle','getSelection',
                'matchMedia','moveBy','moveTo','open','postMessage','print','prompt',
                'queueMicrotask','reportError','requestAnimationFrame','requestIdleCallback',
                'resizeBy','resizeTo','scroll','scrollBy','scrollTo','setInterval',
                'setTimeout','stop','structuredClone','webkitCancelAnimationFrame',
                'webkitRequestAnimationFrame','getScreenDetails','queryLocalFonts',
                'showDirectoryPicker','showOpenFilePicker','showSaveFilePicker',
                'originAgentCluster','trustedTypes','crossOriginEmbedderPolicy',
                'performance','onbeforetoggle']);

            for (const key of Object.keys(window)) {
                if (builtins.has(key)) continue;
                if (key.startsWith('on')) continue;
                try {
                    const val = window[key];
                    if (typeof val === 'string' || typeof val === 'number' || typeof val === 'boolean') {
                        result[key] = String(val).substring(0, 300);
                    } else if (typeof val === 'object' && val !== null) {
                        result[key] = JSON.stringify(val).substring(0, 500);
                    }
                } catch(e) {}
            }
            return result;
        }""")

        # ══════════════════════════════════════════════
        # GUARDAR TODO
        # ══════════════════════════════════════════════
        resultado = {
            "intercepted_forms": intercepted.get("formSubmits", []),
            "intercepted_window_opens": intercepted.get("windowOpens", []),
            "intercepted_forms_created": intercepted.get("forms", []),
            "intercepted_fetches": intercepted.get("fetches", []),
            "popup_navigation_requests": popup_nav_request,
            "console_messages": [m for m in console_msgs if "INTERCEPTED" in m.get("text", "")],
            "all_console_messages": console_msgs[-20:],  # últimos 20
            "torre_js_variables": post_vars,
            "cookies_final": context.cookies(),
        }

        browser.close()

    # Guardar
    output = "debug_form_interceptado.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, default=str, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"RESULTADOS GUARDADOS: {output}")
    print(f"{'='*60}")

    # Resumen en consola
    print(f"\nForms interceptados: {len(resultado['intercepted_forms'])}")
    for fm in resultado["intercepted_forms"]:
        print(f"  → action={fm.get('action', '?')}")
        print(f"    method={fm.get('method', '?')} target={fm.get('target', '?')}")
        for inp in fm.get("inputs", []):
            val = inp.get('value', '')
            if len(val) > 80:
                val = val[:80] + "..."
            print(f"    [{inp.get('name', '?')}] = {val}")

    print(f"\nwindow.open interceptados: {len(resultado['intercepted_window_opens'])}")
    for wo in resultado["intercepted_window_opens"]:
        print(f"  → url={wo.get('url', '?')}")

    print(f"\nNavigation requests del popup: {len(resultado['popup_navigation_requests'])}")
    for nr in resultado["popup_navigation_requests"]:
        print(f"  → [{nr['method']}] {nr['url'][:100]}")
        if nr.get("post_data"):
            print(f"    POST: {nr['post_data'][:300]}")

    # Variables JS interesantes
    interesting_keys = [k for k in post_vars.keys() if any(
        term in k.lower() for term in ['token', 'login', 'key', 'auth', 'session',
                                        'usuario', 'user', 'entorno', 'url', 'llave']
    )]
    if interesting_keys:
        print(f"\nVariables JS relevantes:")
        for k in interesting_keys:
            print(f"  {k} = {post_vars[k][:200]}")


if __name__ == "__main__":
    main()
