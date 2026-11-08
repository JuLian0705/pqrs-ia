"""Reglas de negocio del ciclo de vida de una PQRS."""
from __future__ import annotations

import logging
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.database import SessionLocal, ahora_utc
from app.models import Area, HistorialPqrs, Pqrs, Usuario
from app.services import catalogo
from app.services.clasificador import ResultadoClasificacion, clasificar
from app.services.plazos import generar_radicado, sumar_dias_habiles

log = logging.getLogger(__name__)


def registrar(
    db: Session,
    p: Pqrs,
    evento: str,
    detalle: str,
    usuario: Usuario | None = None,
    visible_cliente: bool = False,
    estado_anterior: str | None = None,
    estado_nuevo: str | None = None,
) -> None:
    db.add(
        HistorialPqrs(
            pqrs=p,
            usuario_id=usuario.id if usuario else None,
            evento=evento,
            detalle=detalle,
            visible_cliente=visible_cliente,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_nuevo,
        )
    )


def area_por_codigo(db: Session, codigo: str) -> Area | None:
    return db.scalar(select(Area).where(Area.codigo == codigo))


def radicar(db: Session, cliente: Usuario, asunto: str, descripcion: str) -> Pqrs:
    ahora = ahora_utc()
    p = Pqrs(
        asunto=asunto,
        descripcion=descripcion,
        cliente_id=cliente.id,
        estado="abierto",
        estado_ia="pendiente",
        fecha_vencimiento=sumar_dias_habiles(ahora, settings.dias_habiles_respuesta),
        creado_en=ahora,
        actualizado_en=ahora,
    )
    db.add(p)
    db.flush()  
    p.radicado = generar_radicado(p.id, ahora)
    registrar(
        db, p, "creada",
        f"Solicitud radicada con el número {p.radicado}. Plazo de respuesta: "
        f"{settings.dias_habiles_respuesta} días hábiles.",
        usuario=cliente, visible_cliente=True, estado_nuevo="abierto",
    )
    db.commit()
    db.refresh(p)
    return p


def aplicar_clasificacion(db: Session, p: Pqrs, r: ResultadoClasificacion) -> None:
    area_anterior = p.area_id
    area = area_por_codigo(db, r.area)
    p.tipo, p.categoria, p.prioridad = r.tipo, r.categoria, r.prioridad
    p.resumen, p.justificacion = r.resumen, r.justificacion
    p.clasificado_por, p.modelo_ia, p.duracion_ia_ms, p.error_ia = r.origen, r.modelo, r.duracion_ms, r.error
    p.area_id = area.id if area else None
    p.estado_ia = "completada"

    nombre_area = area.nombre if area else "sin área"
    origen = "con IA" if r.origen == "ia" else "por reglas de respaldo"
    registrar(
        db, p, "clasificada",
        f"Clasificada {origen} como {catalogo.TIPOS[r.tipo]} ({catalogo.CATEGORIAS[r.categoria]}), "
        f"prioridad {catalogo.PRIORIDADES[r.prioridad]}, en {r.duracion_ms} ms.",
    )
    if p.area_id != area_anterior:
        registrar(
            db, p, "asignada",
            f"Su solicitud fue clasificada como {catalogo.TIPOS[r.tipo]} y remitida al área {nombre_area}.",
            visible_cliente=True,
        )


def procesar_clasificacion(pqrs_id: int) -> None:
    """Tarea en segundo plano: clasifica la PQRS sin bloquear al ciudadano."""
    with SessionLocal() as db:
        p = db.get(Pqrs, pqrs_id)
        if p is None:
            return
        try:
            resultado = clasificar(p.asunto, p.descripcion)
            aplicar_clasificacion(db, p, resultado)
            db.commit()
            log.info("PQRS %s clasificada (%s) en %s ms", p.radicado, resultado.origen, resultado.duracion_ms)
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("No se pudo clasificar la PQRS %s", pqrs_id)
            p = db.get(Pqrs, pqrs_id)
            if p is not None:
                p.estado_ia = "error"
                db.commit()


def cambiar_estado(db: Session, p: Pqrs, nuevo: str, usuario: Usuario, comentario: str | None) -> None:
    if nuevo == p.estado:
        raise HTTPException(status.HTTP_409_CONFLICT, f"La PQRS ya está en estado {catalogo.ESTADOS[nuevo]}")
    if nuevo not in catalogo.TRANSICIONES[p.estado]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"No se puede pasar de {catalogo.ESTADOS[p.estado]} a {catalogo.ESTADOS[nuevo]}",
        )
    comentario = (comentario or "").strip()
    if nuevo == "resuelto" and not comentario and not any(h.evento == "respuesta" for h in p.historial):
        raise HTTPException(
            422,
            "Para resolver la PQRS escribe la respuesta al ciudadano",
        )

    anterior = p.estado
    p.estado = nuevo
    p.resuelto_en = ahora_utc() if nuevo == "resuelto" else None
    if p.asignado_a_id is None:
        p.asignado_a_id = usuario.id
    detalle = comentario or f"Estado actualizado a {catalogo.ESTADOS[nuevo]}."
    evento = "respuesta" if (nuevo == "resuelto" and comentario) else "estado"
    registrar(db, p, evento, detalle, usuario=usuario, visible_cliente=True,
              estado_anterior=anterior, estado_nuevo=nuevo)


def reclasificar_manual(db: Session, p: Pqrs, usuario: Usuario, tipo: str, categoria: str, prioridad: str,
                        motivo: str | None) -> None:
    antes = f"{p.tipo}/{p.categoria}/{p.prioridad}"
    area_anterior = p.area_id
    area = area_por_codigo(db, catalogo.area_para_categoria(categoria))
    p.tipo, p.categoria, p.prioridad = tipo, categoria, prioridad
    p.area_id = area.id if area else None
    p.clasificado_por = "humano"
    p.estado_ia = "completada"
    detalle = f"Clasificación corregida de {antes} a {tipo}/{categoria}/{prioridad}."
    if motivo:
        detalle += f" Motivo: {motivo.strip()}"
    registrar(db, p, "reclasificada", detalle, usuario=usuario)
    if p.area_id != area_anterior and area is not None:
        registrar(db, p, "asignada", f"Su solicitud fue remitida al área {area.nombre}.",
                  usuario=usuario, visible_cliente=True)
