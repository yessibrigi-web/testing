# Documentación — Pruebas Automatizadas SINCO ERP con Playwright

> Guía completa: clonar el proyecto, crear pruebas y ejecutarlas.

---

## Índice

1. [Requisitos previos](#1-requisitos-previos)
2. [Clonar el proyecto](#2-clonar-el-proyecto)
3. [Instalar dependencias](#3-instalar-dependencias)
4. [Estructura del proyecto](#4-estructura-del-proyecto)
5. [Cómo funciona cada archivo](#5-cómo-funciona-cada-archivo)
6. [Grabar un nuevo test con Codegen](#6-grabar-un-nuevo-test-con-codegen)
7. [Convertir el código grabado a Python](#7-convertir-el-código-grabado-a-python)
8. [Reglas de selectores del proyecto](#8-reglas-de-selectores-del-proyecto)
9. [Ejecutar las pruebas](#9-ejecutar-las-pruebas)
10. [Leer los resultados](#10-leer-los-resultados)
11. [Errores frecuentes y soluciones](#11-errores-frecuentes-y-soluciones)

---

## 1. Requisitos previos

Antes de comenzar, verifica que tienes instalado:

| Herramienta | Cómo verificar | Dónde descargar |
|-------------|---------------|-----------------|
| Python 3.8+ | `python --version` | https://www.python.org/downloads |
| Git | `git --version` | https://git-scm.com |
| VS Code (recomendado) | — | https://code.visualstudio.com |

> **Importante en Windows:** Al instalar Python, marca la casilla **"Add Python to PATH"**.

---

## 2. Clonar el proyecto

Abre una terminal y ejecuta los siguientes comandos **uno por uno**:

```bash
git clone https://github.com/diafara2003/playwright-testing.git
```

```bash
cd playwright-testing
```

Si no tienes Git, descarga el ZIP desde GitHub:
- Ve al repositorio → botón verde **Code** → **Download ZIP**
- Descomprime la carpeta y ábrela en la terminal

---

## 3. Instalar dependencias

### 3.1 Instalar paquetes de Python

```bash
python -m pip install -r requirements.txt
```

Esto instala:
- `playwright` — librería principal de automatización
- `pytest` — framework para ejecutar las pruebas
- `pytest-playwright` — integración entre pytest y playwright

> Si `pip` no funciona usa `python -m pip`

### 3.2 Instalar el navegador

```bash
python -m playwright install chromium
```

Descarga el navegador Chromium que Playwright usará para ejecutar los tests.
Puede tardar unos minutos la primera vez.

### 3.3 Verificar que todo quedó instalado

```bash
python -m pytest --version
python -m playwright --version
```

Debes ver algo como:
```
pytest 7.x.x
Version 1.52.0
```

---

## 4. Estructura del proyecto

```
playwright-testing/
│
├── tests/                        ← Carpeta con todos los tests
│   ├── conftest.py               ← Login compartido para todos los tests
│   └── test_Crear_Pedido.py      ← Test del flujo "Crear Pedido"
│
├── requirements.txt              ← Dependencias del proyecto
├── DOCUMENTACION_PRUEBAS.md      ← Este archivo
└── GUIA_INSTALACION.md           ← Guía de instalación general
```

> Cada nuevo test que crees debe guardarse dentro de la carpeta `tests/`
> y su nombre debe comenzar con `test_` para que pytest lo detecte.

---

## 5. Cómo funciona cada archivo

### `tests/conftest.py` — Login compartido

Este archivo ejecuta el proceso de login **una sola vez** y lo comparte con
todos los tests. Así no tienes que repetir el código de login en cada archivo.

```python
# tests/conftest.py
import pytest
from playwright.sync_api import Page

@pytest.fixture
def login(page: Page):
    # Paso 1: ingresar credenciales
    page.goto("https://desarrollo.sincoerp.com/SincoOk/V3/Marco/Login_iv.aspx")
    page.get_by_role("textbox", name="Usuario").fill("Admin")
    page.get_by_role("textbox", name="Contraseña").fill("Admin123")
    page.get_by_role("button", name="Iniciar sesión").click()

    # Paso 2: selección de empresa/sucursal (pantalla intermedia de SINCO)
    page.wait_for_url("**/Seleccion_iv.aspx")
    page.get_by_role("button", name="Ingresar").click()
    page.wait_for_url("**/Default_iv.aspx")
```

**Para usar el login en un test**, simplemente agrega `login` como parámetro:

```python
def test_mi_flujo(page: Page, login):
    # El login ya ocurrió automáticamente
    # Aquí escribes tu flujo
```

---

### `tests/test_Crear_Pedido.py` — Ejemplo de test completo

Estructura de un test en Python con Playwright:

```python
from playwright.sync_api import Page, expect

def test_nombre_descriptivo(page: Page, login):
    # 1. Navegar al módulo
    # 2. Realizar acciones
    # 3. Validar con expect()
```

---

## 6. Grabar un nuevo test con Codegen

**Codegen** es el grabador visual de Playwright. Abre el navegador, registra
todo lo que haces y genera el código automáticamente.

### Paso 1 — Ejecutar Codegen

```bash
python -m playwright codegen https://desarrollo.sincoerp.com/SincoOk/V3/Marco/Login_iv.aspx
```

Se abren **dos ventanas** simultáneamente:

| Ventana | Qué es |
|---------|--------|
| Navegador | Aquí navegas y realizas las acciones |
| Panel de código | Aquí aparece el código generado en tiempo real |

### Paso 2 — Realizar el flujo que quieres probar

1. Inicia sesión con tus credenciales
2. Navega al módulo que quieres probar
3. Realiza todas las acciones: clics, formularios, búsquedas, etc.
4. Codegen va generando el código a medida que actúas

### Paso 3 — Copiar el código generado

Cuando termines el flujo:
1. En el panel de código, selecciona todo (`Ctrl + A`)
2. Copia el código (`Ctrl + C`)
3. Cierra las dos ventanas

> **Nota:** Codegen genera código en **Python** si seleccionas el lenguaje
> correcto en el panel. Asegúrate de que diga `Python` en el selector
> de lenguaje del panel de código.

---

## 7. Convertir el código grabado a Python

### Paso 1 — Crear el archivo de test

Crea un nuevo archivo dentro de la carpeta `tests/`:

```
tests/test_NombreDelFlujo.py
```

> El nombre debe comenzar con `test_` y usar guiones bajos, sin espacios.

### Paso 2 — Estructura base del archivo

Pega este bloque al inicio del archivo y agrega el código de Codegen dentro:

```python
from playwright.sync_api import Page, expect


def test_nombre_del_flujo(page: Page, login):
    """Descripción corta de qué prueba este test."""

    # Aquí va el código grabado por Codegen
    # (después de quitar el login, que ya lo maneja conftest.py)
```

### Paso 3 — Limpiar el código de Codegen

El código grabado por Codegen tiene problemas comunes que **debes corregir**:

#### ❌ Problema 1: Artefactos de CapsLock

Codegen graba cada tecla que presionas. Si tenías Bloq Mayús activo genera:

```python
# ❌ Código generado (incorrecto)
page.get_by_role("textbox", name="Usuario").press("CapsLock")
page.get_by_role("textbox", name="Usuario").fill("A")
page.get_by_role("textbox", name="Usuario").press("CapsLock")
page.get_by_role("textbox", name="Usuario").fill("Admin")
```

```python
# ✅ Código correcto
page.get_by_role("textbox", name="Usuario").fill("Admin")
```

#### ❌ Problema 2: Selectores frágiles

Codegen a veces graba clases CSS dinámicas que cambian con cada versión:

```python
# ❌ Frágil — cambia con cada build
page.locator(".MuiBox-root.css-1umnpr4").click()
page.locator('[id="_r_87_"]').fill("10.5")
page.locator(".css-1tdeh38").click()
```

```python
# ✅ Estable — usa data-field y keyboard
fila.locator('[data-field="cantidad"]').click()
page.keyboard.type("10.5")
page.keyboard.press("Tab")
```

#### ❌ Problema 3: setInputFiles en un botón

```python
# ❌ Incorrecto — setInputFiles no aplica sobre botones
page.get_by_role("button", name="Adjuntar").set_input_files("archivo.png")
```

```python
# ✅ Correcto — setInputFiles va sobre el input[type="file"]
page.frame_locator("#pagina1").locator(
    '[data-testid="drop-zone"] input[type="file"]'
).set_input_files("archivo.png")
```

#### ❌ Problema 4: Acceder al iframe

```python
# ❌ Incorrecto — no es la forma Python
page.locator("#pagina1").content_frame().get_by_role(...)
```

```python
# ✅ Correcto en Python
frame = page.frame_locator("#pagina1")
frame.get_by_role("button", name="Nuevo pedido").click()
```

### Paso 4 — Agregar validaciones (expect)

Después de cada acción importante agrega una validación:

```python
# Después de navegar
expect(frame.get_by_role("button", name="Nuevo pedido")).to_be_visible()

# Después de escribir en un campo
expect(page.get_by_role("textbox", name="Usuario")).to_have_value("Admin")

# Después de un guardado
expect(modal.locator('span:has-text("Sin guardar")')).not_to_be_visible()

# Después de una acción que cierra un elemento
expect(modal).not_to_be_visible()

# Para verificar texto en una celda
expect(fila.locator('[data-field="cantidad"]')).to_contain_text("10.5")

# Para esperar que un botón esté activo antes de hacer clic
expect(btn).to_be_enabled(timeout=10000)
btn.click()
```

---

## 8. Reglas de selectores del proyecto

Usa los selectores en este orden de prioridad:

| Prioridad | Selector | Ejemplo | Cuándo |
|-----------|----------|---------|--------|
| 1 | `data-testid` | `locator('[data-testid="attachments-modal"]')` | Siempre que exista |
| 2 | `aria-label` | `locator('button[aria-label="Imprimir"]')` | Botones de ícono |
| 3 | `role` + nombre | `get_by_role("button", name="Guardar")` | Botones con texto |
| 4 | `data-field` | `locator('[data-field="cantidad"]')` | Celdas de DataGrid |
| 5 | `data-descripcion` | `locator('[data-descripcion="Contenedor tabla pedidos"]')` | Contenedores |
| 6 | Texto visible | `get_by_text("Eliminar pedido")` | Último recurso |

### Selectores que NUNCA debes usar

```python
# ❌ Clase CSS dinámica
locator(".MuiButton-root")
locator(".css-abc123")

# ❌ Posición en el DOM
locator("button").nth(3)

# ❌ Cadena de divs
locator("div > div > button")
```

---

## 9. Ejecutar las pruebas

### Ejecutar todos los tests

```bash
python -m pytest tests/
```

### Ejecutar un test específico

```bash
python -m pytest tests/test_Crear_Pedido.py
```

### Ejecutar con el navegador visible (modo headed)

```bash
python -m pytest tests/test_Crear_Pedido.py --headed
```

### Ejecutar con reporte detallado

```bash
python -m pytest tests/ -v
```

### Ejecutar en modo lento para ver cada paso

```bash
python -m pytest tests/test_Crear_Pedido.py --headed --slowmo=1000
```

> `--slowmo=1000` agrega una pausa de 1 segundo entre cada acción.
> Útil para observar qué está haciendo el test.

---

## 10. Leer los resultados

### Test exitoso

```
tests/test_Crear_Pedido.py::test_crear_pedido PASSED    [100%]

1 passed in 45.32s
```

### Test fallido

```
tests/test_Crear_Pedido.py::test_crear_pedido FAILED    [100%]

FAILED tests/test_Crear_Pedido.py::test_crear_pedido
Error: expect(locator).to_be_visible() failed
Locator: frame_locator("#pagina1").get_by_role("button", name="Guardar")
Expected: visible
```

Cuando un test falla, Playwright genera en `test-results/`:
- `test-failed-1.png` — captura de pantalla del momento exacto del error
- `error-context.md` — descripción del error con el estado de la página

---

## 11. Errores frecuentes y soluciones

| Error | Causa | Solución |
|-------|-------|----------|
| `ModuleNotFoundError: playwright` | No instalado | `python -m pip install -r requirements.txt` |
| `Browser not found` | Navegador no descargado | `python -m playwright install chromium` |
| `TimeoutError: locator not found` | Selector incorrecto o tiempo agotado | Revisar el selector y aumentar timeout |
| `expect().to_be_enabled() failed` | Botón deshabilitado | Esperar a que la carga termine antes del clic |
| `Error: element(s) not found` | El nombre del elemento no coincide | Usar `--headed` para ver qué muestra la pantalla |
| Código TypeScript en archivo Python | Se pegó el código equivocado | Seguir la sección 7 de esta guía |

---

## Flujo de trabajo resumido

```
1. Clonar repositorio
   git clone https://github.com/diafara2003/playwright-testing.git

2. Instalar dependencias
   python -m pip install -r requirements.txt
   python -m playwright install chromium

3. Grabar el flujo con Codegen
   python -m playwright codegen <URL>

4. Crear el archivo de test
   tests/test_NuevoFlujo.py

5. Pegar y limpiar el código grabado
   - Quitar login (lo maneja conftest.py)
   - Reemplazar selectores frágiles
   - Agregar validaciones con expect()

6. Ejecutar y verificar
   python -m pytest tests/test_NuevoFlujo.py --headed -v
```

---

*Proyecto: ADPRO Almacén — Pedidos por Actividad*
*Framework: Python + Playwright + pytest*
