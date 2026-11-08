from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DB, UsuarioActual
from app.models import Usuario
from app.schemas import LoginIn, RegistroIn, TokenOut, UsuarioOut
from app.security import crear_token, hash_password, verificar_password

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])


def _token(usuario: Usuario) -> TokenOut:
    return TokenOut(
        access_token=crear_token(usuario.id, usuario.rol),
        usuario=UsuarioOut.model_validate(usuario),
    )


@router.post("/registro", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def registro(datos: RegistroIn, db: DB) -> TokenOut:
    """Crea una cuenta de ciudadano (rol cliente)."""
    email = datos.email.lower()
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese correo")
    usuario = Usuario(nombre=datos.nombre, email=email, password_hash=hash_password(datos.password), rol="cliente")
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return _token(usuario)


@router.post("/login", response_model=TokenOut)
def login(datos: LoginIn, db: DB) -> TokenOut:
    usuario = db.scalar(select(Usuario).where(Usuario.email == datos.email.strip().lower()))
    if usuario is None or not usuario.activo or not verificar_password(datos.password, usuario.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos")
    return _token(usuario)


@router.get("/me", response_model=UsuarioOut)
def yo(usuario: UsuarioActual) -> Usuario:
    return usuario
