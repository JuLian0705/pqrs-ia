"""Módulo del ciudadano: radicar y consultar sus PQRS."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select

from app.deps import DB, Cliente
from app.models import Pqrs
from app.schemas import PqrsClienteOut, PqrsCrear
from app.services import flujo
from app.services.vistas import vista_cliente

router = APIRouter(prefix="/api/pqrs", tags=["PQRS - Ciudadano"])


@router.post("", response_model=PqrsClienteOut, status_code=status.HTTP_201_CREATED)
def radicar(datos: PqrsCrear, tareas: BackgroundTasks, usuario: Cliente, db: DB) -> dict:
    """Radica la PQRS y la envía a clasificar en segundo plano (la respuesta es inmediata)."""
    p = flujo.radicar(db, usuario, datos.asunto, datos.descripcion)
    tareas.add_task(flujo.procesar_clasificacion, p.id)
    return vista_cliente(p)


@router.get("/mias", response_model=list[PqrsClienteOut])
def mis_pqrs(usuario: Cliente, db: DB) -> list[dict]:
    filas = db.scalars(select(Pqrs).where(Pqrs.cliente_id == usuario.id).order_by(Pqrs.creado_en.desc())).all()
    return [vista_cliente(p, con_historial=False) for p in filas]


@router.get("/{pqrs_id}", response_model=PqrsClienteOut)
def detalle(pqrs_id: int, usuario: Cliente, db: DB) -> dict:
    p = db.get(Pqrs, pqrs_id)
    if p is None or p.cliente_id != usuario.id:  # 404 también si es de otro: no revela que existe
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PQRS no encontrada")
    return vista_cliente(p)
