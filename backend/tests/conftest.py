"""Configuración de pruebas: base SQLite temporal, IA desactivada y hash rápido."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Debe ir ANTES de importar la app: la configuración se lee al importar.
_DB = Path(tempfile.gettempdir()) / "pqrs_pruebas.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB.as_posix()}"
os.environ["IA_HABILITADA"] = "false"
os.environ["SEED_DEMO"] = "false"
os.environ["PASSWORD_ITERACIONES"] = "1000"
os.environ["SECRET_KEY"] = "clave-de-pruebas-con-al-menos-32-caracteres"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client():
    """Cliente HTTP contra una base limpia en cada prueba."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.database import Base, engine
    from app.main import app

    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as c:  # el lifespan crea tablas y áreas
        yield c
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def crear_personal(client):
    """Crea un empleado o admin directamente en BD y devuelve sus encabezados de autenticación."""
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import Area, Usuario
    from app.security import crear_token, hash_password

    def _crear(email: str, rol: str = "empleado", area_codigo: str | None = None) -> dict:
        with SessionLocal() as db:
            area = db.scalar(select(Area).where(Area.codigo == area_codigo)) if area_codigo else None
            u = Usuario(nombre=email.split("@")[0].title(), email=email, rol=rol,
                        password_hash=hash_password("Clave1234"), area_id=area.id if area else None)
            db.add(u)
            db.commit()
            return {"Authorization": f"Bearer {crear_token(u.id, u.rol)}"}

    return _crear


@pytest.fixture()
def cliente_auth(client):
    """Registra un ciudadano y devuelve sus encabezados de autenticación."""

    def _registrar(email: str = "ciudadano@correo.com") -> dict:
        r = client.post("/api/auth/registro",
                        json={"nombre": "Ciudadano Prueba", "email": email, "password": "Clave1234"})
        assert r.status_code == 201, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _registrar
