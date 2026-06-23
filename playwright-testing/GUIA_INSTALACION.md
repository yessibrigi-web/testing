# Guia de instalacion - Pruebas automatizadas SINCO ERP

Este proyecto ejecuta pruebas automatizadas sobre SINCO ERP desde una pagina web.
Solo necesitas hacer click en un boton y ver los resultados en pantalla.

---

## Paso 1: Instalar Python

Descarga Python desde:

https://www.python.org/downloads/

**MUY IMPORTANTE:** Durante la instalacion, marca la casilla **"Add Python to PATH"**.

Para verificar que quedo instalado, abre una terminal y escribe:

```bash
python3 --version
```

Debe aparecer algo como `Python 3.x.x`.

### Como abrir una terminal

- **Mac**: Presiona `Cmd + Espacio`, escribe `Terminal` y presiona Enter
- **Windows**: Presiona la tecla Windows, escribe `cmd` y presiona Enter

---

## Paso 2: Descargar el proyecto

Abre una terminal y escribe estos comandos uno por uno:

```bash
git clone https://github.com/diafara2003/playwright-testing.git
```

```bash
cd playwright-testing
```

> Si no tienes `git` instalado, puedes descargar el proyecto como ZIP desde GitHub:
> Ve a https://github.com/diafara2003/playwright-testing, haz click en el boton verde **"Code"** y luego en **"Download ZIP"**. Descomprime la carpeta y abre una terminal dentro de ella.

---

## Paso 3: Instalar dependencias

Escribe este comando en la terminal y presiona Enter:

```bash
pip3 install -r requirements.txt
```

> **En Windows**, si `pip3` no funciona, intenta con `pip`:
> ```bash
> pip install -r requirements.txt
> ```

---

## Paso 4: Instalar el navegador

Escribe este comando y presiona Enter:

```bash
python3 -m playwright install chromium
```

> **En Windows**, si `python3` no funciona, intenta con `python`:
> ```bash
> python -m playwright install chromium
> ```

Esto descarga el navegador que usa el programa. Puede tardar unos minutos.

---

## Paso 5: Iniciar el servidor

Escribe este comando:

```bash
python3 server.py
```

> **En Windows**:
> ```bash
> python server.py
> ```

Debe aparecer el mensaje:

```
Servidor iniciado en http://localhost:5050
```

**No cierres esta terminal.** Debe quedar abierta mientras usas el programa.

---

## Paso 6: Abrir el panel de pruebas

Abre cualquier navegador (Chrome, Edge, Firefox) y escribe en la barra de direcciones:

```
http://localhost:5050
```

Veras el **Panel de Pruebas Automatizadas**.

---

## Como usar el panel

1. **Configura los datos** en la seccion superior:
   - **Usuario**: Tu usuario de SINCO
   - **Contrasena**: Tu contrasena de SINCO
   - **Empresa**: El nombre exacto de la empresa (como aparece en SINCO)
   - **URL**: La direccion de tu SINCO ERP

2. **Haz click en "Ejecutar pruebas"**

3. **Observa el progreso**:
   - Veras una barra de progreso avanzando
   - Cada paso muestra una captura de pantalla de lo que esta haciendo
   - Puedes hacer click en las capturas para verlas en grande
   - Puedes ocultar/mostrar las capturas con el boton "Ocultar capturas"

4. **Revisa los resultados**:
   - **OK (verde)**: La prueba paso correctamente
   - **X (rojo)**: La prueba fallo

---

## Para detener el servidor

Ve a la terminal donde ejecutaste `python3 server.py` y presiona `Ctrl + C`.

---

## Para volver a usarlo otro dia

1. Abre una terminal
2. Ve a la carpeta del proyecto:
   ```bash
   cd playwright-testing
   ```
3. Inicia el servidor:
   ```bash
   python3 server.py
   ```
4. Abre `http://localhost:5050` en el navegador

---

## Problemas frecuentes

| Problema | Solucion |
|----------|----------|
| `command not found: python3` | Instala Python (Paso 1) o usa `python` en vez de `python3` |
| `command not found: pip3` | Usa `pip` en vez de `pip3` o `python -m pip` |
| El navegador no carga `localhost:5050` | Verifica que la terminal con el servidor siga abierta |
| `Address already in use` | Otro programa usa el puerto. Cierra la terminal anterior y vuelve a intentar |
| Error al ejecutar la prueba | Verifica que los datos de configuracion (usuario, contrasena, empresa, URL) sean correctos |
