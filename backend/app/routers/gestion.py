"""BackOffice: bandeja, gestión de casos y métricas para empleados y administradores."""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import Select, case, or_, select

from app.database import ahora_utc
from app.deps import DB, Admin, Personal
from app.models import Area, HistorialPqrs, Pqrs, Usuario
from app.schemas import (
    CambioEstadoIn,
    ComentarioIn,
    PqrsDetalleOut,
    PqrsListaOut,
    ReclasificacionIn,
)
from app.services import catalogo, flujo
from app.services.vistas import esta_vencida, vista_detalle, vista_lista

router = APIRouter(prefix="/api/gestion", tags=["Gestión (BackOffice)"])


def _visibles(usuario: Usuario) -> Select:
    """Un empleado ve las PQRS de su área; el administrador ve todas."""
    consulta = select(Pqrs)
    if usuario.rol == "empleado" and usuario.area_id is not None:
        consulta = consulta.where(Pqrs.area_id == usuario.area_id)
    return consulta


def _obtener(db, usuario: Usuario, pqrs_id: int) -> Pqrs:
    p = db.scalar(_visibles(usuario).where(Pqrs.id == pqrs_id))
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PQRS no encontrada o fuera de tu área")
    return p


def _guardar(db, p: Pqrs) -> dict:
    db.commit()
    db.refresh(p)
    return vista_detalle(p)


@router.get("/pqrs", response_model=list[PqrsListaOut])
def bandeja(
    usuario: Personal,
    db: DB,
    estado: str | None = Query(default=None, description="abierto | en_proceso | resuelto"),
    prioridad: str | None = None,
    tipo: str | None = None,
    categoria: str | None = None,
    area_id: int | None = None,
    q: str | None = Query(default=None, max_length=100, description="Busca en radicado, asunto y descripción"),
    solo_mias: bool = False,
    limite: int = Query(default=200, ge=1, le=500),
) -> list[dict]:
    consulta = _visibles(usuario)
    if estado:
        consulta = consulta.where(Pqrs.estado == estado)
    if prioridad:
        consulta = consulta.where(Pqrs.prioridad == prioridad)
    if tipo:
        consulta = consulta.where(Pqrs.tipo == tipo)
    if categoria:
        consulta = consulta.where(Pqrs.categoria == categoria)
    if area_id is not None:
        consulta = consulta.where(Pqrs.area_id == area_id)
    if solo_mias:
        consulta = consulta.where(Pqrs.asignado_a_id == usuario.id)
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.where(
            or_(Pqrs.radicado.ilike(patron), Pqrs.asunto.ilike(patron), Pqrs.descripcion.ilike(patron))
        )

    # Orden de atención: pendientes primero, luego por prioridad y antigüedad
    resueltas_al_final = case((Pqrs.estado == "resuelto", 1), else_=0)
    peso_prioridad = case(catalogo.PRIORIDAD_PESO, value=Pqrs.prioridad, else_=0)
    consulta = consulta.order_by(resueltas_al_final, peso_prioridad.desc(), Pqrs.creado_en.asc()).limit(limite)
    return [vista_lista(p) for p in db.scalars(consulta).all()]


@router.get("/pqrs/{pqrs_id}", response_model=PqrsDetalleOut)
def detalle(pqrs_id: int, usuario: Personal, db: DB) -> dict:
    return vista_detalle(_obtener(db, usuario, pqrs_id))


@router.post("/pqrs/{pqrs_id}/tomar", response_model=PqrsDetalleOut)
def tomar_caso(pqrs_id: int, usuario: Personal, db: DB) -> dict:
    """El empleado se asigna el caso; si estaba abierto pasa a 'En proceso'."""
    p = _obtener(db, usuario, pqrs_id)
    if p.asignado_a_id == usuario.id and p.estado != "abierto":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya tienes asignado este caso")
    p.asignado_a_id = usuario.id
    flujo.registrar(db, p, "asignada", f"Caso asignado a {usuario.nombre}.", usuario=usuario)
    if p.estado == "abierto":
        flujo.cambiar_estado(db, p, "en_proceso", usuario, "Un asesor está revisando su solicitud.")
    return _guardar(db, p)


@router.patch("/pqrs/{pqrs_id}/estado", response_model=PqrsDetalleOut)
def cambiar_estado(pqrs_id: int, datos: CambioEstadoIn, usuario: Personal, db: DB) -> dict:
    p = _obtener(db, usuario, pqrs_id)
    flujo.cambiar_estado(db, p, datos.estado, usuario, datos.comentario)
    return _guardar(db, p)


@router.post("/pqrs/{pqrs_id}/comentarios", response_model=PqrsDetalleOut)
def comentar(pqrs_id: int, datos: ComentarioIn, usuario: Personal, db: DB) -> dict:
    """Respuesta al ciudadano (visible) o nota interna (no visible)."""
    p = _obtener(db, usuario, pqrs_id)
    evento = "respuesta" if datos.visible_cliente else "nota"
    flujo.registrar(db, p, evento, datos.mensaje.strip(), usuario=usuario, visible_cliente=datos.visible_cliente)
    if datos.visible_cliente and p.asignado_a_id is None:
        p.asignado_a_id = usuario.id
    p.actualizado_en = ahora_utc()
    return _guardar(db, p)


@router.patch("/pqrs/{pqrs_id}/clasificacion", response_model=PqrsDetalleOut)
def corregir_clasificacion(pqrs_id: int, datos: ReclasificacionIn, usuario: Personal, db: DB) -> dict:
    """Corrección humana de la IA (queda en el historial y alimenta la métrica de precisión)."""
    p = _obtener(db, usuario, pqrs_id)
    flujo.reclasificar_manual(db, p, usuario, datos.tipo, datos.categoria, datos.prioridad, datos.motivo)
    return _guardar(db, p)


@router.post("/pqrs/{pqrs_id}/reclasificar-ia", response_model=PqrsDetalleOut, status_code=status.HTTP_202_ACCEPTED)
def reclasificar_con_ia(pqrs_id: int, tareas: BackgroundTasks, usuario: Personal, db: DB) -> dict:
    """Vuelve a enviar la PQRS al modelo (útil si Ollama estaba apagado)."""
    p = _obtener(db, usuario, pqrs_id)
    p.estado_ia = "pendiente"
    flujo.registrar(db, p, "nota", "Se solicitó una nueva clasificación con IA.", usuario=usuario)
    vista = _guardar(db, p)
    tareas.add_task(flujo.procesar_clasificacion, p.id)
    return vista


@router.get("/metricas")
def metricas(usuario: Admin, db: DB) -> dict:
    """Indicadores para la gerencia (calculados en memoria: suficiente para el prototipo)."""
    todas = db.scalars(select(Pqrs)).all()
    areas = {a.id: a.nombre for a in db.scalars(select(Area)).all()}
    corregidas = set(db.scalars(select(HistorialPqrs.pqrs_id).where(HistorialPqrs.evento == "reclasificada")).all())
    ahora = ahora_utc()

    clasificadas = [p for p in todas if p.estado_ia == "completada"]
    con_ia = [p for p in clasificadas if p.modelo_ia]
    resueltas = [p for p in todas if p.resuelto_en]
    horas_resolucion = [(p.resuelto_en - p.creado_en).total_seconds() / 3600 for p in resueltas]

    dias = [(ahora - timedelta(days=i)).date() for i in range(6, -1, -1)]
    por_dia = Counter(p.creado_en.date() for p in todas)

    def conteo(valores) -> dict:
        return dict(Counter(v for v in valores if v is not None))

    return {
        "total": len(todas),
        "abiertas": sum(p.estado != "resuelto" for p in todas),
        "vencidas": sum(esta_vencida(p) for p in todas),
        "criticas_pendientes": sum(p.prioridad == "critica" and p.estado != "resuelto" for p in todas),
        "por_estado": conteo(p.estado for p in todas),
        "por_prioridad": conteo(p.prioridad for p in todas),
        "por_tipo": conteo(p.tipo for p in todas),
        "por_categoria": conteo(p.categoria for p in todas),
        "por_area": conteo(areas.get(p.area_id) for p in todas),
        "clasificacion": {
            "pendientes": sum(p.estado_ia == "pendiente" for p in todas),
            "por_origen": conteo(p.clasificado_por for p in todas),
            "corregidas_por_humano": len(corregidas),
            "tasa_correccion_pct": round(100 * len(corregidas) / len(clasificadas), 1) if clasificadas else 0.0,
            "tiempo_promedio_ia_ms": round(statistics.mean(p.duracion_ia_ms for p in con_ia if p.duracion_ia_ms))
            if any(p.duracion_ia_ms for p in con_ia) else None,
        },
        "tiempo_promedio_resolucion_h": round(statistics.mean(horas_resolucion), 1) if horas_resolucion else None,
        "ultimos_7_dias": [{"fecha": d.isoformat(), "cantidad": por_dia.get(d, 0)} for d in dias],
    }
