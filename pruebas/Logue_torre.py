import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://core.sincoerp.com/SincoSoporte/Torre.html")
    page.get_by_role("textbox", name="UsuarioWindows").click()
    page.get_by_role("textbox", name="UsuarioWindows").fill("yessica.olaya")
    page.get_by_role("textbox", name="Contraseña").click()
    page.get_by_role("textbox", name="Contraseña").press("CapsLock")
    page.get_by_role("textbox", name="Contraseña").fill("J")
    page.get_by_role("textbox", name="Contraseña").press("CapsLock")
    page.get_by_role("textbox", name="Contraseña").fill("Jeronimo2026")
    page.get_by_role("button", name="Ingresar con Windows").click()
    page.get_by_title("Master").get_by_role("img").click()
    page.get_by_title("Entornos").click()
    page.locator("#listWidget").get_by_role("textbox").click()
    page.locator("#listWidget").get_by_role("textbox").fill("rizek")
    page.locator("div").filter(has_text=re.compile(r"^REPLICA_SincoConsRizekREPLICA CONSTRUCTORA RIZEK & ASOCIADOS SRLRéplica$")).nth(2).click()
    page.locator("section:nth-child(2) > .siguienteIcon").click()
    page.get_by_text("Principal", exact=True).click()
    page.locator("#toolkit").get_by_role("complementary").filter(has_text="Bases de datosREPLICA_SincoConsRizekreplica constructora rizek & asociados").get_by_role("img").first.click()
    with page.expect_popup() as page1_info:
        page.locator(".contenedor-opcion > .siguienteIcon").first.click()
    page1 = page1_info.value
    page1.locator("#ddlEmpresa").select_option("1")
    page1.locator("#ddlEmpresa").select_option("1")
    page1.locator("#ddlEmpresa").select_option("1")

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
