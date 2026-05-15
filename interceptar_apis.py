"""
interceptar_apis.py
Abre Torre.html con Playwright e intercepta TODAS las llamadas de red (XHR, fetch, etc.)
para descubrir las APIs reales que usa la página.

Uso:
  python interceptar_apis.py

Instrucciones:
  1. Se abrirá el navegador con Torre.html
  2. Haz login manualmente
  3. Busca un cliente, selecciona entornos, abre bases de datos
  4. Cada llamada de red se imprime en la consola con URL, método, headers y body
  5. Cierra el navegador cuando termines
  6. Se genera un archivo 'apis_capturadas.json' con todas las llamadas
"""

import json
from datetime import datetime
from playwright.sync_api import sync_playwright

URL_TORRE = "https://core.sincoerp.com/SincoSoporte/Torre.html"

llamadas = []


def on_request(request):
    url = request.url
    # Filtrar recursos estáticos (imágenes, CSS, fonts, etc.)
    extensiones_ignorar = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico',
                           '.css', '.woff', '.woff2', '.ttf', '.eot')
    if any(url.lower().endswith(ext) for ext in extensiones_ignorar):
        return

    metodo = request.method
    headers = dict(request.headers)
    body = None
    try:
        body = request.post_data
    except Exception:
        pass

    entrada = {
        "timestamp": datetime.now().isoformat(),
        "method":    metodo,
        "url":       url,
        "headers":   headers,
        "body":      body,
    }
    llamadas.append(entrada)

    # Imprimir en consola con formato legible
    print(f"\n{'='*80}")
    print(f"  {metodo} {url}")
    if body:
        print(f"  BODY: {body[:500]}")
    print(f"{'='*80}")


def on_response(response):
    url = response.url
    extensiones_ignorar = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico',
                           '.css', '.woff', '.woff2', '.ttf', '.eot')
    if any(url.lower().endswith(ext) for ext in extensiones_ignorar):
        return

    status = response.status
    content_type = response.headers.get("content-type", "")

    # Solo capturar respuestas JSON o de APIs
    if "json" in content_type or "xml" in content_type or "text/plain" in content_type:
        try:
            body = response.text()
            # Truncar respuestas muy largas para la consola
            preview = body[:1000] + "..." if len(body) > 1000 else body
            print(f"  ← RESPONSE [{status}] {content_type}")
            print(f"  {preview}")

            # Guardar respuesta completa en las llamadas
            for entrada in reversed(llamadas):
                if entrada["url"] == url and "response" not in entrada:
                    entrada["response"] = {
                        "status":       status,
                        "content_type": content_type,
                        "body":         body[:5000],  # limitar tamaño
                    }
                    break
        except Exception:
            pass


def main():
    print("=" * 60)
    print("  INTERCEPTOR DE APIs - Torre.html")
    print("=" * 60)
    print()
    print("Instrucciones:")
    print("  1. Haz login en Torre.html")
    print("  2. Busca clientes, selecciona entornos, abre bases de datos")
    print("  3. Observa las APIs que aparecen en esta consola")
    print("  4. Cierra el navegador cuando termines")
    print()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(ignore_https_errors=True)
        pagina  = context.new_page()

        # Registrar interceptores
        pagina.on("request",  on_request)
        pagina.on("response", on_response)

        pagina.goto(URL_TORRE)

        # Esperar a que el usuario cierre el navegador
        try:
            pagina.wait_for_event("close", timeout=600000)  # 10 minutos máximo
        except Exception:
            pass

        browser.close()

    # Guardar todas las llamadas capturadas
    archivo = "apis_capturadas.json"
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(llamadas, f, indent=2, ensure_ascii=False)

    print(f"\n\nCapturadas {len(llamadas)} llamadas de red.")
    print(f"Guardadas en: {archivo}")

    # Resumen de APIs únicas (solo las que parecen APIs, no recursos estáticos)
    apis = set()
    for ll in llamadas:
        url = ll["url"]
        if any(x in url for x in [".js", ".html", "favicon", "fonts.g"]):
            continue
        if ll["method"] == "POST" or "api" in url.lower() or "service" in url.lower() or "handler" in url.lower() or "ashx" in url.lower() or "asmx" in url.lower() or "svc" in url.lower():
            apis.add(f"{ll['method']} {url.split('?')[0]}")

    if apis:
        print("\n" + "=" * 60)
        print("  APIs DETECTADAS:")
        print("=" * 60)
        for api in sorted(apis):
            print(f"  → {api}")


if __name__ == "__main__":
    main()
