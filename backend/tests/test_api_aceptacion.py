"""Pruebas de integración de la API, organizadas por criterio de aceptación (CA)
del documento de formulación del proyecto."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

TEXTO_COBRO = {
    "asunto": "Cobro duplicado en octubre",
    "descripcion": "Me cobraron dos veces la factura de octubre en mi tarjeta. Necesito que me devuelvan el valor.",
}


def _radicar(client, headers, datos=TEXTO_COBRO) -> dict:
    r = client.post("/api/pqrs", json=datos, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ CA1
def test_ca1_crear_cuenta_iniciar_sesion_y_radicar(client):
    r = client.post("/api/auth/registro",
                    json={"nombre": "Laura Gómez", "email": "Laura@Correo.com", "password": "Segura123"})
    assert r.status_code == 201
    assert r.json()["usuario"]["rol"] == "cliente"

    r = client.post("/api/auth/login", json={"email": "laura@correo.com", "password": "Segura123"})
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    pqrs = _radicar(client, headers)
    assert pqrs["radicado"].startswith("PQRS-")
    assert pqrs["estado"] == "abierto"


def test_ca1_rechaza_credenciales_y_datos_invalidos(client, cliente_auth):
    cliente_auth("laura@correo.com")
    assert client.post("/api/auth/login", json={"email": "laura@correo.com", "password": "mala"}).status_code == 401
    assert client.post("/api/auth/registro", json={"nombre": "Otra", "email": "laura@correo.com",
                                                   "password": "Segura123"}).status_code == 409
    assert client.post("/api/auth/registro", json={"nombre": "Débil", "email": "debil@correo.com",
                                                   "password": "soloLetras"}).status_code == 422


def test_asistente_de_redaccion_usa_respaldo_si_ia_esta_deshabilitada(client, cliente_auth):
    respuesta = client.post(
        "/api/asistente/chat",
        json={"mensajes": [{"rol": "usuario", "texto": "Me cobraron dos veces la factura."}]},
        headers=cliente_auth(),
    )

    assert respuesta.status_code == 200
    assert "asistente de IA no está disponible" in respuesta.text


# ------------------------------------------------------------------ CA2
def test_ca2_la_solicitud_se_guarda_integra(client, cliente_auth):
    h = cliente_auth()
    creada = _radicar(client, h)
    r = client.get(f"/api/pqrs/{creada['id']}", headers=h)
    assert r.status_code == 200
    assert r.json()["descripcion"] == TEXTO_COBRO["descripcion"]
    assert r.json()["historial"][0]["evento"] == "creada"


def test_ca2_valida_longitud_minima(client, cliente_auth):
    r = client.post("/api/pqrs", json={"asunto": "Hola", "descripcion": "corto"}, headers=cliente_auth())
    assert r.status_code == 422


# ------------------------------------------------------------------ CA3 y CA4
def test_ca3_ca4_clasificacion_con_ia_simulada(client, cliente_auth, crear_personal, monkeypatch):
    from app.services import clasificador, flujo

    respuesta_modelo = json.dumps({"tipo": "R", "categoria": "facturacion", "prioridad": "alta",
                                   "resumen": "El cliente reporta un cobro duplicado y pide el reembolso.",
                                   "justificacion": "Exige corregir un cobro."})
    monkeypatch.setattr(clasificador, "_llamar_ollama", lambda mensajes: respuesta_modelo)
    monkeypatch.setattr(flujo, "clasificar", lambda a, d: clasificador.clasificar(a, d, usar_ia=True))

    creada = _radicar(client, cliente_auth())  # la clasificación corre en segundo plano
    admin = crear_personal("admin@empresa.com", rol="admin")
    d = client.get(f"/api/gestion/pqrs/{creada['id']}", headers=admin).json()

    assert d["estado_ia"] == "completada"
    assert (d["tipo"], d["categoria"], d["prioridad"]) == ("R", "facturacion", "alta")
    assert d["clasificado_por"] == "ia" and d["resumen"]
    assert d["area_nombre"] == "Facturación y Cartera"
    assert any(e["evento"] == "clasificada" and e["autor"] == "Sistema" for e in d["historial"])


def test_ca4_sin_ollama_se_clasifica_por_reglas(client, cliente_auth, crear_personal):
    creada = _radicar(client, cliente_auth())
    admin = crear_personal("admin@empresa.com", rol="admin")
    d = client.get(f"/api/gestion/pqrs/{creada['id']}", headers=admin).json()
    assert d["clasificado_por"] == "reglas"
    assert (d["tipo"], d["categoria"], d["prioridad"]) == ("R", "facturacion", "alta")


# ------------------------------------------------------------------ CA5
def test_ca5_empleado_gestiona_solo_las_pqrs_de_su_area(client, cliente_auth, crear_personal):
    creada = _radicar(client, cliente_auth())
    facturacion = crear_personal("camila@empresa.com", area_codigo="facturacion_cartera")
    soporte = crear_personal("diego@empresa.com", area_codigo="soporte_tecnico")

    bandeja = client.get("/api/gestion/pqrs", headers=facturacion).json()
    assert [p["id"] for p in bandeja] == [creada["id"]]
    assert client.get("/api/gestion/pqrs", headers=soporte).json() == []
    assert client.get(f"/api/gestion/pqrs/{creada['id']}", headers=soporte).status_code == 404

    r = client.post(f"/api/gestion/pqrs/{creada['id']}/tomar", headers=facturacion)
    assert r.status_code == 200 and r.json()["estado"] == "en_proceso"

    r = client.patch(f"/api/gestion/pqrs/{creada['id']}/estado", json={"estado": "resuelto"}, headers=facturacion)
    assert r.status_code == 422  # no se puede resolver sin responder al ciudadano

    r = client.patch(f"/api/gestion/pqrs/{creada['id']}/estado",
                     json={"estado": "resuelto", "comentario": "Reembolso aprobado."}, headers=facturacion)
    assert r.status_code == 200 and r.json()["estado"] == "resuelto"
    assert r.json()["resuelto_en"] is not None


def test_ca5_transiciones_invalidas_y_filtros(client, cliente_auth, crear_personal):
    creada = _radicar(client, cliente_auth())
    admin = crear_personal("admin@empresa.com", rol="admin")
    r = client.patch(f"/api/gestion/pqrs/{creada['id']}/estado", json={"estado": "abierto"}, headers=admin)
    assert r.status_code == 409
    assert len(client.get("/api/gestion/pqrs?prioridad=alta", headers=admin).json()) == 1
    assert client.get("/api/gestion/pqrs?prioridad=baja", headers=admin).json() == []
    assert len(client.get(f"/api/gestion/pqrs?q={creada['radicado']}", headers=admin).json()) == 1


def test_ca5_correccion_humana_cambia_el_area(client, cliente_auth, crear_personal):
    creada = _radicar(client, cliente_auth())
    admin = crear_personal("admin@empresa.com", rol="admin")
    soporte = crear_personal("diego@empresa.com", area_codigo="soporte_tecnico")

    r = client.patch(f"/api/gestion/pqrs/{creada['id']}/clasificacion",
                     json={"tipo": "R", "categoria": "soporte_tecnico", "prioridad": "media",
                           "motivo": "El cobro lo generó una falla de la app"}, headers=admin)
    assert r.status_code == 200
    assert r.json()["clasificado_por"] == "humano"
    assert any(e["evento"] == "reclasificada" for e in r.json()["historial"])
    assert [p["id"] for p in client.get("/api/gestion/pqrs", headers=soporte).json()] == [creada["id"]]

    m = client.get("/api/gestion/metricas", headers=admin).json()
    assert m["clasificacion"]["corregidas_por_humano"] == 1


# ------------------------------------------------------------------ CA6
def test_ca6_cliente_ve_estados_y_respuestas_pero_no_notas_internas(client, cliente_auth, crear_personal):
    h = cliente_auth()
    creada = _radicar(client, h)
    admin = crear_personal("admin@empresa.com", rol="admin")
    base = f"/api/gestion/pqrs/{creada['id']}"
    client.post(f"{base}/tomar", headers=admin)
    client.post(f"{base}/comentarios", json={"mensaje": "Revisar con cartera", "visible_cliente": False},
                headers=admin)
    client.post(f"{base}/comentarios", json={"mensaje": "Ya validamos el cobro doble.", "visible_cliente": True},
                headers=admin)
    client.patch(f"{base}/estado", json={"estado": "resuelto"}, headers=admin)

    vista = client.get(f"/api/pqrs/{creada['id']}", headers=h).json()
    textos = [e["detalle"] for e in vista["historial"]]
    assert vista["estado"] == "resuelto"
    assert "Ya validamos el cobro doble." in textos
    assert "Revisar con cartera" not in textos
    assert "prioridad" not in vista  # dato interno
    assert all(e["autor"] in {"Sistema", "Equipo de atención", "Ciudadano Prueba"} for e in vista["historial"])

    lista = client.get("/api/pqrs/mias", headers=h).json()
    assert [p["id"] for p in lista] == [creada["id"]]


# ------------------------------------------------------------------ Seguridad
def test_control_de_acceso_por_rol(client, cliente_auth, crear_personal):
    h1 = cliente_auth("uno@correo.com")
    h2 = cliente_auth("dos@correo.com")
    creada = _radicar(client, h1)
    empleado = crear_personal("camila@empresa.com", area_codigo="facturacion_cartera")

    assert client.get("/api/pqrs/mias").status_code == 401
    assert client.get("/api/gestion/pqrs", headers=h1).status_code == 403
    assert client.get(f"/api/pqrs/{creada['id']}", headers=h2).status_code == 404
    assert client.post("/api/pqrs", json=TEXTO_COBRO, headers=empleado).status_code == 403
    assert client.get("/api/gestion/metricas", headers=empleado).status_code == 403
    assert client.get("/api/pqrs/mias", headers={"Authorization": "Bearer token-falso"}).status_code == 401


def test_endpoints_de_sistema(client):
    assert client.get("/api/salud").json()["estado"] == "ok"
    cat = client.get("/api/catalogo").json()
    assert len(cat["areas"]) == 6 and "S" in cat["tipos"]
