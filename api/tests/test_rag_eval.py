# /api/tests/test_rag_eval.py
"""
Evaluación de calidad del RAG con RAGAS.

Este test NO es un test de correctitud funcional (eso ya lo cubren
test_rag_service.py y test_integration.py) — mide CALIDAD de las
respuestas con métricas objetivas de RAGAS:

- faithfulness: ¿la respuesta se basa solo en el contexto recuperado,
  o el LLM está fabricando/alucinando información?
- answer_relevancy: ¿la respuesta es realmente relevante a la pregunta?
- context_precision (sin referencia): ¿los chunks recuperados son
  relevantes, o es ruido que solo confunde al LLM?

Sirve como comprobación cuantitativa del fix del umbral de relevancia en
RAGService (ver settings.min_relevance_score / _filter_by_relevance): el
dataset incluye tanto preguntas dentro del alcance del documento de
prueba como preguntas deliberadamente fuera de alcance, para verificar
que estas últimas activan el fallback "no tengo información" en vez de
una respuesta fabricada.

Requisitos previos (no corre en el CI normal — solo pytest -m unit):
    ollama serve
    docker-compose up -d chromadb

Ejecutar con:
    pytest -m eval tests/test_rag_eval.py -v -s

v1: solo reporta scores (no hay assert de umbral) — no existe todavía un
baseline estable con el que comparar, y las métricas dependen de un LLM
local no determinista. Los resultados se guardan en eval_results/latest.json
(gitignored) para comparar manualmente entre ejecuciones. Revisar ese
archivo tras cambios en el prompt, en min_relevance_score, o de modelo.
"""

import json
import warnings
from pathlib import Path

import pytest

# ragas 0.4.x avisa de que ragas.metrics (API clásica, la que usamos aquí)
# se deprecará en favor de ragas.metrics.collections (basada en `instructor`
# en vez de LangchainLLMWrapper) — ver comentario en requirements.txt.
warnings.filterwarnings("ignore", category=DeprecationWarning)


# Preguntas derivadas directamente del contenido de data/test_document.pdf
# (generado por scripts/generate_test_pdf.py — determinista, mismo texto
# siempre). Las últimas dos son deliberadamente ajenas al documento: deben
# activar el fallback de RAGService, no una respuesta inventada.
EVAL_DATASET = [
    {
        "question": "¿Qué significa RAG?",
        "ground_truth": "RAG significa Retrieval-Augmented Generation, una técnica que combina búsqueda de información con generación de texto mediante modelos de lenguaje.",
        "in_scope": True,
    },
    {
        "question": "¿Qué modelo de lenguaje usa el sistema?",
        "ground_truth": "El sistema usa Ollama con el modelo llama3.2.",
        "in_scope": True,
    },
    {
        "question": "¿Qué base de datos vectorial utiliza el proyecto?",
        "ground_truth": "El proyecto utiliza ChromaDB como base de datos vectorial.",
        "in_scope": True,
    },
    {
        "question": "¿Qué arquitectura de software utiliza el proyecto?",
        "ground_truth": "Arquitectura hexagonal (puertos y adaptadores), para mantener la lógica de negocio independiente de la infraestructura.",
        "in_scope": True,
    },
    {
        "question": "¿Qué framework se usa para la API REST?",
        "ground_truth": "FastAPI.",
        "in_scope": True,
    },
    {
        "question": "¿Cuáles son las ventajas mencionadas del sistema?",
        "ground_truth": "Privacidad total (todo es local), sin costos de API externa, escalable y mantenible, y fácil de testear.",
        "in_scope": True,
    },
    {
        "question": "¿Cuál es la fórmula química del agua?",
        "ground_truth": None,
        "in_scope": False,
    },
    {
        "question": "¿Quién ganó el Mundial de fútbol de 2022?",
        "ground_truth": None,
        "in_scope": False,
    },
]

EVAL_COLLECTION = "bibliotecario_eval"  # dedicada, no toca bibliotecario_docs
EVAL_RESULTS_PATH = Path(__file__).parent / "eval_results" / "latest.json"


@pytest.mark.eval
@pytest.mark.integration
@pytest.mark.asyncio
async def test_rag_quality_with_ragas():
    """
    Ingesta data/test_document.pdf en una colección dedicada, ejecuta
    EVAL_DATASET a través del pipeline RAG real, y calcula métricas RAGAS
    sobre las respuestas obtenidas.
    """
    from app.adapters.outbound.ollama_adapter import OllamaAdapter
    from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
    from app.adapters.outbound.pdf_processor_adapter import PDFProcessorAdapter
    from app.core.services.sync_service import SyncService
    from app.core.services.rag_service import RAGService
    from app.core.domain.models import Query
    from app.config.settings import settings

    ollama = OllamaAdapter()
    if not await ollama.is_available():
        pytest.skip("Ollama no está disponible")

    chromadb = ChromaDBAdapter()
    try:
        await chromadb.collection_exists(EVAL_COLLECTION)
    except Exception:
        pytest.skip("ChromaDB no está disponible")

    test_pdf = Path(__file__).parent.parent.parent / "data" / "test_document.pdf"
    if not test_pdf.exists():
        pytest.skip(f"PDF de prueba no encontrado en {test_pdf} (regenerar con scripts/generate_test_pdf.py)")

    # ========================================================================
    # PASO 1: Ingestar el documento de prueba en una colección dedicada
    # ========================================================================
    pdf_processor = PDFProcessorAdapter()
    sync_service = SyncService(document_processor=pdf_processor, llm=ollama, vector_db=chromadb)
    sync_result = await sync_service.sync_document_from_file(str(test_pdf), collection_name=EVAL_COLLECTION)
    assert sync_result.success, f"Ingesta falló: {sync_result.message}"

    # ========================================================================
    # PASO 2: Ejecutar cada pregunta a través del pipeline RAG real
    # ========================================================================
    rag_service = RAGService(llm=ollama, vector_db=chromadb)

    eval_rows = []
    for item in EVAL_DATASET:
        query = Query(question=item["question"], max_results=4)
        response = await rag_service.ask_question(query, collection_name=EVAL_COLLECTION)
        eval_rows.append({
            "question": item["question"],
            "ground_truth": item["ground_truth"],
            "in_scope": item["in_scope"],
            "answer": response.answer,
            "contexts": [doc.chunk_content for doc in response.source_documents],
        })

    # ========================================================================
    # PASO 3: Calcular métricas RAGAS
    # ========================================================================
    from langchain_ollama import ChatOllama, OllamaEmbeddings
    from ragas import evaluate, EvaluationDataset
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.metrics import Faithfulness, ResponseRelevancy, LLMContextPrecisionWithoutReference

    # Juez: mismo Ollama local, pero por su propio cliente ChatOllama (RAGAS
    # espera un BaseChatModel de LangChain, no el OllamaLLM de completions
    # que usa el resto de la app) y temperature=0 para que el juicio sea lo
    # más determinista posible.
    judge_llm = LangchainLLMWrapper(ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=0.0,
    ))
    judge_embeddings = LangchainEmbeddingsWrapper(OllamaEmbeddings(
        model=settings.ollama_embedding_model,
        base_url=settings.ollama_base_url,
    ))

    ragas_dataset = EvaluationDataset.from_list([
        {
            "user_input": row["question"],
            "response": row["answer"],
            "retrieved_contexts": row["contexts"] or ["(sin contexto recuperado)"],
        }
        for row in eval_rows
    ])

    result = evaluate(
        dataset=ragas_dataset,
        metrics=[Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithoutReference()],
        llm=judge_llm,
        embeddings=judge_embeddings,
        raise_exceptions=False,  # una métrica fallida (p.ej. NaN por json inválido del juez) no debe tumbar el test
    )
    scores_df = result.to_pandas()

    # ========================================================================
    # PASO 4: Guardar y reportar resultados
    # ========================================================================
    EVAL_RESULTS_PATH.parent.mkdir(exist_ok=True)
    report = {
        "rows": [
            {
                **eval_rows[i],
                "faithfulness": _safe_float(scores_df.iloc[i].get("faithfulness")),
                "answer_relevancy": _safe_float(scores_df.iloc[i].get("answer_relevancy")),
                "context_precision": _safe_float(scores_df.iloc[i].get("llm_context_precision_without_reference")),
            }
            for i in range(len(eval_rows))
        ],
    }
    EVAL_RESULTS_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print("\n" + "=" * 100)
    print(f"{'Pregunta':<45} {'Alcance':<10} {'Faithful':<10} {'Relevancy':<10} {'CtxPrec':<10}")
    print("-" * 100)
    for row in report["rows"]:
        scope = "dentro" if row["in_scope"] else "fuera"
        print(
            f"{row['question'][:44]:<45} {scope:<10} "
            f"{_fmt(row['faithfulness']):<10} {_fmt(row['answer_relevancy']):<10} {_fmt(row['context_precision']):<10}"
        )
    print("=" * 100)
    print(f"Resultados completos guardados en: {EVAL_RESULTS_PATH}")

    # Éxito del harness en sí (no de la calidad del RAG): que haya corrido
    # de principio a fin y producido una fila por pregunta. La calidad se
    # lee del reporte de arriba / del JSON, no se afirma aquí (ver v1 en
    # el docstring del módulo).
    assert len(report["rows"]) == len(EVAL_DATASET)


def _safe_float(value) -> float | None:
    """None si el valor es NaN (fallo del juez al parsear su propia respuesta) o falta."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # f != f ⟺ NaN


def _fmt(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "N/A"
