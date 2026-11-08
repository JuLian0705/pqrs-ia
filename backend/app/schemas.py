"""Contratos de entrada y salida de la API (validados con Pydantic)."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, PlainSerializer, field_validator


def _iso_utc(valor: datetime) -> str:
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# Las fechas se guardan en UTC sin zona; se exponen con "Z" para que el
# navegador las convierta bien a la hora de Colombia.
FechaUTC = Annotated[datetime, PlainSerializer(_iso_utc, return_type=str)]

EstadoLit = Literal["abierto", "en_proceso", "resuelto"]
TipoLit = Literal["P", "Q", "R", "S"]
CategoriaLit = Literal[
    "facturacion", "soporte_tecnico", "entregas", "calidad_producto", "atencion_servicio", "datos_personales", "otro"
]
PrioridadLit = Literal["baja", "media", "alta", "critica"]


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _limpiar(v: object) -> object:
    return " ".join(v.split()) if isinstance(v, str) else v


# ---------------------------------------------------------------- Autenticación
class RegistroIn(BaseModel):
    nombre: str = Field(min_length=3, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("nombre", mode="before")
    @classmethod
    def _nombre(cls, v: object) -> object:
        return _limpiar(v)

    @field_validator("password")
    @classmethod
    def _password_segura(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("La contraseña debe tener letras y números")
        return v


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=128)


class AreaOut(_Base):
    id: int
    codigo: str
    nombre: str


class UsuarioOut(_Base):
    id: int
    nombre: str
    email: str
    rol: str
    area: AreaOut | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut


# ---------------------------------------------------------------- PQRS
class PqrsCrear(BaseModel):
    asunto: str = Field(min_length=5, max_length=150)
    descripcion: str = Field(min_length=20, max_length=4000)

    @field_validator("asunto", mode="before")
    @classmethod
    def _asunto(cls, v: object) -> object:
        return _limpiar(v)

    @field_validator("descripcion", mode="before")
    @classmethod
    def _descripcion(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class HistorialOut(BaseModel):
    id: int
    evento: str
    detalle: str
    estado_anterior: str | None = None
    estado_nuevo: str | None = None
    visible_cliente: bool
    autor: str
    creado_en: FechaUTC


class PqrsClienteOut(BaseModel):
    """Lo que ve el ciudadano: sin prioridad ni datos internos."""

    id: int
    radicado: str
    asunto: str
    descripcion: str
    tipo: str | None
    tipo_nombre: str | None
    area_nombre: str | None
    estado: str
    estado_ia: str
    fecha_vencimiento: FechaUTC
    creado_en: FechaUTC
    actualizado_en: FechaUTC
    resuelto_en: FechaUTC | None
    historial: list[HistorialOut] = []


class PqrsListaOut(BaseModel):
    """Fila de la bandeja de gestión."""

    id: int
    radicado: str
    asunto: str
    tipo: str | None
    categoria: str | None
    prioridad: str | None
    estado: str
    estado_ia: str
    clasificado_por: str | None
    area_nombre: str | None
    cliente_nombre: str
    asignado_a_nombre: str | None
    fecha_vencimiento: FechaUTC
    vencida: bool
    creado_en: FechaUTC


class PqrsDetalleOut(PqrsListaOut):
    descripcion: str
    resumen: str | None
    justificacion: str | None
    modelo_ia: str | None
    duracion_ia_ms: int | None
    error_ia: str | None
    area_id: int | None
    asignado_a_id: int | None
    cliente_email: str
    actualizado_en: FechaUTC
    resuelto_en: FechaUTC | None
    historial: list[HistorialOut] = []


class CambioEstadoIn(BaseModel):
    estado: EstadoLit
    comentario: str | None = Field(default=None, max_length=3000)


class ComentarioIn(BaseModel):
    mensaje: str = Field(min_length=2, max_length=3000)
    visible_cliente: bool = True


class ReclasificacionIn(BaseModel):
    tipo: TipoLit
    categoria: CategoriaLit
    prioridad: PrioridadLit
    motivo: str | None = Field(default=None, max_length=500)
