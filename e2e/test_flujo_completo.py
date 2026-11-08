"""Prueba de aceptación de punta a punta (E2E) con Playwright.

Recorre el flujo completo como lo haría una persona y guarda un pantallazo de
cada paso en docs/capturas/ (listos para el informe).

Requisitos: el sistema corriendo (frontend + backend) y los usuarios demo.
    pip install -r e2e/requirements.txt
    playwright install chromium
    pytest e2e -s                                   # contra http://localhost:5173
    $env:E2E_BASE_URL="http://localhost:8080"; pytest e2e -s   # contra Docker (PowerShell)
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

BASE = os.getenv("E2E_BASE_URL", "http://localhost:5173").rstrip("/")
#BASE = os.getenv("E2E_BASE_URL", "https://g6x4777s-5173.use.devtunnels.ms/").rstrip("/")
CAPTURAS = Path(__file__).resolve().parent.parent / "docs" / "capturas"
TIEMPO_IA_MS = int(os.getenv("E2E_TIEMPO_IA_MS", "180000"))  # la IA local puede tardar en CPU

EMPLEADO = ("facturacion@demo-pqrs.co", "Empleado123*")
ADMIN = ("admin@demo-pqrs.co", "Admin123*")
CLAVE_NUEVO = "Ciudadano123*"


@pytest.fixture(scope="module")
def page():
    CAPTURAS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=os.getenv("E2E_VER", "0") != "1", slow_mo=150)
        contexto = navegador.new_context(viewport={"width": 1366, "height": 900}, locale="es-CO")
        pagina = contexto.new_page()
        pagina.set_default_timeout(15000)
        yield pagina
        navegador.close()


def captura(page: Page, nombre: str) -> None:
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(CAPTURAS / f"{nombre}.png"), full_page=True)
    print(f"  📸 docs/capturas/{nombre}.png")


def iniciar_sesion(page: Page, email: str, clave: str) -> None:
    page.goto(f"{BASE}/login")
    page.get_by_test_id("login-email").fill(email)
    page.get_by_test_id("login-password").fill(clave)
    page.get_by_test_id("login-enviar").click()
    expect(page.get_by_test_id("usuario-nombre")).to_be_visible()


def salir(page: Page) -> None:
    page.get_by_test_id("btn-salir").click()
    expect(page.get_by_test_id("login-email")).to_be_visible()


def test_flujo_completo_de_una_pqrs(page: Page):
    email_nuevo = f"ciudadano.{int(time.time())}@correo.com"

    # CA1 — registro, inicio de sesión y radicación
    page.goto(f"{BASE}/login")
    captura(page, "01_inicio_sesion")
    page.goto(f"{BASE}/registro")
    page.get_by_test_id("registro-nombre").fill("María Fernanda Ruiz")
    page.get_by_test_id("registro-email").fill(email_nuevo)
    page.get_by_test_id("registro-password").fill(CLAVE_NUEVO)
    page.get_by_test_id("registro-confirmacion").fill(CLAVE_NUEVO)
    page.get_by_test_id("registro-acepta").check()
    captura(page, "02_registro")
    page.get_by_test_id("registro-enviar").click()
    expect(page.get_by_test_id("btn-nueva-pqrs")).to_be_visible()

    page.get_by_test_id("btn-nueva-pqrs").click()
    page.get_by_test_id("pqrs-asunto").fill("Cobro duplicado en la factura de noviembre")
    page.get_by_test_id("pqrs-descripcion").fill(
        "Me cobraron dos veces la factura de noviembre en mi tarjeta de crédito. "
        "Solicito el reembolso del cobro duplicado lo antes posible."
    )
    captura(page, "03_formulario_radicacion")
    page.get_by_test_id("pqrs-enviar").click()

    # CA2, CA3, CA4 — se guarda, se clasifica con IA y se asigna el área
    radicado = page.get_by_test_id("detalle-radicado").inner_text()
    expect(page.get_by_test_id("detalle-tipo")).to_be_visible(timeout=TIEMPO_IA_MS)
    captura(page, "04_pqrs_radicada_y_clasificada")
    salir(page)

    # CA5 — el empleado del área la ve, la toma, responde y la resuelve
    iniciar_sesion(page, *EMPLEADO)
    fila = page.locator(f'[data-testid="fila-pqrs"][data-radicado="{radicado}"]')
    expect(fila, "La PQRS no llegó al área de Facturación: revisa cómo la clasificó la IA").to_be_visible(
        timeout=20000
    )
    captura(page, "05_bandeja_empleado")
    fila.click()
    expect(page.get_by_test_id("panel-ia")).to_be_visible()
    captura(page, "06_detalle_con_analisis_ia")

    page.get_by_test_id("btn-tomar").click()
    expect(page.get_by_test_id("insignia-estado")).to_have_text("En proceso")
    page.get_by_test_id("respuesta-texto").fill(
        "Hola, confirmamos el cobro duplicado. El reembolso se verá reflejado en su tarjeta en 5 días hábiles."
    )
    page.get_by_test_id("respuesta-enviar").click()
    expect(page.get_by_test_id("alerta-exito")).to_contain_text("Respuesta enviada")
    page.get_by_test_id("estado-nuevo").select_option("resuelto")
    page.get_by_test_id("estado-guardar").click()
    expect(page.get_by_test_id("insignia-estado")).to_have_text("Resuelto")
    captura(page, "07_caso_gestionado_y_resuelto")
    salir(page)

    # CA6 — el ciudadano ve el historial y la respuesta
    iniciar_sesion(page, email_nuevo, CLAVE_NUEVO)
    page.get_by_text(radicado).click()
    expect(page.get_by_test_id("linea-tiempo")).to_contain_text("confirmamos el cobro duplicado")
    captura(page, "08_seguimiento_del_ciudadano")
    salir(page)

    # Gerencia — métricas
    iniciar_sesion(page, *ADMIN)
    page.goto(f"{BASE}/metricas")
    expect(page.get_by_test_id("metricas")).to_be_visible()
    captura(page, "09_metricas_gerencia")
