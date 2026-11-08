"""Asistente de redacción de PQRS: chat con Llama (vía Ollama) que ayuda al
ciudadano a revisar y mejorar su texto ANTES de radicarlo.

- La respuesta llega en streaming (palabra por palabra), como un chat.
- No guarda las conversaciones ni registra su contenido en los logs.
- Si Ollama no está disponible, responde con una revisión básica por reglas.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Iterator
from typing import Literal
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.deps import Cliente
from app.services import catalogo
from app.services.clasificador import clasificar_por_reglas, keep_alive_ollama

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/asistente", tags=["Asistente IA"])

MAX_MENSAJES = 12  # se envía al modelo solo la parte reciente de la conversación

PROMPT_ASISTENTE = """Eres el Asistente de redacción de PQRS de una plataforma de atención al ciudadano en Colombia.
Ayudas a las personas a escribir bien sus peticiones, quejas, reclamos y sugerencias ANTES de radicarlas.

Reglas:
- Responde siempre en español claro, cordial y breve (máximo 150 palabras, sin contar el texto mejorado).
- Solo hablas de cómo redactar o entender una PQRS. Si te preguntan otra cosa, di con amabilidad que solo ayudas con PQRS.
- No inventes datos (fechas, números de factura, nombres, valores). Si faltan, pídelos o deja un espacio como [fecha] o [número de factura].
- El plazo general de respuesta es de 15 días hábiles (Ley 1755 de 2015). No prometas resultados ni otros plazos.
- No das la respuesta oficial del caso: eso lo hace el equipo de atención.
- Recuerda no incluir números de tarjeta, contraseñas ni datos sensibles.

Tipos de PQRS:
- Petición: pide información, un documento, un trámite o un servicio.
- Queja: inconformidad con la conducta o la atención de una persona de la organización.
- Reclamo: exige corregir una falla en un producto o servicio (cobros, entregas, garantías).
- Sugerencia: propone una mejora.

Cuando el usuario comparta el texto de su PQRS:
1. En una frase, di qué tipo parece y por qué.
2. En viñetas cortas, señala lo que falta o se puede mejorar: qué pasó, cuándo, datos de referencia (factura, pedido, cuenta) y qué solución espera.
3. Escribe una versión mejorada, en primera persona, respetuosa y concreta, así:
TEXTO MEJORADO:
(el texto aquí)
FIN"""


class Mensaje(BaseModel):
    rol: Literal["usuario", "asistente"]
    texto: str = Field(min_length=1, max_length=4000)


class ChatIn(BaseModel):
    mensajes: list[Mensaje] = Field(min_length=1, max_length=40)


def _stream_ollama(mensajes: list[dict]) -> Iterator[str]:
    """Pide la respuesta a Ollama en modo streaming y la entrega por trozos."""
    cuerpo = {
        "model": settings.ollama_modelo,
        "messages": mensajes,
        "stream": True,
        "options": {"temperature": 0.4, "num_ctx": 4096, "num_predict": settings.ollama_max_tokens_asistente},
        "keep_alive": keep_alive_ollama(),
    }
    peticion = urllib.request.Request(
        f"{settings.ollama_url.rstrip('/')}/api/chat",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(peticion, timeout=settings.ollama_timeout_s) as resp:
        for linea in resp:
            if not linea.strip():
                continue
            dato = json.loads(linea)
            if dato.get("error"):
                raise RuntimeError(dato["error"])
            trozo = (dato.get("message") or {}).get("content", "")
            if trozo:
                yield trozo
            if dato.get("done"):
                break


def respuesta_de_respaldo(texto_usuario: str) -> str:
    """Revisión básica cuando la IA no está disponible."""
    partes = ["En este momento el asistente de IA no está disponible, pero te dejo una revisión rápida:\n"]
    if len(texto_usuario.strip()) >= 20:
        sugerido = clasificar_por_reglas(texto_usuario[:150], texto_usuario)
        articulo = "un" if sugerido.tipo == "R" else "una"
        partes.append(f"- Por lo que escribes, parece {articulo} **{catalogo.TIPOS[sugerido.tipo].lower()}**.")
    partes += [
        "- Cuenta **qué pasó** y **cuándo** (una fecha aproximada sirve).",
        "- Agrega **datos de referencia**: número de factura, pedido o cuenta.",
        "- Di **qué solución esperas**: reembolso, cambio, explicación, etc.",
        "- No incluyas números de tarjeta ni contraseñas.",
        "\nCon eso tu PQRS queda lista para radicar.",
    ]
    return "\n".join(partes)


def generar_respuesta(mensajes: list[Mensaje]) -> Iterator[str]:
    recientes = mensajes[-MAX_MENSAJES:]
    para_modelo = [{"role": "system", "content": PROMPT_ASISTENTE}] + [
        {"role": "user" if m.rol == "usuario" else "assistant", "content": m.texto} for m in recientes
    ]
    ultimo_del_usuario = next((m.texto for m in reversed(recientes) if m.rol == "usuario"), "")

    enviado = False
    try:
        if not settings.ia_habilitada:
            raise RuntimeError("IA deshabilitada")
        for trozo in _stream_ollama(para_modelo):
            enviado = True
            yield trozo
    except Exception as e:  # noqa: BLE001 - cualquier fallo de la IA activa el respaldo
        log.warning("Asistente sin IA (%s)", type(e).__name__)  # sin contenido del usuario en logs
        if enviado:
            yield "\n\n_(La respuesta se interrumpió. Intenta de nuevo.)_"
        else:
            yield respuesta_de_respaldo(ultimo_del_usuario)


@router.post("/chat")
def chat(datos: ChatIn, usuario: Cliente) -> StreamingResponse:
    """Responde en streaming (texto plano) a la conversación del ciudadano."""
    return StreamingResponse(
        generar_respuesta(datos.mensajes),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )