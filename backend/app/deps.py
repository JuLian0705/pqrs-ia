"""Dependencias de FastAPI: sesión de BD, usuario autenticado y control de roles."""
from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario
from app.security import leer_token

_bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]


def _no_autenticado(detalle: str = "Sesión inválida o expirada") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalle,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_usuario_actual(
    db: DB,
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Usuario:
    if credenciales is None:
        raise _no_autenticado("Debes iniciar sesión")
    try:
        carga = leer_token(credenciales.credentials)
        usuario = db.get(Usuario, int(carga["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _no_autenticado() from None
    if usuario is None or not usuario.activo:
        raise _no_autenticado()
    return usuario


UsuarioActual = Annotated[Usuario, Depends(get_usuario_actual)]


def requiere_roles(*roles: str):
    def _verificar(usuario: UsuarioActual) -> Usuario:
        if usuario.rol not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permiso para esta acción")
        return usuario

    return _verificar


Cliente = Annotated[Usuario, Depends(requiere_roles("cliente"))]
Personal = Annotated[Usuario, Depends(requiere_roles("empleado", "admin"))]
Admin = Annotated[Usuario, Depends(requiere_roles("admin"))]
