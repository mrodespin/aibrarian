# ADR-006: Docker para servicios, Ollama nativo

**Estado:** Aceptada
**Fecha:** Febrero 2026
**Supersede:** Decisión anterior de ejecutar todo en Docker (Modo A/B)

---

## Contexto

Inicialmente el proyecto soportaba dos modos de instalación:
- **Modo A**: Todo en Docker (Ollama + ChromaDB + API)
- **Modo B**: Ollama nativo + ChromaDB en Docker + API local

Esta dualidad generaba problemas:
- Configuración de `.env` diferente según el modo (OLLAMA_BASE_URL)
- Scripts de setup complejos con selección de modo
- Documentación duplicada para cada modo
- Errores recurrentes por configuración incorrecta

Se decidió simplificar a una única configuración.

## Alternativas evaluadas

### 1. Todo en Docker (antiguo Modo A)
- Reproducible y aislado
- **Ollama en Docker no tiene acceso a GPU en macOS** (Metal no disponible)
- Inferencia ~10x más lenta (solo CPU)
- Más simple de documentar (un solo `docker-compose up`)

### 2. Todo nativo (sin Docker)
- Máximo rendimiento
- ChromaDB requiere instalación manual o pip
- Sin persistencia automatizada
- Más difícil de reproducir

### 3. Híbrido: ChromaDB + API en Docker, Ollama nativo
- Ollama aprovecha GPU Metal (~10x más rápido)
- ChromaDB y API en Docker con `docker-compose up -d`
- Un solo modo = una sola configuración
- La API en Docker usa `host.docker.internal` para conectar con Ollama en el host

## Decisión

**ChromaDB + API en Docker, Ollama nativo** por:

1. **Rendimiento**: Ollama nativo con GPU Metal es ~10x más rápido que en Docker (CPU)
2. **Simplicidad**: Un solo modo de instalación, una sola documentación
3. **Reproducibilidad**: `docker-compose up -d` levanta ChromaDB + API consistentemente
4. **Facilidad de evaluación**: El evaluador del TFM solo necesita:
   - Instalar Ollama (`brew install ollama`)
   - Ejecutar `docker-compose up -d`
   - Ejecutar `cd frontend && npm run dev`

### Arquitectura de red

```
┌─────────────────────────────────────────────┐
│              macOS Host                      │
│                                             │
│  ┌─────────┐                                │
│  │ Ollama  │ :11434 (GPU Metal)             │
│  └────▲────┘                                │
│       │ host.docker.internal                │
│  ┌────┼────────────────────────────┐        │
│  │ Docker                          │        │
│  │  ┌──────┐    ┌──────────┐      │        │
│  │  │ API  │───▶│ ChromaDB │      │        │
│  │  │:8000 │    │  :8000   │      │        │
│  │  └──────┘    └──────────┘      │        │
│  └─────────────────────────────────┘        │
│       │                                     │
│  ┌────▼────┐                                │
│  │Frontend │ :5173 (npm run dev)            │
│  └─────────┘                                │
└─────────────────────────────────────────────┘
```

## Consecuencias

**Positivas:**
- Eliminado el sistema de modos (A/B) y toda su complejidad
- Scripts de setup reducidos de 857 a 446 líneas
- Un solo `.env.example` sin condicionales
- Evaluador puede instalar en < 10 minutos

**Negativas:**
- Requiere macOS con Apple Silicon para rendimiento óptimo de Ollama
- La API en Docker tiene latencia de red mínima al conectar con Ollama vía `host.docker.internal`
- Si Ollama no está corriendo, `docker-compose up` arranca pero la API reporta Ollama como no disponible
