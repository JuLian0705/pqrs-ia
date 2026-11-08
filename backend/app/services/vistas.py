"""Convierte entidades en las vistas que ve cada rol."""
from __future__ import annotations
from app.database import ahora_utc
from app.models import HistorialPqrs, Pqrs
from app.services import catalogo


def _historial(eventos: list[HistorialPqrs], solo_visibles: bool) -> list[dict]:
    salida = []
    for h in eventos:
        if solo_visibles and not h.visible_cliente:
            continue
        if h.usuario is None:
            autor = "Sistema"
        elif solo_visibles and h.usuario.rol != "cliente":
            autor = "Equipo de atención"  # el ciudadano no ve nombres internos
        else:
            autor = h.usuario.nombre
        salida.append(
            {
                "id": h.id,
                "evento": h.evento,
                "detalle": h.detalle,
                "estado_anterior": h.estado_anterior,
                "estado_nuevo": h.estado_nuevo,
                "visible_cliente": h.visible_cliente,
                "autor": autor,
                "creado_en": h.creado_en,
            }
        )
    return salida


def esta_vencida(p: Pqrs) -> bool:
    return p.estado != "resuelto" and p.fecha_vencimiento < ahora_utc()


def vista_cliente(p: Pqrs, con_historial: bool = True) -> dict:
    return {
        "id": p.id,
        "radicado": p.radicado,
        "asunto": p.asunto,
        "descripcion": p.descripcion,
        "tipo": p.tipo,
        "tipo_nombre": catalogo.TIPOS.get(p.tipo) if p.tipo else None,
        "area_nombre": p.area.nombre if p.area else None,
        "estado": p.estado,
        "estado_ia": p.estado_ia,
        "fecha_vencimiento": p.fecha_vencimiento,
        "creado_en": p.creado_en,
        "actualizado_en": p.actualizado_en,
        "resuelto_en": p.resuelto_en,
        "historial": _historial(p.historial, solo_visibles=True) if con_historial else [],
    }


def vista_lista(p: Pqrs) -> dict:
    return {
        "id": p.id,
        "radicado": p.radicado,
        "asunto": p.asunto,
        "tipo": p.tipo,
        "categoria": p.categoria,
        "prioridad": p.prioridad,
        "estado": p.estado,
        "estado_ia": p.estado_ia,
        "clasificado_por": p.clasificado_por,
        "area_nombre": p.area.nombre if p.area else None,
        "cliente_nombre": p.cliente.nombre,
        "asignado_a_nombre": p.asignado_a.nombre if p.asignado_a else None,
        "fecha_vencimiento": p.fecha_vencimiento,
        "vencida": esta_vencida(p),
        "creado_en": p.creado_en,
    }


def vista_detalle(p: Pqrs) -> dict:
    return {
        **vista_lista(p),
        "descripcion": p.descripcion,
        "resumen": p.resumen,
        "justificacion": p.justificacion,
        "modelo_ia": p.modelo_ia,
        "duracion_ia_ms": p.duracion_ia_ms,
        "error_ia": p.error_ia,
        "area_id": p.area_id,
        "asignado_a_id": p.asignado_a_id,
        "cliente_email": p.cliente.email,
        "actualizado_en": p.actualizado_en,
        "resuelto_en": p.resuelto_en,
        "historial": _historial(p.historial, solo_visibles=False),
    }
