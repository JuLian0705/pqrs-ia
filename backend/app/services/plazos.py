"""Cálculo de plazos de respuesta y número de radicado."""
from __future__ import annotations

from datetime import datetime, timedelta


def sumar_dias_habiles(desde: datetime, dias: int) -> datetime:
    """Suma días hábiles (lunes a viernes).

    Limitación conocida del prototipo: no descuenta los festivos colombianos.
    """
    fecha = desde
    restantes = dias
    while restantes > 0:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5:
            restantes -= 1
    return fecha


def generar_radicado(pqrs_id: int, fecha: datetime) -> str:
    return f"PQRS-{fecha.year}-{pqrs_id:06d}"
