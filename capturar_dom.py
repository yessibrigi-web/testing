"""
Script interactivo: tu navegas manualmente, y cuando llegas a la pagina
del DataGridPro, presiona Enter en la terminal para capturar el DOM.
"""
import json
from playwright.sync_api import sync_playwright

USUARIO = "office"
PASSWORD = "Office123"
EMPRESA = "SincoPlus Pruebas Módulos"
URL_BASE = "https://www4.sincoerp.com/SincoPlusPruebasModulos2022/V3/Marco/Seleccion_iv.aspx"

with sync_playwright() as p:
    navegador = p.chromium.launch(headless=False)
    contexto = navegador.new_context(ignore_https_errors=True)
    pagina = contexto.new_page()

    print("Abriendo SINCO...")
    pagina.goto(URL_BASE)
    pagina.wait_for_load_state("networkidle")

    print("Ingresando credenciales...")
    pagina.locator("input:visible").nth(0).click()
    pagina.keyboard.type(USUARIO)
    pagina.locator("input:visible").nth(1).click()
    pagina.keyboard.type(PASSWORD)

    pagina.locator("button:visible").nth(0).click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(5000)

    pagina.locator("#ddlEmpresa").select_option(label=EMPRESA)
    pagina.wait_for_timeout(3000)

    boton = pagina.locator(
        "button:has-text('Ingresar'), input[value='Ingresar'], "
        "a:has-text('Ingresar'), :text('Ingresar')"
    ).first
    boton.wait_for(state="visible", timeout=10000)
    boton.click()
    pagina.wait_for_load_state("networkidle")
    pagina.wait_for_timeout(5000)

    print("\n" + "=" * 60)
    print("LOGIN EXITOSO")
    print("=" * 60)
    print("\nAhora NAVEGA en el navegador al modulo con DataGridPro")
    print("(ej: ADPRO > Almacen > Pedidos > Pedidos proyecto)")
    print("\nCuando estes en la pagina, presiona ENTER aqui...")
    input()

    pagina.wait_for_timeout(3000)
    pagina.screenshot(path="reportes/captura_pagina.png")

    # Buscar el frame
    frames = pagina.frames
    frame_obj = None
    for f in frames:
        if f != pagina.main_frame:
            frame_obj = f
            break

    if not frame_obj:
        print("No se encontro iframe. Capturando DOM de la pagina principal...")
        frame_obj = pagina.main_frame

    print(f"\nAnalizando frame: {frame_obj.url[:80]}...")

    # Extraer TODA la estructura
    resultado = frame_obj.evaluate("""() => {
        const todos = document.querySelectorAll('*');

        // 1. Todos los roles ARIA
        const roles = {};
        for (const el of todos) {
            const role = el.getAttribute('role');
            if (role) roles[role] = (roles[role] || 0) + 1;
        }

        // 2. Clases MUI relevantes
        const muiClasses = {};
        for (const el of todos) {
            for (const cls of el.classList) {
                if (cls.startsWith('MuiDataGrid') || cls.startsWith('MuiTable') || cls.startsWith('MuiBox')) {
                    muiClasses[cls] = (muiClasses[cls] || 0) + 1;
                }
            }
        }

        // 3. Elementos con data-* attributes
        const dataElements = [];
        for (const el of todos) {
            if (el.getAttribute('data-field') || el.getAttribute('data-id') ||
                el.getAttribute('data-rowindex') || el.getAttribute('aria-colindex') ||
                el.getAttribute('aria-rowindex')) {
                dataElements.push({
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute('role'),
                    dataField: el.getAttribute('data-field'),
                    dataId: el.getAttribute('data-id'),
                    dataRowindex: el.getAttribute('data-rowindex'),
                    ariaColindex: el.getAttribute('aria-colindex'),
                    ariaRowindex: el.getAttribute('aria-rowindex'),
                    text: (el.textContent || '').trim().substring(0, 50),
                    classes: [...el.classList].filter(c => c.startsWith('Mui') || c.startsWith('css-')).join(', '),
                });
            }
        }

        // 4. Tablas HTML
        const tablas = [];
        for (const tabla of document.querySelectorAll('table')) {
            const headers = [...tabla.querySelectorAll('th')].map(th => ({
                texto: (th.textContent || '').trim().substring(0, 30),
                classes: [...th.classList].join(', '),
            }));
            const filas = tabla.querySelectorAll('tbody tr');
            const primera_fila_celdas = filas.length > 0 ? [...filas[0].querySelectorAll('td')].map(td => ({
                texto: (td.textContent || '').trim().substring(0, 30),
                classes: [...td.classList].join(', '),
                role: td.getAttribute('role'),
            })) : [];
            tablas.push({
                clases: [...tabla.classList].join(', '),
                num_filas: filas.length,
                headers: headers,
                primera_fila: primera_fila_celdas,
            });
        }

        // 5. Elementos interactivos con info completa
        const interactivos = [];
        for (const el of document.querySelectorAll('input, button, select, textarea, [role="button"], [role="textbox"], [role="combobox"], [role="gridcell"], [role="row"], [role="grid"]')) {
            const clases = [...el.classList];
            interactivos.push({
                tag: el.tagName.toLowerCase(),
                id: el.id || null,
                role: el.getAttribute('role'),
                ariaLabel: el.getAttribute('aria-label'),
                ariaColindex: el.getAttribute('aria-colindex'),
                ariaRowindex: el.getAttribute('aria-rowindex'),
                placeholder: el.getAttribute('placeholder'),
                dataField: el.getAttribute('data-field'),
                dataTestId: el.getAttribute('data-testid'),
                type: el.getAttribute('type'),
                text: (el.textContent || '').trim().substring(0, 50),
                tieneIdReact: /(_r_\\d+_|:r[0-9a-f]+:)/.test(el.id || ''),
                tieneMui: clases.some(c => c.startsWith('Mui')),
                clasesRelevantes: clases.filter(c => c.startsWith('Mui')).join(', '),
            });
        }

        // 6. Estructura HTML simplificada (arbol del grid)
        const gridContainer = document.querySelector('.MuiDataGrid-root, .MuiTableContainer-root, [role="grid"], table');
        let arbolHTML = '';
        if (gridContainer) {
            function dumpTree(el, depth) {
                if (depth > 4) return;
                const indent = '  '.repeat(depth);
                const role = el.getAttribute('role') ? ` role="${el.getAttribute('role')}"` : '';
                const dataField = el.getAttribute('data-field') ? ` data-field="${el.getAttribute('data-field')}"` : '';
                const id = el.id ? ` id="${el.id}"` : '';
                const muiCls = [...el.classList].filter(c => c.startsWith('Mui')).join('.');
                const cls = muiCls ? ` class="${muiCls}"` : '';
                arbolHTML += indent + `<${el.tagName.toLowerCase()}${id}${role}${dataField}${cls}>\\n`;
                for (const child of el.children) {
                    dumpTree(child, depth + 1);
                }
            }
            dumpTree(gridContainer, 0);
        }

        return { roles, muiClasses, dataElements, tablas, interactivos, arbolHTML };
    }""")

    print("\n" + "=" * 60)
    print("RESULTADOS DE INSPECCION")
    print("=" * 60)

    print(f"\n1. ROLES ARIA ({len(resultado['roles'])}):")
    if resultado["roles"]:
        for role, count in sorted(resultado["roles"].items()):
            print(f"   role=\"{role}\": {count}")
    else:
        print("   NINGUNO (la pagina no tiene roles ARIA)")

    print(f"\n2. CLASES MUI ({len(resultado['muiClasses'])}):")
    for cls, count in sorted(resultado["muiClasses"].items()):
        print(f"   {cls}: {count}")

    print(f"\n3. ELEMENTOS CON data-* ATTRIBUTES ({len(resultado['dataElements'])}):")
    for d in resultado["dataElements"][:20]:
        print(f"   <{d['tag']}> role={d['role']} field={d['dataField']} id={d['dataId']} row={d['dataRowindex']} texto=\"{d['text'][:25]}\"")

    print(f"\n4. TABLAS HTML ({len(resultado['tablas'])}):")
    for i, t in enumerate(resultado["tablas"]):
        print(f"   Tabla #{i+1}: clases=\"{t['clases'][:60]}\" filas={t['num_filas']}")
        if t["headers"]:
            print(f"   Headers: {' | '.join(h['texto'] for h in t['headers'])}")
        if t["primera_fila"]:
            print(f"   Fila 1:  {' | '.join(c['texto'][:15] for c in t['primera_fila'])}")

    print(f"\n5. ELEMENTOS INTERACTIVOS ({len(resultado['interactivos'])}):")
    for e in resultado["interactivos"][:20]:
        extras = []
        if e["role"]:
            extras.append(f'role="{e["role"]}"')
        if e["ariaLabel"]:
            extras.append(f'label="{e["ariaLabel"]}"')
        if e["placeholder"]:
            extras.append(f'ph="{e["placeholder"]}"')
        if e["dataField"]:
            extras.append(f'field="{e["dataField"]}"')
        if e["tieneIdReact"]:
            extras.append(f'ID_REACT="{e["id"]}"')
        if e["clasesRelevantes"]:
            extras.append(f'mui="{e["clasesRelevantes"][:40]}"')
        ext = " ".join(extras)
        print(f"   <{e['tag']}> {ext} texto=\"{e['text'][:25]}\"")

    if resultado["arbolHTML"]:
        print(f"\n6. ARBOL HTML DEL GRID (primeros niveles):")
        for line in resultado["arbolHTML"].split("\n")[:30]:
            print(f"   {line}")

    # Guardar JSON completo
    with open("reportes/dom_captura.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    print(f"\nReporte completo guardado en: reportes/dom_captura.json")

    print("\n" + "=" * 60)
    print("Quieres inspeccionar OTRA pagina? Navega y presiona ENTER")
    print("O cierra el navegador para terminar.")
    print("=" * 60)

    try:
        input()
        # Segunda captura
        pagina.wait_for_timeout(2000)
        pagina.screenshot(path="reportes/captura_pagina2.png")
        frame_obj2 = None
        for f in pagina.frames:
            if f != pagina.main_frame:
                frame_obj2 = f
                break
        if frame_obj2:
            resultado2 = frame_obj2.evaluate("""() => {
                const todos = document.querySelectorAll('*');
                const roles = {};
                for (const el of todos) {
                    const role = el.getAttribute('role');
                    if (role) roles[role] = (roles[role] || 0) + 1;
                }
                const muiClasses = {};
                for (const el of todos) {
                    for (const cls of el.classList) {
                        if (cls.startsWith('MuiDataGrid') || cls.startsWith('MuiTable') || cls.startsWith('MuiBox')) {
                            muiClasses[cls] = (muiClasses[cls] || 0) + 1;
                        }
                    }
                }
                const interactivos = [];
                for (const el of document.querySelectorAll('input, button, select, [role]')) {
                    interactivos.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || null,
                        role: el.getAttribute('role'),
                        text: (el.textContent || '').trim().substring(0, 50),
                        clasesRelevantes: [...el.classList].filter(c => c.startsWith('Mui')).join(', '),
                    });
                }
                return { roles, muiClasses, interactivos };
            }""")
            print(f"\nPAGINA 2 - ROLES: {resultado2['roles']}")
            print(f"CLASES MUI: {resultado2['muiClasses']}")
            for e in resultado2["interactivos"][:15]:
                print(f"  <{e['tag']}> role={e['role']} mui={e['clasesRelevantes'][:30]} texto=\"{e['text'][:25]}\"")
    except Exception:
        pass

    navegador.close()
