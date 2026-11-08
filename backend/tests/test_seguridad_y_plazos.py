from __future__ import annotations

from datetime import datetime

import jwt
import pytest

from app.security import crear_token, hash_password, leer_token, verificar_password
from app.services.plazos import generar_radicado, sumar_dias_habiles


def test_hash_de_contrasena_no_guarda_texto_plano():
    h = hash_password("Clave1234")
    assert "Clave1234" not in h
    assert verificar_password("Clave1234", h)
    assert not verificar_password("otra", h)
    assert hash_password("Clave1234") != h  # sal aleatoria


def test_hash_corrupto_no_lanza_error():
    assert verificar_password("x", "basura") is False


def test_token_contiene_usuario_y_rol():
    carga = leer_token(crear_token(7, "empleado"))
    assert carga["sub"] == "7" and carga["rol"] == "empleado"


def test_token_firmado_con_otra_clave_es_rechazado():
    falso = jwt.encode({"sub": "1", "rol": "admin"}, "clave-del-atacante-de-32-caracteres!", algorithm="HS256")
    with pytest.raises(jwt.PyJWTError):
        leer_token(falso)


def test_dias_habiles_saltan_fines_de_semana():
    viernes = datetime(2026, 11, 6, 10, 0)
    assert sumar_dias_habiles(viernes, 1) == datetime(2026, 11, 9, 10, 0)  # lunes
    assert sumar_dias_habiles(viernes, 15).weekday() < 5
    assert (sumar_dias_habiles(viernes, 15) - viernes).days == 21  # 3 semanas


def test_formato_de_radicado():
    assert generar_radicado(42, datetime(2026, 11, 6)) == "PQRS-2026-000042"
