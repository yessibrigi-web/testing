@echo off
setlocal EnableDelayedExpansion
title Instalador - Pruebas Automatizadas SINCO ERP
color 0A

echo ============================================================
echo   INSTALADOR - Pruebas Automatizadas SINCO ERP
echo   Sincosoft SAS
echo ============================================================
echo.

:: ─── 1. Verificar Python ─────────────────────────────────────
echo [1/5] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python no esta instalado o no esta en el PATH.
    echo.
    echo  Por favor instala Python desde:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANTE: Durante la instalacion marca la casilla
    echo    "Add Python to PATH"
    echo.
    echo  Luego vuelve a ejecutar este instalador.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  OK: %%v

:: ─── 2. Verificar pip ────────────────────────────────────────
echo.
echo [2/5] Verificando pip...
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: pip no encontrado. Intenta reinstalar Python.
    pause
    exit /b 1
)
echo  OK: pip encontrado.

:: ─── 3. Actualizar pip ───────────────────────────────────────
echo.
echo [3/5] Actualizando pip...
python -m pip install --upgrade pip --quiet
echo  OK: pip actualizado.

:: ─── 4. Instalar dependencias Python ─────────────────────────
echo.
echo [4/5] Instalando dependencias Python...
echo  (flask, playwright, requests, requests-ntlm)
echo.

python -m pip install flask playwright requests requests-ntlm
if errorlevel 1 (
    echo.
    echo  ERROR: Fallo la instalacion de dependencias.
    echo  Verifica tu conexion a internet e intentalo de nuevo.
    pause
    exit /b 1
)
echo.
echo  OK: Dependencias instaladas.

:: ─── 5. Instalar navegadores Playwright ──────────────────────
echo.
echo [5/5] Instalando navegadores de Playwright...
echo  (Esto puede tardar varios minutos la primera vez)
echo.

python -m playwright install chromium
if errorlevel 1 (
    echo.
    echo  ADVERTENCIA: No se pudo instalar Chromium.
    echo  Si tienes Google Chrome instalado, el sistema lo usara automaticamente.
)

:: Tambien instalar las dependencias del sistema si es posible
python -m playwright install-deps chromium >nul 2>&1

echo.
echo ============================================================
echo   INSTALACION COMPLETADA
echo ============================================================
echo.
echo  REQUISITO ADICIONAL:
echo  Este sistema requiere Google Chrome instalado para conectarse
echo  al ERP con autenticacion NTLM de Windows.
echo  Descargalo en: https://www.google.com/chrome/
echo.
echo  Para iniciar el sistema usa el archivo:
echo    iniciar.bat
echo.
echo  O ejecuta manualmente:
echo    python server.py
echo.
echo  Luego abre en tu navegador:
echo    http://localhost:5000
echo.
pause
