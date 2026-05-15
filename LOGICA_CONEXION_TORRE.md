# Lógica de Conexión Torre → ERP SINCO

Documento técnico que describe el flujo completo de autenticación desde Torre.html hasta la apertura de un entorno ERP, incluyendo tiempos medidos y la estrategia de optimización.

---

## Resumen Ejecutivo

Torre.html es la puerta de entrada a los entornos SINCO ERP. El flujo completo toma **~42 segundos** vía navegador (Playwright). El análisis reveló que todo se reduce a **3 llamadas HTTP** que pueden ejecutarse en **~3-5 segundos**.

---

## PARTE 1: Carga de Entornos (Dashboard)

### Flujo actual (ya optimizado con SignalR HTTP)

El dashboard ya usa HTTP puro para cargar clientes, entornos y bases de datos. No requiere navegador.

#### Paso 1 — Login a Torre API (~3s total con Playwright, ~1s con HTTP)

**Endpoint:** `POST https://core.sincoerp.com/Sincosoporte/API/Trabajadores/Validar`

**Request:**
```json
{
  "usuario": "yessica.olaya",
  "password": "<password encriptado con CryptoJS AES>"
}
```

**Encriptación del password:**
- Torre usa `CryptoJS` (disponible globalmente en Torre.html)
- El password se encripta del lado del cliente antes de enviarse
- Ejemplo de password encriptado:
  ```
  NNYRrHxodOZL+rTuagySNsVa6fbtJnPl66kO1NCCw/sPmkhP1dnPYybg84yuXDS7
  h6D6Vlbuto5gTNaJqHRDdhhzOwTk/FK7T9tlCg0I9gJLOGZedMepwTFpCyFbnxif
  b+Gzn/Sc+1gyDCc8cWVtfw==4
  ```
- **NOTA:** Actualmente se usa Playwright headless para ejecutar el JS de encriptación del cliente. El password encriptado se guarda en `localStorage.usuario` como JSON.

**Response (200 OK):**
```json
{
  "tokenAuth": "Bearer nzrTaflz52op8UUecal7vv...",
  "token": { "value": 9388 },
  "trabajador": {
    "Id": 270,
    "NombreCompleto": "ADPRO - Yessica Olaya",
    "UsuarioDominio": "sinco\\yessica.olaya",
    "UsuarioLogin": "admin",
    "EquipoTrabajo": "ADPRO",
    "EquipoTrabajo_Id": 105,
    "Correo": "yessica.olaya@sinco.com.co"
  }
}
```

**Datos extraídos:**
- `tokenAuth` → Bearer token para API
- `UsuarioDominio` → `sinco\yessica.olaya` (usado para SignalR y login ERP)
- `UsuarioLogin` → `admin` (usado para login ERP)
- `EquipoTrabajo` → `ADPRO` (usado para SignalR)
- `EquipoTrabajo_Id` → `105`

#### Paso 2 — Conectar SignalR

**Negotiate:** `GET /SincoSoporte/API/signalr/negotiate`
```
?clientProtocol=1.5
&UserName=sinco\yessica.olaya
&EquipoTrabajo=ADPRO
&AppEmpresa=sincosoporte
&connectionData=[{"name":"myhub"},{"name":"releasemanager"}]
```

**Response:** `{ "ConnectionToken": "RZmH5jmq...", "ConnectionId": "2477e7a8-..." }`

**Start:** `GET /SincoSoporte/API/signalr/start` (mismos params + connectionToken)

**Response:** `{ "Response": "started" }`

#### Paso 3 — Cargar Clientes

**SignalR Send:** `POST /SincoSoporte/API/signalr/send`
```json
{ "H": "clientes", "M": "GetClientes", "A": [], "I": 1 }
```
Retorna array completo de clientes con IdCliente, Cliente, Nit, Ciudad.

#### Paso 4 — Cargar Entornos

**SignalR Send:**
```json
{ "H": "entornos", "M": "GetEntornos", "A": [], "I": 2 }
```
Retorna array de entornos con Id, Nombre, URL, NombreCliente, BasesDatos[].

Cada entorno incluye sus bases de datos con Id, Catalogo, Nombre, Principal.

---

## PARTE 2: Login al Entorno ERP (el cuello de botella)

### Flujo actual vía Playwright (~42s)

| Paso | Acción | Duración |
|------|--------|----------|
| 1 | Cargar Torre.html | 3.5s |
| 2 | Llenar usuario/password + clic Login | 2.2s |
| 3 | Clic en Master | 1.1s |
| 4 | Buscar y seleccionar cliente | 5.3s |
| 5 | Seleccionar entorno | 3.7s |
| 6 | Clic en "Ingresar al entorno" | 26.8s |
| **Total** | | **~42s** |

### Lo que realmente hace Torre al hacer clic en "Ingresar"

Torre.js ejecuta estos pasos:

#### 1. Obtener Key de Login Centralizado

Antes de abrir el entorno, Torre llama por SignalR:
```json
{ "H": "myhub", "M": "obtenerKeyLoginCentralizado", "A": ["sinco\\yessica.olaya"], "I": 0 }
```

Esto retorna la lista de entornos con URLs, pero lo importante es que **genera y almacena una key en el servidor**. La key se almacena en la variable global `user_central_key`:

```
user_central_key = "CD3332D6CFA8A96D0AF9DF723EF18A2788814094X0"
```

#### 2. Crear Form Dinámico y POST a Login.aspx

Torre crea dinámicamente un `<form>` con `target="_blank"` y lo envía:

```html
<form method="post" action="https://kilauea-v01.sincoerp.com:444/SincoConsRizek/V3/Marco/Login.aspx" target="_blank">
  <input name="keyC"        value="CD3332D6CFA8A96D0AF9DF723EF18A2788814094X0">
  <input name="ingreso"     value="0">
  <input name="usuDominio"  value="sinco\yessica.olaya">
  <input name="usuario"     value="admin">
</form>
```

**Campos del formulario:**
| Campo | Valor | Origen |
|-------|-------|--------|
| `keyC` | Hash hexadecimal + "X0" | `obtenerKeyLoginCentralizado` → `user_central_key` |
| `ingreso` | `"0"` | Constante |
| `usuDominio` | `sinco\yessica.olaya` | `trabajador.UsuarioDominio` |
| `usuario` | `admin` | `trabajador.UsuarioLogin` |

#### 3. Saltos del Popup (autenticación exitosa)

Cuando el POST llega a Login.aspx con los datos correctos + NTLM válido:

```
Login.aspx (POST, 200) → Seleccion.aspx (GET, 200) → Seleccion_iv.aspx (GET, 200)
```

- **Login.aspx**: Recibe el form POST, valida `keyC` contra el servidor, establece sesión ASP.NET
- **Seleccion.aspx**: Página intermedia que redirige
- **Seleccion_iv.aspx**: Página final "Selección empresa y sucursal" con dropdown `#ddlEmpresa`

#### 4. APIs que llama Seleccion_iv.aspx

Una vez cargada, la página hace:
- `GET /V3/API/Cliente/1/Empresas` → Lista de empresas disponibles
- `GET /V3/API/Info/Noticias/Locales` → Noticias
- `GET /V3/API/Cliente/10/Empresa/1/Sucursales` → Sucursales de la empresa seleccionada

#### 5. Selección de Empresa + Ingresar

El usuario selecciona empresa en `#ddlEmpresa` y hace clic en "Ingresar":
```
Seleccion_iv.aspx → Default_iv.aspx (la aplicación ERP)
```

---

## PARTE 3: Problema con NTLM

### ¿Por qué falla headless?

El servidor ERP (`kilauea-v01.sincoerp.com:444`, `www2.sincoerp.com`, etc.) requiere **autenticación NTLM** a nivel HTTP. Esto es independiente de los datos del form — es la capa de transporte.

- **Chromium de Playwright** (headless o no): No tiene acceso al almacén de credenciales de Windows → `chrome-error://chromewebdata/`
- **Chrome del sistema** (`channel="chrome"`): Sí tiene acceso a NTLM → funciona, pero requiere navegador visible
- **HTTP con `requests`**: Necesita `requests_ntlm` con credenciales explícitas

### Credenciales NTLM

Las credenciales NTLM son las mismas del dominio:
- **Dominio\Usuario:** `sinco\yessica.olaya`
- **Password:** `Jeronimo2026` (el mismo de Torre)

---

## PARTE 4: Estrategia de Optimización

### Flujo propuesto (100% HTTP, ~3-5s)

```
┌─────────────────────────────────────────────────────────┐
│ PASO 1: Login Torre API (ya existe en SincoAPI)         │
│ POST /API/Trabajadores/Validar                          │
│ → tokenAuth, UsuarioDominio, UsuarioLogin               │
│ Duración: ~1s                                           │
├─────────────────────────────────────────────────────────┤
│ PASO 2: SignalR obtenerKeyLoginCentralizado              │
│ POST /API/signalr/send                                  │
│ → user_central_key                                      │
│ Duración: ~0.5s                                         │
├─────────────────────────────────────────────────────────┤
│ PASO 3: POST a Login.aspx con NTLM                     │
│ POST https://<servidor>/V3/Marco/Login.aspx             │
│ Body: keyC + ingreso + usuDominio + usuario             │
│ Auth: NTLM (sinco\yessica.olaya / Jeronimo2026)        │
│ → Sigue redirects → llega a Seleccion_iv.aspx           │
│ → Captura cookies de sesión ASP.NET                     │
│ Duración: ~1-2s                                         │
├─────────────────────────────────────────────────────────┤
│ PASO 4: Seleccionar empresa via POST                    │
│ POST Seleccion_iv.aspx (form submit con empresa)        │
│ → Redirige a Default_iv.aspx                            │
│ → Captura URL final + cookies                           │
│ Duración: ~1s                                           │
├─────────────────────────────────────────────────────────┤
│ PASO 5: Abrir navegador con cookies inyectadas          │
│ Playwright browser.new_context(storage_state=cookies)   │
│ page.goto(Default_iv.aspx)                              │
│ → ERP listo para pruebas                                │
│ Duración: ~1s                                           │
└─────────────────────────────────────────────────────────┘
TOTAL ESTIMADO: ~3-5 segundos (vs ~42s actual)
```

### Dependencias necesarias

```bash
pip install requests-ntlm
```

### Datos disponibles desde SincoAPI (ya cargados)

Al momento de ejecutar una prueba, el dashboard ya tiene:
- `trabajador.UsuarioDominio` = `sinco\yessica.olaya`
- `trabajador.UsuarioLogin` = `admin`
- `entorno.URL` = `https://kilauea-v01.sincoerp.com:444/SincoConsRizek/V3/Marco/Login.aspx`
- Credenciales NTLM = mismo user/pass de Torre

### Lo que falta implementar

1. **Llamar `obtenerKeyLoginCentralizado`** vía SignalR HTTP para obtener `user_central_key`
2. **POST a Login.aspx** con NTLM + form data (keyC, ingreso, usuDominio, usuario)
3. **Seguir redirects** hasta Seleccion_iv.aspx, capturar cookies
4. **POST a Seleccion_iv.aspx** para seleccionar empresa
5. **Inyectar cookies** en Playwright context

---

## PARTE 5: Referencia de APIs

### Torre (core.sincoerp.com/SincoSoporte)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/API/Trabajadores/Validar` | Login (password AES) → tokenAuth |
| GET | `/API/signalr/negotiate` | Iniciar SignalR |
| GET | `/API/signalr/start` | Activar conexión |
| POST | `/API/signalr/send` | Llamar métodos SignalR |

### SignalR Hubs y Métodos

| Hub | Método | Params | Retorna |
|-----|--------|--------|---------|
| `clientes` | `GetClientes` | [] | Array de clientes |
| `entornos` | `GetEntornos` | [] | Array de entornos con BD |
| `myhub` | `obtenerKeyLoginCentralizado` | [usuDominio] | Array de entornos + genera key |
| `myhub` | `accesosEntornos` | [usuario] | Array de entornos accesibles |
| `myhub` | `misLinks` | [trabajadorId] | Links del trabajador |
| `administrativo` | `GetEmpId` | [empresaId] | Datos empresa |

### ERP (servidor del entorno)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/V3/Marco/Login.aspx` | Recibe form (keyC, ingreso, usuDominio, usuario) |
| GET | `/V3/Marco/Seleccion.aspx` | Redirect intermedio |
| GET | `/V3/Marco/Seleccion_iv.aspx` | Selección de empresa |
| GET | `/V3/API/Cliente/{id}/Empresas` | Lista empresas |
| GET | `/V3/API/Cliente/{id}/Empresa/{empId}/Sucursales` | Sucursales |
| POST | `/V3/Marco/Seleccion_iv.aspx` | Submit empresa → Default_iv |
| GET | `/V3/Marco/Default_iv.aspx` | Aplicación ERP |

---

## PARTE 6: Variables Globales de Torre.js

Variables relevantes disponibles en `window` después del login:

| Variable | Tipo | Contenido |
|----------|------|-----------|
| `trabajador` | Object | Datos completos del trabajador |
| `user_central_key` | String | Key para login centralizado |
| `accesos_LoginC` | Array | Entornos accesibles con URLs |
| `SesionCliente` | Object | Info de sesión |
| `Config` | Object | URLs de soporte y módulos |
| `tokenAuth` (localStorage) | String | Bearer token |
| `usuario` (localStorage) | JSON | usuario + password encriptado |

---

*Documento generado: 2026-05-08*
*Basado en diagnóstico completo del flujo Torre → ERP*
