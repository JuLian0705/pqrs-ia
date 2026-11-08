"""Modelo relacional: áreas, usuarios, PQRS e historial (trazabilidad)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, ahora_utc


class Area(Base):
    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(100))


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20), default="cliente")  # cliente | empleado | admin
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)

    area: Mapped[Area | None] = relationship()


class Pqrs(Base):
    __tablename__ = "pqrs"

    id: Mapped[int] = mapped_column(primary_key=True)
    radicado: Mapped[str | None] = mapped_column(String(30), unique=True, index=True, nullable=True)
    asunto: Mapped[str] = mapped_column(String(150))
    descripcion: Mapped[str] = mapped_column(Text)
    canal: Mapped[str] = mapped_column(String(20), default="web")
    cliente_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)

    # Resultado de la clasificación automática
    estado_ia: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | completada
    tipo: Mapped[str | None] = mapped_column(String(1), nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prioridad: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    resumen: Mapped[str | None] = mapped_column(Text, nullable=True)
    justificacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    clasificado_por: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ia | reglas | humano
    modelo_ia: Mapped[str | None] = mapped_column(String(60), nullable=True)
    duracion_ia_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_ia: Mapped[str | None] = mapped_column(Text, nullable=True)
    area_id: Mapped[int | None] = mapped_column(ForeignKey("areas.id"), nullable=True, index=True)

    # Gestión humana
    estado: Mapped[str] = mapped_column(String(20), default="abierto", index=True)
    asignado_a_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_vencimiento: Mapped[datetime] = mapped_column(DateTime)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, index=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, onupdate=ahora_utc)
    resuelto_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cliente: Mapped[Usuario] = relationship(foreign_keys=[cliente_id])
    asignado_a: Mapped[Usuario | None] = relationship(foreign_keys=[asignado_a_id])
    area: Mapped[Area | None] = relationship()
    historial: Mapped[list[HistorialPqrs]] = relationship(
        back_populates="pqrs", order_by="HistorialPqrs.id", cascade="all, delete-orphan"
    )


class HistorialPqrs(Base):
    """Cada cambio queda registrado: quién, qué, cuándo y si el cliente lo ve."""

    __tablename__ = "historial_pqrs"

    id: Mapped[int] = mapped_column(primary_key=True)
    pqrs_id: Mapped[int] = mapped_column(ForeignKey("pqrs.id"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)  # None = sistema
    evento: Mapped[str] = mapped_column(String(30))
    # creada | clasificada | estado | asignada | respuesta | nota | reclasificada
    detalle: Mapped[str] = mapped_column(Text, default="")
    estado_anterior: Mapped[str | None] = mapped_column(String(20), nullable=True)
    estado_nuevo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    visible_cliente: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)

    pqrs: Mapped[Pqrs] = relationship(back_populates="historial")
    usuario: Mapped[Usuario | None] = relationship()
