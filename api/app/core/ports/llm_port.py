# /api/app/core/ports/llm_port.py
"""
Puerto (Interfaz) para operaciones del Modelo de Lenguaje - TFM Bibliotecario-IA

Este archivo define el CONTRATO que debe cumplir cualquier LLM (Large Language Model).
Es una interfaz abstracta que permite cambiar de Ollama a OpenAI sin modificar servicios.

¿Qué es un LLM?
- Large Language Model = Modelo de Lenguaje Grande
- Ejemplos: GPT-4, Llama, Mistral, Claude
- Puede entender y generar texto en lenguaje natural

¿Por qué dos tipos de operaciones?
1. generate_response: Usa modelo conversacional (llama3.2) para generar texto
2. generate_embedding: Usa modelo de embeddings (nomic-embed-text) para vectorizar

Son modelos DIFERENTES aunque ambos se accedan por Ollama.

Equivalente en TypeScript:
    interface LLMPort {
        generateResponse(prompt: string, context?: string): Promise<string>;
        generateEmbedding(text: string): Promise<number[]>;
        generateEmbeddingsBatch(texts: string[]): Promise<number[][]>;
        isAvailable(): Promise<boolean>;
        getModelInfo(): Record<string, any>;
    }

La implementación real está en: /adapters/outbound/ollama_adapter.py
"""

# ============================================================================
# IMPORTS
# ============================================================================
# ABC permite crear clases abstractas (interfaces)
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


# ============================================================================
# INTERFAZ DEL MODELO DE LENGUAJE
# ============================================================================
class LLMPort(ABC):
    """
    Interfaz abstracta para operaciones del Modelo de Lenguaje.

    El sistema RAG necesita DOS capacidades del LLM:

    1. GENERACIÓN DE TEXTO (generate_response):
       - Recibe: pregunta + contexto (chunks relevantes)
       - Devuelve: respuesta en lenguaje natural
       - Modelo usado: llama3.2 (conversacional)

    2. GENERACIÓN DE EMBEDDINGS (generate_embedding):
       - Recibe: texto a vectorizar
       - Devuelve: vector numérico [0.1, -0.2, 0.3, ...]
       - Modelo usado: nomic-embed-text (especializado en embeddings)

    Flujo en el sistema RAG:
        Usuario: "¿Qué es machine learning?"
            ↓
        generate_embedding("¿Qué es machine learning?")
            ↓
        Vector → ChromaDB → chunks relevantes
            ↓
        generate_response(prompt=pregunta, context=chunks)
            ↓
        "Machine learning es una rama de la IA..."

    Nota: ABC = Abstract Base Class (no se puede instanciar directamente)
    """

    @abstractmethod
    async def generate_response(
        self,
        prompt: str,
        context: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Genera una respuesta de texto usando el modelo de lenguaje.

        ESTE MÉTODO ES EL "CEREBRO" DEL CHATBOT.

        ¿Cómo funciona internamente?
        1. Se construye un prompt con la pregunta + contexto
        2. Se envía al modelo (Ollama/llama3.2)
        3. El modelo genera tokens uno a uno hasta completar
        4. Se devuelve la respuesta completa

        Args:
            prompt: Pregunta del usuario en lenguaje natural
                   Ejemplo: "¿Qué es machine learning?"

            context: Contexto opcional (chunks recuperados de ChromaDB)
                    Ejemplo: "Según el documento X, machine learning es..."
                    El contexto se inyecta en el prompt para dar información

            max_tokens: Límite de tokens en la respuesta (None = sin límite)
                       Un token ≈ 0.75 palabras en español
                       Ejemplo: max_tokens=500 ≈ 375 palabras

            temperature: Controla la "creatividad" del modelo (0.0 a 1.0)
                        - 0.0 = determinista (siempre la misma respuesta)
                        - 0.7 = balance entre coherencia y variedad (default)
                        - 1.0 = muy creativo/aleatorio
                        Para Q&A técnico, mejor usar 0.3-0.5

            **kwargs: Parámetros adicionales específicos del modelo
                     Es como ...rest en JavaScript
                     Ejemplo: top_p=0.9, repetition_penalty=1.1

        Returns:
            str: Respuesta generada por el modelo

        Ejemplo de uso:
            response = await llm.generate_response(
                prompt="¿Qué es RAG?",
                context="RAG significa Retrieval-Augmented Generation...",
                temperature=0.3  # Bajo para respuestas más precisas
            )
            # response = "RAG (Retrieval-Augmented Generation) es una técnica..."
        """
        pass  # La implementación real está en ollama_adapter.py

    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Genera un vector embedding para un texto.

        ¿Qué es un embedding?
        - Representación numérica del "significado" de un texto
        - Vector de ~768 números flotantes
        - Textos similares → vectores cercanos en el espacio

        ¿Para qué sirve?
        - Convertir la pregunta del usuario en vector
        - Ese vector se compara con los chunks en ChromaDB
        - Se encuentran los chunks más "semánticamente similares"

        Args:
            text: Texto a convertir en vector
                 Ejemplo: "¿Cómo funciona la autenticación?"

        Returns:
            List[float]: Vector de ~768 números
                        Ejemplo: [0.123, -0.456, 0.789, ...]

        Ejemplo:
            # Vectorizar una pregunta
            embedding = await llm.generate_embedding("¿Qué es Docker?")
            # embedding = [0.1, -0.2, 0.3, ...] (768 números)

            # Este vector se envía a ChromaDB para buscar chunks similares

        Modelo usado: nomic-embed-text (especializado en embeddings)
        Dimensiones: 768 (fijo para este modelo)
        """
        pass

    @abstractmethod
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Genera embeddings para múltiples textos en lote.

        ¿Por qué batch en lugar de uno por uno?
        - Eficiencia: una llamada en lugar de N llamadas
        - Menor latencia total
        - Cuando ingestas un PDF de 100 chunks, es MUY ineficiente
          hacer 100 llamadas individuales

        Args:
            texts: Lista de textos a vectorizar
                  Ejemplo: ["Chunk 1 del PDF...", "Chunk 2 del PDF...", ...]

        Returns:
            List[List[float]]: Lista de vectores, uno por cada texto
                              Mantiene el mismo orden que la entrada

        Ejemplo:
            chunks = ["Texto chunk 1", "Texto chunk 2", "Texto chunk 3"]
            embeddings = await llm.generate_embeddings_batch(chunks)
            # embeddings[0] corresponde a chunks[0]
            # embeddings[1] corresponde a chunks[1]
            # etc.

        Nota: Internamente puede procesar en paralelo o en mini-batches
              según las capacidades del modelo/hardware
        """
        pass

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Verifica si el servicio LLM está disponible y respondiendo.

        Útil para:
        - Health checks de la API (endpoint /health)
        - Verificar que Ollama está corriendo antes de procesar
        - Mostrar estado al usuario en el frontend

        Returns:
            bool: True si el servicio está disponible

        Ejemplo:
            if not await llm.is_available():
                raise ServiceUnavailableError("Ollama no está corriendo")

        Implementación típica:
        - Intenta hacer una llamada simple al modelo
        - Si responde en < 5 segundos → True
        - Si hay timeout o error → False
        """
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """
        Obtiene información sobre el modelo actual.

        Nota: Este método NO es async (sin await) porque la info
              típicamente está cacheada en memoria.

        Returns:
            Dict con información del modelo:
            {
                "model_name": "llama3.2",
                "embedding_model": "nomic-embed-text",
                "embedding_dimensions": 768,
                "provider": "ollama",
                "base_url": "http://localhost:11434"
            }

        Útil para:
        - Endpoint /info de la API
        - Debugging ("¿qué modelo estoy usando?")
        - Logging y monitoreo
        """
        pass
