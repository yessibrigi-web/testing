@echo off
title SINCO ERP - Dashboard de Pruebas
color 0B
cd /d "%~dp0"

echo ============================================================
echo   SINCO ERP - Dashboard de Pruebas Automatizadas
echo ============================================================
echo.

:: Verificar que Python este disponible
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python no encontrado.
    echo  Ejecuta primero el archivo "instalar.bat"
    echo.
    pause
    exit /b 1
)

:: Verificar que server.py exista en esta carpeta
if not exist "server.py" (
    echo  ERROR: No se encontro server.py en esta carpeta.
    echo  Asegurate de ejecutar este .bat desde la carpeta del proyecto.
    echo.
    pause
    exit /b 1
)

echo  Iniciando servidor...
echo  Una vez iniciado, abre tu navegador en:
echo    http://localhost:5000
echo.
echo  Para detener el servidor presiona Ctrl+C en esta ventana.
echo.
echo ============================================================
echo.

python server.py
if errorlevel 1 (
    echo.
    echo  El servidor se detuvo con un error.
    echo  Si es la primera vez que usas el sistema, ejecuta "instalar.bat".
)
pause
