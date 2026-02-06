# ADR-002: Ollama nativo en macOS para LLM local

**Estado:** Aceptada
**Fecha:** Noviembre 2025

---

## Contexto

El sistema RAG necesita un modelo de lenguaje (LLM) para dos tareas:
- **Generación de embeddings**: Convertir texto en vectores para búsqueda semántica
- **Generación de respuestas**: Responder preguntas basándose en contexto recuperado

El TFM tiene un requisito implícito de **privacidad**: los datos del usuario no deben salir de la máquina local. Además, el entorno de desarrollo es macOS con Apple Silicon.

## Alternativas evaluadas

### 1. OpenAI API (GPT-4, text-embedding-ada-002)
- Mejor calidad de respuestas
- Requiere conexión a internet y API key de pago
- **Los datos salen de la máquina** (viola requisito de privacidad)
- Dependencia de un servicio externo

### 2. Ollama en Docker
- Aislamiento y reproducibilidad
- **No tiene acceso a GPU en macOS** (Docker no expone Metal)
- Inferencia ~10x más lenta que nativo (solo CPU)
- Mayor consumo de memoria

### 3. Ollama nativo en macOS
- Acceso directo a **GPU Apple Silicon (Metal)**
- Inferencia rápida (~10x vs Docker/CPU)
- Instalación simple con Homebrew
- Datos 100% locales

## Decisión

**Ollama nativo en macOS** por:

1. **Privacidad**: Los datos nunca salen de la máquina. No hay API keys de terceros, no hay llamadas a APIs externas
2. **Rendimiento**: Apple Silicon con Metal proporciona inferencia rápida para un LLM de 3B parámetros (llama3.2)
3. **Simplicidad**: `brew install ollama && ollama pull llama3.2` vs configurar API keys y gestionar costes
4. **Independencia**: Sin dependencia de servicios cloud ni costes recurrentes

### Modelos elegidos

| Modelo | Tarea | Tamaño | Justificación |
|--------|-------|--------|---------------|
| `llama3.2` | Generación de respuestas | ~2GB | Buen equilibrio calidad/velocidad para 3B params |
| `nomic-embed-text` | Embeddings | ~275MB | 768 dimensiones, optimizado para búsqueda semántica |

## Consecuencias

**Positivas:**
- Privacidad total de los datos
- Sin costes de API
- Respuestas en ~2-5 segundos con Apple Silicon
- Funciona offline

**Negativas:**
- Calidad de respuestas inferior a GPT-4 (pero suficiente para el caso de uso)
- Requiere macOS con Apple Silicon para rendimiento óptimo
- El usuario debe descargar ~2.3GB de modelos en la primera instalación
