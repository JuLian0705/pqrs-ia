"""Catálogo cerrado del dominio PQRS.

La IA solo puede elegir valores de estas listas. El área responsable NO la
decide el modelo: se deriva de la categoría con una tabla fija, así una
alucinación del LLM nunca puede enviar un caso a un área inexistente.
"""
from __future__ import annotations

TIPOS: dict[str, str] = {
    "P": "Petición",
    "Q": "Queja",
    "R": "Reclamo",
    "S": "Sugerencia",
}

TIPOS_DESCRIPCION: dict[str, str] = {
    "P": "Solicita información, un documento, un trámite o un servicio.",
    "Q": "Expresa inconformidad con la conducta o atención de una persona de la organización.",
    "R": "Exige corregir una falla en un producto o servicio (cobros, entregas, garantías) y espera una solución.",
    "S": "Propone una idea o mejora; no reporta un problema propio.",
}

CATEGORIAS: dict[str, str] = {
    "facturacion": "Facturación y pagos",
    "soporte_tecnico": "Soporte técnico",
    "entregas": "Entregas y logística",
    "calidad_producto": "Calidad del producto o servicio",
    "atencion_servicio": "Atención y servicio al cliente",
    "datos_personales": "Datos personales y privacidad",
    "otro": "Otro",
}

CATEGORIAS_DESCRIPCION: dict[str, str] = {
    "facturacion": "cobros, facturas, pagos, reembolsos, tarifas, cartera",
    "soporte_tecnico": "fallas de la plataforma, app, internet, contraseñas, errores de sistema",
    "entregas": "envíos, pedidos retrasados, domicilios, paquetes perdidos o dañados en transporte",
    "calidad_producto": "producto defectuoso, garantía, servicio prestado con mala calidad",
    "atencion_servicio": "trato del personal, tiempos de espera, canales de atención",
    "datos_personales": "uso de datos, habeas data, eliminar o actualizar información personal",
    "otro": "cualquier tema que no encaje claramente en las anteriores",
}

AREAS: dict[str, str] = {
    "atencion_cliente": "Atención al Cliente",
    "facturacion_cartera": "Facturación y Cartera",
    "soporte_tecnico": "Soporte Técnico",
    "logistica": "Logística",
    "calidad": "Calidad",
    "juridica": "Jurídica y Protección de Datos",
}

CATEGORIA_A_AREA: dict[str, str] = {
    "facturacion": "facturacion_cartera",
    "soporte_tecnico": "soporte_tecnico",
    "entregas": "logistica",
    "calidad_producto": "calidad",
    "atencion_servicio": "atencion_cliente",
    "datos_personales": "juridica",
    "otro": "atencion_cliente",
}

PRIORIDADES: dict[str, str] = {
    "baja": "Baja",
    "media": "Media",
    "alta": "Alta",
    "critica": "Crítica",
}

# Orden para ordenar bandejas (mayor número = más urgente)
PRIORIDAD_PESO: dict[str, int] = {"baja": 1, "media": 2, "alta": 3, "critica": 4}

ESTADOS: dict[str, str] = {
    "abierto": "Abierto",
    "en_proceso": "En proceso",
    "resuelto": "Resuelto",
}

# Transiciones de estado permitidas (máquina de estados)
TRANSICIONES: dict[str, set[str]] = {
    "abierto": {"en_proceso", "resuelto"},
    "en_proceso": {"resuelto"},
    "resuelto": {"en_proceso"},  # reabrir
}

ROLES = ("cliente", "empleado", "admin")


def area_para_categoria(categoria: str) -> str:
    return CATEGORIA_A_AREA.get(categoria, "atencion_cliente")
