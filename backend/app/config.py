"""Configuración centralizada leída de variables de entorno.

Se usa solo la librería estándar para que el módulo de clasificación
pueda ejecutarse (y probarse) sin dependencias adicionales.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _cargar_env(ruta: Path) -> None:
    """Lee un archivo .env simple (CLAVE=valor). Las variables ya definidas tienen prioridad."""
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env(Path(__file__).resolve().parent.parent / ".env")


def _bool(nombre: str, defecto: bool) -> bool:
    valor = os.getenv(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def _lista(nombre: str, defecto: str) -> list[str]:
    return [v.strip() for v in os.getenv(nombre, defecto).split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    app_nombre: str = "Sistema Inteligente de Gestión de PQRS"
    app_version: str = "1.0.0-prototipo"

    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./pqrs.db"))

    # Seguridad
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", "cambia-esta-clave-secreta-en-produccion-2026"))
    access_token_minutos: int = field(default_factory=lambda: int(os.getenv("ACCESS_TOKEN_MINUTOS", "480")))
    password_iteraciones: int = field(default_factory=lambda: int(os.getenv("PASSWORD_ITERACIONES", "600000")))

    # Inteligencia artificial (Llama vía Ollama)
    ia_habilitada: bool = field(default_factory=lambda: _bool("IA_HABILITADA", True))
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))
   # ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "https://g6x4777s-11434.use.devtunnels.ms/"))
    ollama_modelo: str = field(default_factory=lambda: os.getenv("OLLAMA_MODELO", "llama3.2:3b"))
    ollama_timeout_s: float = field(default_factory=lambda: float(os.getenv("OLLAMA_TIMEOUT_S", "90")))
    ollama_reintentos: int = field(default_factory=lambda: int(os.getenv("OLLAMA_REINTENTOS", "1")))
    # Rendimiento: "-1" = el modelo se queda cargado en memoria (no se recarga en cada uso)
    ollama_keep_alive: str = field(default_factory=lambda: os.getenv("OLLAMA_KEEP_ALIVE", "-1"))
    # Tope de palabras (tokens) que genera el modelo: menos tokens = respuesta más rápida
    ollama_max_tokens_clasificacion: int = field(
        default_factory=lambda: int(os.getenv("OLLAMA_MAX_TOKENS_CLASIFICACION", "320"))
    )
    ollama_max_tokens_asistente: int = field(
        default_factory=lambda: int(os.getenv("OLLAMA_MAX_TOKENS_ASISTENTE", "450"))
    )
    precalentar_modelo: bool = field(default_factory=lambda: _bool("PRECALENTAR_MODELO", True))

    # Negocio: plazo de respuesta en días hábiles (Ley 1755 de 2015, regla general)
    dias_habiles_respuesta: int = field(default_factory=lambda: int(os.getenv("DIAS_HABILES_RESPUESTA", "15")))

    # Arranque
    seed_demo: bool = field(default_factory=lambda: _bool("SEED_DEMO", True))
    cors_origenes: list[str] = field(
        default_factory=lambda: _lista("CORS_ORIGENES", "http://localhost:5173,http://localhost:8080")
        #default_factory=lambda: _lista("CORS_ORIGENES", "https://g6x4777s-11434.use.devtunnels.ms/")
    )


settings = Settings()