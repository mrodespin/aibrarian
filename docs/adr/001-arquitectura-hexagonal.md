# ADR-001: Arquitectura Hexagonal (Puertos y Adaptadores)

**Estado:** Aceptada
**Fecha:** Noviembre 2025

---

## Contexto

El TFM requiere implementar un sistema RAG que integra múltiples servicios externos (LLM, base de datos vectorial, procesadores de documentos) y múltiples fuentes de datos (PDFs, Notion). Se necesita una arquitectura que:

- Permita cambiar implementaciones sin modificar la lógica de negocio
- Facilite el testing con mocks y dobles de test
- Demuestre conocimientos de diseño de software a nivel de máster
- Sea mantenible y extensible a futuras fuentes de datos

## Alternativas evaluadas

### 1. MVC (Model-View-Controller)
- Patrón ampliamente conocido
- Tiende a crear controladores gordos con lógica acoplada a frameworks
- Dificultad para aislar la lógica de negocio de los servicios externos

### 2. Layered Architecture (capas)
- Simple y directo: Controller → Service → Repository
- Dependencias fluyen en una dirección
- Pero las capas tienden a filtrar abstracciones y crear acoplamiento vertical

### 3. Hexagonal Architecture (Puertos y Adaptadores)
- Lógica de negocio aislada en el centro (dominio)
- Dependencias apuntan hacia adentro (Dependency Inversion)
- Servicios externos son adaptadores intercambiables

## Decisión

**Hexagonal Architecture** por las siguientes razones:

1. **Testabilidad**: Los servicios (`RAGService`, `SyncService`) dependen de puertos abstractos (`LLMPort`, `VectorDBPort`, `DocumentProcessorPort`), permitiendo inyectar mocks en tests sin tocar servicios reales
2. **Extensibilidad**: Añadir Notion como fuente de datos solo requirió un nuevo adaptador (`NotionProcessorAdapter`) que implementa el mismo puerto `DocumentProcessorPort`
3. **Desacoplamiento**: Si mañana se cambia Ollama por OpenAI, solo se reemplaza `OllamaAdapter` sin tocar `RAGService`
4. **Valor académico**: Demuestra conocimiento de patrones de arquitectura empresarial (DDD, SOLID, Clean Architecture)

## Estructura resultante

```
api/app/
├── core/                    # Hexágono (lógica pura)
│   ├── domain/models.py     # Entidades: Document, Chunk, Query
│   ├── ports/               # Interfaces abstractas (ABC)
│   └── services/            # RAGService, SyncService
└── adapters/outbound/       # Implementaciones concretas
    ├── ollama_adapter.py
    ├── chromadb_adapter.py
    ├── pdf_processor_adapter.py
    └── notion_processor_adapter.py
```

## Consecuencias

**Positivas:**
- 66 tests unitarios posibles gracias a los mocks de puertos
- Notion se integró en ~1 día al reutilizar el pipeline existente
- El código del dominio no importa ninguna librería externa

**Negativas:**
- Mayor complejidad inicial vs un simple script monolítico
- Más archivos y abstracciones para un proyecto de una persona
- Curva de aprendizaje para quien no conozca el patrón
