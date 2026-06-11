"""
Prueba: Flujo Completo Addon/Aprobaciones
Módulo: Aprobaciones
Orquesta: InstalarAddon → DarAcceso → Validación específica del addon
"""
import sys
import os
import importlib

sys.path.insert(0, os.path.dirname(__file__))

import InstalarAddon
import DarAcceso


def ejecutar(pagina, frame, on_paso=None, parametros=None, addon=None):

    # Aceptar tanto `parametros={"addon": ...}` (lo que manda el dashboard)
    # como `addon=...` (uso directo desde código)
    if not addon:
        parametros = parametros or {}
        addon = parametros.get("addon")

    # Normalizar número del addon PRESERVANDO el signo.
    # Default 142 (positivo). Si el usuario escribió "-142" se respeta.
    addon_str = str(addon or "142").strip()
    if addon_str.startswith("+"):
        addon_str = addon_str[1:]
    if not addon_str:
        addon_str = "142"

    # `addon_num`  → sin signo, para nombrar el módulo de validación
    #                 (Python no permite "-" en nombres de módulo)
    # `addon_full` → con signo tal como vino, para mostrar y para InstalarAddon
    addon_num  = addon_str.lstrip("-").strip() or "142"
    addon_full = addon_str

    # ─────────────────────────────────────────────
    # PASO 1: Instalar Addon
    # ─────────────────────────────────────────────
    if on_paso: on_paso(f"── PASO 1: Instalar Addon {addon_full} ──")

    resultado1 = InstalarAddon.ejecutar(pagina, frame, on_paso, parametros=parametros, addon=addon_full)

    if resultado1.get("estado") != "ok":
        return {
            **resultado1,
            "prueba": f"Flujo Addon {addon_full}",
            "obtenido": f"[PASO 1 FALLÓ] {resultado1.get('obtenido', '')}",
        }

    # ─────────────────────────────────────────────
    # PASO 2: Dar Acceso
    # ─────────────────────────────────────────────
    if on_paso: on_paso("── PASO 2: Dar Acceso ──")

    resultado2 = DarAcceso.ejecutar(pagina, frame, on_paso)

    if resultado2.get("estado") != "ok":
        return {
            **resultado2,
            "prueba": f"Flujo Addon {addon_full}",
            "obtenido": f"[PASO 2 FALLÓ] {resultado2.get('obtenido', '')}",
        }

    # ─────────────────────────────────────────────
    # PASO 3: Validación específica del addon
    # ─────────────────────────────────────────────
    if on_paso: on_paso(f"── PASO 3: Validar Addon {addon_full} ──")

    try:
        modulo_addon = importlib.import_module(f"Addon{addon_num}")
        importlib.reload(modulo_addon)
        resultado3 = modulo_addon.ejecutar(pagina, frame, on_paso)
    except ModuleNotFoundError:
        return {
            "prueba":       f"Flujo Addon {addon_full}",
            "estado":       "fail",
            "dato_entrada": addon_full,
            "esperado":     f"Módulo de validación Addon{addon_num}.py",
            "obtenido":     f"No existe el archivo Addon{addon_num}.py en la carpeta pruebas/ — debes crearlo",
        }
    except Exception as e:
        return {
            "prueba":       f"Flujo Addon {addon_full}",
            "estado":       "fail",
            "dato_entrada": addon_full,
            "esperado":     "Validación del addon sin errores",
            "obtenido":     f"[PASO 3 FALLÓ] {str(e)[:200]}",
        }

    return {
        **resultado3,
        "prueba": f"Flujo Addon {addon_full}",
    }
