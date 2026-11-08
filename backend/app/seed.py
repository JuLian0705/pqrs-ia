"""Datos iniciales: áreas (siempre) y usuarios/PQRS de demostración (opcional)."""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import ahora_utc
from app.models import Area, Pqrs, Usuario
from app.security import hash_password
from app.services import catalogo, flujo
from app.services.clasificador import clasificar
from app.services.plazos import generar_radicado, sumar_dias_habiles

log = logging.getLogger(__name__)

# Credenciales SOLO para la demostración del prototipo (se documentan en el README).
USUARIOS_DEMO = [
    ("Administrador PQRS", "admin@demo-pqrs.co", "Admin123*", "admin", None),
    ("Camila Ortiz", "facturacion@demo-pqrs.co", "Empleado123*", "empleado", "facturacion_cartera"),
    ("Diego Ramírez", "soporte@demo-pqrs.co", "Empleado123*", "empleado", "soporte_tecnico"),
    ("Paula Medina", "atencion@demo-pqrs.co", "Empleado123*", "empleado", "atencion_cliente"),
    ("Laura Gómez", "cliente@demo-pqrs.co", "Cliente123*", "cliente", None),
    ("Andrés Rojas", "cliente2@demo-pqrs.co", "Cliente123*", "cliente", None),
]

# (cliente, días atrás, asunto, descripción, estado final, respuesta)
PQRS_DEMO = [
    ("cliente@demo-pqrs.co", 6, "Cobro duplicado en octubre",
     "Me cobraron dos veces la factura de octubre en mi tarjeta de crédito. Necesito que me devuelvan el valor "
     "del cobro duplicado lo antes posible.",
     "resuelto", "Confirmamos el cobro duplicado. El reembolso se verá reflejado en su tarjeta en 5 días hábiles."),
    ("cliente2@demo-pqrs.co", 5, "Sin internet desde ayer",
     "Desde ayer no tengo servicio de internet y ya reinicié el módem varias veces. Trabajo desde casa y no "
     "puedo conectarme.",
     "en_proceso", "Programamos una visita técnica para mañana entre 8:00 a. m. y 12:00 m."),
    ("cliente@demo-pqrs.co", 4, "Mala actitud de un asesor",
     "El asesor que me atendió ayer en la sede del centro fue grosero, me levantó la voz y se negó a darme su "
     "nombre. Pido que revisen la actitud de ese funcionario.",
     "abierto", None),
    ("cliente2@demo-pqrs.co", 3, "Compras que no hice",
     "Aparecen compras en mi cuenta que yo no hice. Creo que alguien suplantó mi identidad. Bloqueen todo de "
     "inmediato.",
     "abierto", None),
    ("cliente@demo-pqrs.co", 2, "Copia de facturas",
     "Solicito una copia de mis facturas de los últimos seis meses para presentarlas en mi declaración de renta.",
     "abierto", None),
    ("cliente2@demo-pqrs.co", 1, "Chat en la página web",
     "Sugiero habilitar un canal de atención por chat en la página web, porque las filas en las sedes son muy "
     "largas.",
     "abierto", None),
]


def asegurar_areas(db: Session) -> None:
    existentes = set(db.scalars(select(Area.codigo)).all())
    for codigo, nombre in catalogo.AREAS.items():
        if codigo not in existentes:
            db.add(Area(codigo=codigo, nombre=nombre))
    db.commit()


def cargar_demo(db: Session) -> None:
    if db.scalar(select(func.count(Usuario.id))):
        return  # la base ya tiene datos
    log.info("Cargando datos de demostración…")
    areas = {a.codigo: a for a in db.scalars(select(Area)).all()}
    usuarios: dict[str, Usuario] = {}
    for nombre, email, clave, rol, area in USUARIOS_DEMO:
        u = Usuario(nombre=nombre, email=email, password_hash=hash_password(clave), rol=rol,
                    area_id=areas[area].id if area else None)
        db.add(u)
        usuarios[email] = u
    db.flush()

    ahora = ahora_utc()
    for email, dias, asunto, descripcion, estado, respuesta in PQRS_DEMO:
        creado = ahora - timedelta(days=dias, hours=2)
        cliente = usuarios[email]
        p = Pqrs(asunto=asunto, descripcion=descripcion, cliente_id=cliente.id, estado="abierto",
                 estado_ia="pendiente", creado_en=creado, actualizado_en=creado,
                 fecha_vencimiento=sumar_dias_habiles(creado, settings.dias_habiles_respuesta))
        db.add(p)
        db.flush()
        p.radicado = generar_radicado(p.id, creado)
        flujo.registrar(db, p, "creada", f"Solicitud radicada con el número {p.radicado}.",
                        usuario=cliente, visible_cliente=True, estado_nuevo="abierto")
        # Los datos demo se clasifican con reglas para que el arranque no dependa de Ollama.
        flujo.aplicar_clasificacion(db, p, clasificar(asunto, descripcion, usar_ia=False))
        db.flush()

        if estado != "abierto":
            empleado = next(
                (u for u in usuarios.values() if u.rol == "empleado" and u.area_id == p.area_id),
                usuarios["admin@demo-pqrs.co"],
            )
            flujo.cambiar_estado(db, p, "en_proceso", empleado, "Un asesor está revisando su solicitud.")
            if respuesta:
                flujo.registrar(db, p, "respuesta", respuesta, usuario=empleado, visible_cliente=True)
            if estado == "resuelto":
                flujo.cambiar_estado(db, p, "resuelto", empleado, None)
                p.resuelto_en = creado + timedelta(hours=20)

        # Fechas coherentes en la línea de tiempo de la demo
        minutos = [0, 1, 1, 180, 1080, 1200]
        for i, evento in enumerate(p.historial):
            evento.creado_en = creado + timedelta(minutes=minutos[min(i, len(minutos) - 1)])
    db.commit()
    log.info("Datos de demostración listos: %s usuarios, %s PQRS", len(USUARIOS_DEMO), len(PQRS_DEMO))
