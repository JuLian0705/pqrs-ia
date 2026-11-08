"""Hash de contraseñas (PBKDF2-SHA256, librería estándar) y tokens JWT."""
from __future__ import annotations
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
import jwt

from app.config import settings

ALGORITMO_JWT = "HS256"


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


def hash_password(password: str) -> str:
    sal = secrets.token_bytes(16)
    iteraciones = settings.password_iteraciones
    derivada = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), sal, iteraciones)
    return f"pbkdf2_sha256${iteraciones}${_b64(sal)}${_b64(derivada)}"


def verificar_password(password: str, guardado: str) -> bool:
    try:
        algoritmo, iteraciones, sal_b64, hash_b64 = guardado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        derivada = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), base64.b64decode(sal_b64), int(iteraciones)
        )
        return hmac.compare_digest(derivada, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


def crear_token(usuario_id: int, rol: str) -> str:
    ahora = datetime.now(timezone.utc)
    carga = {
        "sub": str(usuario_id),
        "rol": rol,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=settings.access_token_minutos),
    }
    return jwt.encode(carga, settings.secret_key, algorithm=ALGORITMO_JWT)


def leer_token(token: str) -> dict:
    """Lanza jwt.PyJWTError si el token es inválido o expiró."""
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITMO_JWT])
