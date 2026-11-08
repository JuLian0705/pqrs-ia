"""Punto de entrada de la API del Sistema Inteligente de Gestión de PQRS."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.deps import DB
from app.models import Area
from app.routers import asistente_ai, auth, gestion, pqrs
from app.seed import asegurar_areas, cargar_demo
from app.services import catalogo
from app.services.clasificador import ollama_disponible, precalentar_modelo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        asegurar_areas(db)
        if settings.seed_demo:
            cargar_demo(db)
    # Carga el modelo de IA en segundo plano: la API arranca de inmediato y
    # la primera PQRS ya no espera los segundos de carga del modelo.
    if settings.ia_habilitada and settings.precalentar_modelo:
        threading.Thread(target=precalentar_modelo, name="precalentar-ia", daemon=True).start()
    yield


app = FastAPI(
    title=settings.app_nombre,
    version=settings.app_version,
    description=(
        "API del prototipo funcional. Radica PQRS, las clasifica con Llama (vía Ollama) "
        "y permite gestionarlas con trazabilidad completa."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origenes,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(pqrs.router)
app.include_router(gestion.router)
app.include_router(asistente_ai.router)


@app.get("/api/salud", tags=["Sistema"])
def salud() -> dict:
    """Estado del backend y de la conexión con el modelo de IA."""
    disponible, modelos = ollama_disponible() if settings.ia_habilitada else (False, [])
    return {
        "estado": "ok",
        "version": settings.app_version,
        "ia": {
            "habilitada": settings.ia_habilitada,
            "ollama_disponible": disponible,
            "modelo": settings.ollama_modelo,
            "modelo_descargado": any(m in (settings.ollama_modelo, f"{settings.ollama_modelo}:latest")
                                     for m in modelos),
        },
    }


@app.get("/api/catalogo", tags=["Sistema"])
def catalogo_publico(db: DB) -> dict:
    """Listas cerradas que usan los formularios y filtros del frontend."""
    return {
        "tipos": catalogo.TIPOS,
        "categorias": catalogo.CATEGORIAS,
        "prioridades": catalogo.PRIORIDADES,
        "estados": catalogo.ESTADOS,
        "areas": [{"id": a.id, "codigo": a.codigo, "nombre": a.nombre}
                  for a in db.scalars(select(Area).order_by(Area.nombre)).all()],
    }