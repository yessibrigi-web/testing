# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Automated test runner for **SINCO ERP** using Playwright + Flask. A web dashboard (`dashboard.html`) at `http://localhost:5000` lets a user pick Cliente → Entorno → Base de datos, then runs a Python test from `pruebas/` against the live ERP, streaming progress + screenshots back via Server-Sent Events.

Working language is Spanish — variable names, docstrings, UI strings, prints. Match that style when editing.

## Run it

```bash
python server.py                              # starts Flask on :5000 (also iniciar.bat on Windows)
python -m playwright install chromium         # one-time, also installs deps
pip install flask playwright requests requests-ntlm
```

There is **no test runner** (no `pytest`, no CLI). Tests are executed through the dashboard `/ejecutar` endpoint, or by importing `pruebas.<id>.ejecutar(pagina, frame)` from a Playwright session you build yourself. The `playwright-testing/` subfolder is an older pytest-based prototype and is not used by `server.py`.

## Authoring a test

Every test in `pruebas/` is a single module exporting:

```python
"""
Prueba: Human-readable name        # parsed from docstring → shown in UI
Módulo: Category                   # parsed from docstring → groups in UI
"""
def ejecutar(pagina, frame, on_paso=None, parametros=None):
    if on_paso: on_paso("step label")   # sent to dashboard as progress
    ...
    return {
        "prueba": "...",
        "estado": "ok" | "fail",
        "dato_entrada": "...",
        "esperado": "...",
        "obtenido": "...",
    }
```

- `pagina` is a Playwright `Page` already logged into the ERP (SINCO Default_iv.aspx). **Do not build your own browser, login, or call `sync_playwright()` inside a test** — `server.py` owns the lifecycle. Several files in `pruebas/` (e.g. `Logue_torre.py`, `Entrar.py`, `Generacin_Control.py`) are raw codegen output that violate this and will not run from the dashboard; treat them as drafts to be cleaned up, not as templates.
- `frame` is passed as `None`; if your flow uses an iframe, do `frame = pagina.locator("#pagina1").content_frame` yourself.
- `parametros` arrives as a dict from the dashboard's parameter input. The dispatcher in `server.py` (`_ejecutar_prueba`) introspects the signature and only passes `parametros` if the function declares it — keeps old tests compatible.
- Files starting with `_` are skipped by `descubrir_pruebas()`.

Composed flows (e.g. `FlujoCompleto_Addon.py`) `importlib.import_module` other test modules and call their `ejecutar` directly — fine as long as they `sys.path.insert(0, os.path.dirname(__file__))` first.

## The login is the hard part

`LOGICA_CONEXION_TORRE.md` is the authoritative reference — read it before changing anything in `SincoAPI` or the login flow. The short version:

1. **Dashboard data load** (`SincoAPI.conectar_y_cargar`): one-time Playwright headless login to `Torre.html` to capture cookies + `tokenAuth`, then pure HTTP SignalR (`/API/signalr/...`) to fetch clientes + entornos. Cached in memory; `/torre/reset` flushes.
2. **Test execution login** (`_ejecutar_prueba`): runs in **one** Chrome instance (`channel="chrome"`, not chromium — needed for Windows NTLM against `*.sincoerp.com`). Headless does NOT work because the ERP servers require NTLM at the transport layer. The flow is: open Torre → read `window.user_central_key` after login → build a `<form method=post>` to `Login.aspx` with `{keyC, ingreso=0, usuDominio, usuario}` → `expect_popup` → wait for `Seleccion_iv.aspx` → pick empresa via `#ddlEmpresa` (matched by label, since every option's `value` is `"1"`) → click Ingresar → land on `Default_iv.aspx`. The Torre tab is then closed and the popup is handed to the test as `pagina`.

The `seleccionar_empresa_dropdown` helper in `server.py` has a 5-tier fallback (exact → case-insensitive → strip `REPLICA_` prefix → substring → ≥60% word match). If you're tempted to "simplify" it, look at the option labels first — they're inconsistent across clients.

Credentials live in `CONFIG` at the top of `server.py` (currently `yessica.olaya` / `Jeronimo2026`). NTLM uses the same pair.

## Selector conventions (from DOCUMENTACION_PRUEBAS.md §8)

Use selectors in this priority — **never** CSS classes (`.MuiButton-root`, `.css-abc123`) or DOM position (`nth(3)`, `div > div > button`):

1. `data-testid` → `locator('[data-testid="..."]')`
2. `aria-label` → `locator('button[aria-label="..."]')`
3. role + name → `get_by_role("button", name="Guardar")`
4. `data-field` for DataGrid cells → `locator('[data-field="cantidad"]')`
5. `data-descripcion` for containers
6. Visible text → last resort

When pasting codegen output into a test, strip `CapsLock` press artifacts, replace fragile MUI classes with the above, and use `frame_locator("#pagina1")` (not `.content_frame()` chained on a locator) for iframe access. For the ERP main iframe, prefer `frame = pagina.locator("#pagina1").content_frame` (a property in this Playwright version).

## Project layout cheatsheet

- `server.py` — Flask app, `SincoAPI` class, login orchestration, test dispatcher, code editor endpoints. ~1400 lines, single file by design.
- `dashboard.html` — single-page UI (CodeMirror editor, SSE event stream, dropdowns hitting `/torre/*`). Self-contained, no build step.
- `pruebas/` — the test corpus. Each `.py` is one test.
- `playwright-testing/` — legacy pytest experiment, do not modify in tandem with `Testing/`.
- `reportes/` — historic JSON outputs from one-off inspection runs.
- `apis_capturadas.json`, `debug_torre_*`, `interceptar_apis.py`, `capturar_dom.py`, `debug_interceptar_form.py` — diagnostic tools used to reverse-engineer the Torre flow. Reference material, not part of the runtime.

## Things that have bitten this codebase

- Mixing `chromium` (Playwright bundled) with NTLM-protected ERP URLs → `chrome-error://chromewebdata/`. Always `channel="chrome"` for ERP login.
- Splitting login and test across two browser instances → NTLM cookies don't transfer cleanly. `_ejecutar_prueba` keeps everything in one browser for this reason.
- `#ddlEmpresa` option `value` is identical across rows; selecting by value is a bug, always select by **label**.
- `INSTRUCCIONES.TXT` references `grabar.py` — that file lives in the legacy `playwright-testing/` folder. In this project recording is exposed as the `/grabar` HTTP endpoint, which spawns Playwright Inspector via `page.pause()` after an authenticated login.
