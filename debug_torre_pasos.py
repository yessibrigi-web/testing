"""
Debug paso a paso en Torre REAL (visible).
Hace el login completo y captura exactamente qué necesita cada paso.
Solo necesita: cliente + entorno (sin BD).

Ejecutar: python debug_torre_pasos.py
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
    cliente = input("Cliente (ej: Rizek): ").strip()
    entorno_id = input("Entorno ID (ej: SincoConsRizek): ").strip()

    if not cliente or not entorno_id:
        print("ERROR: necesitas cliente y entorno")
        return

    with sync_playwright() as pw:
        # Usar Chrome del sistema (VISIBLE para que veas)
        browser = pw.chromium.launch(
            headless=False,
            channel="chrome",
        )
        context = browser.new_context(ignore_https_errors=True)
        pagina = context.new_page()

        # ── PASO 1: Cargar Torre ──
        t0 = time.time()
        print(f"\n[PASO 1] Cargando Torre...")
        pagina.goto(CONFIG["url_torre"])
        pagina.wait_for_load_state("networkidle")
        print(f"  OK ({time.time()-t0:.1f}s)")

        # ── PASO 2: Login ──
        t0 = time.time()
        print(f"\n[PASO 2] Login...")
        pagina.get_by_role("textbox", name="UsuarioWindows").fill(CONFIG["usuario"])
        pagina.get_by_role("textbox", name="Contraseña").fill(CONFIG["password"])
        pagina.get_by_role("button", name="Ingresar con Windows").click()
        pagina.wait_for_load_state("networkidle")
        pagina.wait_for_timeout(2000)
        print(f"  OK ({time.time()-t0:.1f}s)")

        # Capturar datos de sesión
        key_pre = pagina.evaluate("() => window.user_central_key || 'NO EXISTE AUN'")
        print(f"  user_central_key (pre): {key_pre}")

        # ── PASO 3: Master ──
        t0 = time.time()
        print(f"\n[PASO 3] Clic en Master...")
        pagina.get_by_title("Master").get_by_role("img").click()
        pagina.wait_for_timeout(1000)
        print(f"  OK ({time.time()-t0:.1f}s)")

        # ── PASO 4: Buscar cliente ──
        t0 = time.time()
        print(f"\n[PASO 4] Buscando cliente '{cliente}'...")
        pagina.get_by_title("Clientes", exact=True).locator("path").click()
        pagina.wait_for_timeout(1500)
        palabras = cliente.split()[:2]
        pagina.locator("#listWidgetClientes").get_by_role("textbox").fill(" ".join(palabras))
        pagina.wait_for_timeout(2000)
        pagina.get_by_role("option").locator("div").filter(
            has_text=palabras[0]
        ).nth(1).click()
        pagina.wait_for_timeout(1500)
        print(f"  OK ({time.time()-t0:.1f}s)")

        # ── PASO 5: Seleccionar entorno ──
        t0 = time.time()
        print(f"\n[PASO 5] Seleccionando entorno '{entorno_id}'...")
        pagina.locator(".contenedor-opcion > .siguienteIcon").first.click()
        pagina.wait_for_timeout(2000)
        pagina.get_by_role("option", name=f"_ {entorno_id}").get_by_role("img").nth(2).click()
        pagina.wait_for_timeout(1500)
        print(f"  OK ({time.time()-t0:.1f}s)")

        # Capturar key DESPUES de seleccionar entorno
        key_post = pagina.evaluate("() => window.user_central_key || 'NO EXISTE'")
        print(f"  user_central_key (post): {key_post}")

        # Capturar cookies antes de Ingresar
        cookies_pre = context.cookies()
        print(f"  Cookies: {len(cookies_pre)}")

        # ── PASO 6: INGRESAR (el momento clave) ──
        print(f"\n[PASO 6] Haciendo clic en 'Ingresar al entorno'...")
        print(f"  OBSERVA LA VENTANA DEL NAVEGADOR...")
        t0 = time.time()

        with pagina.expect_popup(timeout=30000) as popup_info:
            pagina.locator("section").filter(
                has_text=re.compile(r"^IngresarAbrir entorno$")
            ).first.click()

        popup = popup_info.value
        print(f"  Popup abierto: {popup.url}")

        # Esperar a que se estabilice
        popup.wait_for_load_state("networkidle")
        popup.wait_for_timeout(3000)
        print(f"  Popup estable: {popup.url}")
        print(f"  Título: {popup.title()}")
        print(f"  OK ({time.time()-t0:.1f}s)")

        # Capturar cookies del popup
        cookies_post = context.cookies()
        new_cookies = [c for c in cookies_post if c not in cookies_pre]
        print(f"\n  Cookies totales: {len(cookies_post)}")
        print(f"  Cookies nuevas: {len(new_cookies)}")
        for c in cookies_post:
            print(f"    {c['name']}={c['value'][:30]}... domain={c.get('domain','')} path={c.get('path','')}")

        # Capturar storage_state completo
        estado = context.storage_state()
        print(f"\n  Storage state: {len(estado.get('cookies',[]))} cookies, {len(estado.get('origins',[]))} origins")

        # ── PAUSA: ver qué pasó ──
        print(f"\n{'='*60}")
        print(f"  URL FINAL DEL POPUP: {popup.url}")
        print(f"  TITULO: {popup.title()}")
        print(f"{'='*60}")

        if "Seleccion" in popup.url:
            print(f"\n  ¡EXITO! Estamos en Seleccion. Hay dropdown de empresa.")
            # Capturar opciones del dropdown
            try:
                opciones = popup.locator("#ddlEmpresa option").all()
                print(f"  Empresas disponibles:")
                for opt in opciones:
                    print(f"    - {opt.text_content().strip()}")
            except Exception:
                print(f"  No se encontró dropdown #ddlEmpresa")

        elif "Default" in popup.url:
            print(f"\n  ¡EXITO! Directo en el ERP.")

        elif "Login" in popup.url:
            print(f"\n  FALLO: Quedó en Login. La autenticación no pasó.")
            try:
                print(f"  HTML preview: {popup.content()[:500]}")
            except:
                pass

        else:
            print(f"\n  Página inesperada: {popup.url}")

        # Guardar storage_state
        storage_path = "debug_storage_state.json"
        context.storage_state(path=storage_path)
        print(f"\n  Storage state guardado en: {storage_path}")

        # ── Mantener abierto para inspección ──
        input("\n  >>> Presiona ENTER para cerrar el navegador <<<")
        browser.close()


if __name__ == "__main__":
    main()
