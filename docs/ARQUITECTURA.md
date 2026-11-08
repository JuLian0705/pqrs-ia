# Arquitectura del prototipo

## 1. Vista de componentes

```mermaid
flowchart LR
    subgraph Navegador
        C[Ciudadano] --> FE
        E[Empleado / Admin] --> FE
        FE["Frontend React + Vite + Tailwind<br/>(SPA)"]
    end

    FE -- "HTTPS / JSON (JWT)" --> API

    subgraph Servidor
        API["API REST FastAPI<br/>auth · pqrs · gestión · métricas"]
        CL["Servicio de clasificación<br/>prompt + validación Pydantic"]
        RG["Clasificador de respaldo<br/>(reglas por palabras clave)"]
        DB[("PostgreSQL / SQLite<br/>usuarios · pqrs · historial")]
        API --> DB
        API -- "tarea en segundo plano" --> CL
        CL -- "si falla" --> RG
    end

    CL -- "POST /api/chat<br/>format = JSON schema" --> OL["Ollama<br/>modelo llama3.2:3b (local)"]
```

## 2. Secuencia: radicación y clasificación

```mermaid
sequenceDiagram
    actor Ciudadano
    participant FE as Frontend
    participant API as API FastAPI
    participant BD as Base de datos
    participant IA as Ollama (Llama)

    Ciudadano->>FE: Escribe asunto y descripción
    FE->>API: POST /api/pqrs (JWT)
    API->>BD: Guarda PQRS + radicado + evento "creada"
    API-->>FE: 201 Created (estado_ia = pendiente)
    Note over API: La respuesta es inmediata;<br/>la IA trabaja en segundo plano
    API->>IA: Prompt + texto delimitado + esquema JSON
    IA-->>API: {tipo, categoria, prioridad, resumen, justificacion}
    API->>API: Valida contra el catálogo · deriva el área · aplica salvaguardas
    API->>BD: Guarda clasificación + eventos "clasificada" y "asignada"
    loop cada 2 s mientras esté pendiente
        FE->>API: GET /api/pqrs/{id}
    end
    FE-->>Ciudadano: Tipo, área responsable y plazo de respuesta
```

## 3. Modelo entidad-relación

```mermaid
erDiagram
    AREAS ||--o{ USUARIOS : "agrupa empleados"
    AREAS ||--o{ PQRS : "es responsable de"
    USUARIOS ||--o{ PQRS : "radica (cliente)"
    USUARIOS ||--o{ PQRS : "gestiona (asignado)"
    PQRS ||--o{ HISTORIAL_PQRS : "registra"
    USUARIOS ||--o{ HISTORIAL_PQRS : "realiza"

    AREAS {
        int id PK
        string codigo UK
        string nombre
    }
    USUARIOS {
        int id PK
        string nombre
        string email UK
        string password_hash
        string rol "cliente | empleado | admin"
        int area_id FK
        bool activo
    }
    PQRS {
        int id PK
        string radicado UK
        string asunto
        text descripcion
        string tipo "P | Q | R | S"
        string categoria
        string prioridad "baja | media | alta | critica"
        text resumen
        string clasificado_por "ia | reglas | humano"
        string estado "abierto | en_proceso | resuelto"
        datetime fecha_vencimiento
        int cliente_id FK
        int asignado_a_id FK
        int area_id FK
    }
    HISTORIAL_PQRS {
        int id PK
        int pqrs_id FK
        int usuario_id FK
        string evento
        text detalle
        string estado_anterior
        string estado_nuevo
        bool visible_cliente
        datetime creado_en
    }
```

## 4. Máquina de estados de una PQRS

```mermaid
stateDiagram-v2
    [*] --> Abierto: radicación
    Abierto --> EnProceso: empleado toma el caso
    Abierto --> Resuelto: respuesta directa
    EnProceso --> Resuelto: respuesta al ciudadano (obligatoria)
    Resuelto --> EnProceso: reabrir
```

## 5. Decisiones de diseño

| Decisión | Por qué |
|---|---|
| El modelo solo elige de listas cerradas y el **backend** deriva el área desde la categoría | Una alucinación no puede enviar un caso a un área que no existe (riesgo #1 de la matriz). |
| Salida forzada con `format` (JSON schema) + validación Pydantic + 1 reintento | La respuesta siempre es parseable o se descarta (criterio de aceptación 3). |
| Clasificación en **segundo plano** | En CPU el modelo puede tardar varios segundos; el ciudadano recibe su radicado al instante. |
| **Clasificador por reglas** de respaldo | Si Ollama está apagado o el hardware no da (riesgo #2), ninguna PQRS queda sin clasificar. |
| **Salvaguarda de prioridad**: palabras como *tutela*, *fraude* o *riesgo* nunca quedan por debajo de "crítica" | Un error del modelo no puede esconder un caso urgente. |
| El texto del ciudadano va entre delimitadores y se le quitan las etiquetas | Mitiga la inyección de instrucciones (*prompt injection*). |
| El resumen oculta números largos (cédulas, tarjetas, teléfonos) | Minimiza datos personales visibles (Ley 1581 de 2012). |
| Historial con `visible_cliente` | Trazabilidad completa para auditoría; el ciudadano solo ve lo que le corresponde. |
| Corrección humana registrada como evento | La IA asiste, el humano decide; además permite medir la tasa de error real del modelo. |
