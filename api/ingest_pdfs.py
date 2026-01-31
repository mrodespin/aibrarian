#!/usr/bin/env python3
# /api/ingest_pdfs.py
"""
Script CLI de Ingesta de PDFs - TFM Bibliotecario-IA

Este script es una ALTERNATIVA a la API para ingestar PDFs desde el terminal.
En lugar de hacer una petición HTTP a POST /sync, lo ejecutas directamente
desde la línea de comandos.

¿Cuándo usar este script vs la API?
- Este script: desarrollo, ingesta manual en batch, no necesitas la API activa
- La API (POST /sync): cuando otra aplicación o el frontend necesita ingestar

¿Qué hace internamente?
Exactamente lo mismo que los endpoints /sync y /sync/directory de main.py:
crea las mismas dependencias, usa el mismo SyncService, y ejecuta el mismo
pipeline (load → split → embed → store). La diferencia es solo la interfaz
de entrada (CLI vs HTTP).

Flujo de ejecución:
    1. check_services()     → Verifica que Ollama y ChromaDB están activos
    2. Inicializa adaptadores y SyncService (misma wiring que main.py)
    3. ingest_file() o ingest_directory() según los argumentos CLI
    4. Imprime resumen de resultados

Uso:
    python ingest_pdfs.py                     # Todos los PDFs en ./data
    python ingest_pdfs.py /ruta/a/pdfs        # PDFs de un directorio específico
    python ingest_pdfs.py manual.pdf          # Un solo PDF (detecta que es fichero)
    python ingest_pdfs.py --file manual.pdf   # Mismo resultado, explícito
"""

# ============================================================================
# IMPORTS
# ============================================================================
import asyncio   # Para ejecutar código async desde un script síncrono
import logging
import sys
from pathlib import Path
from typing import Optional
import argparse   # Librería estándar de Python para parsear argumentos CLI
                  # Equivalente a libraries como 'commander' o 'yargs' en Node.js

# ============================================================================
# CONFIGURACIÓN DE PATH
# ============================================================================
# sys.path.insert(0, ...): añade el directorio api/ al path de búsqueda de módulos.
#
# ¿Por qué es necesario?
# Este script se ejecuta desde api/ como punto de entrada:
#     cd api && python ingest_pdfs.py
# Sin esta línea, Python no encontraría el paquete "app" porque busca
# módulos relativo al directorio del script, y "app" está dentro de api/.
#
# Path(__file__).parent = directorio donde está este script = api/
# Equivalente JS: require.resolve('./app/...')
sys.path.insert(0, str(Path(__file__).parent))

from app.config.settings import settings
from app.core.services.sync_service import SyncService
from app.adapters.outbound.chromadb_adapter import ChromaDBAdapter
from app.adapters.outbound.ollama_adapter import OllamaAdapter
from app.adapters.outbound.pdf_processor_adapter import PDFProcessorAdapter


# ============================================================================
# CONFIGURACIÓN DE LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================================
# VERIFICACIÓN DE SERVICIOS
# ============================================================================
async def check_services():
    """
    Verifica que Ollama y ChromaDB están activos antes de proceder.

    Se ejecuta al inicio del script para fallar rápido con mensajes
    claros si algún servicio no está disponible, en lugar de fallar
    en medio del procesamiento con errores confusos.

    Crea instancias temporales de los adaptadores solo para el check.
    Las instancias definitivas se crean después en main().

    Returns:
        bool: True si todos los servicios están disponibles
    """
    logger.info("Checking service availability...")

    # Verificar Ollama (necesario para embeddings y generación de texto)
    ollama = OllamaAdapter()
    ollama_ok = await ollama.is_available()

    if not ollama_ok:
        logger.error("❌ Ollama is not available!")
        logger.error(f"   Make sure Ollama is running at {settings.ollama_base_url}")
        logger.error("   Run: ollama serve")
        return False

    logger.info(f"✅ Ollama is available ({settings.ollama_model})")

    # Verificar ChromaDB (necesario para almacenar los embeddings)
    # collection_exists("test") es una llamada ligera que comprueba
    # la conectividad sin crear ni modificar datos reales.
    chromadb = ChromaDBAdapter()
    try:
        exists = await chromadb.collection_exists("test")
        logger.info(f"✅ ChromaDB is available ({settings.chromadb_url})")
    except Exception as e:
        logger.error(f"❌ ChromaDB is not available: {e}")
        logger.error("   Make sure ChromaDB is running")
        return False

    return True


# ============================================================================
# FUNCIONES DE INGESTA
# ============================================================================
async def ingest_file(file_path: Path, sync_service: SyncService):
    """
    Ingesta un solo archivo PDF.

    Es un wrapper delgado alrededor de SyncService.sync_document_from_file()
    que añade formato visual al output del terminal (separadores, iconos).

    Args:
        file_path: Ruta al archivo PDF a procesar
        sync_service: Instancia del servicio de sincronización

    Returns:
        SyncResult si el procesamiento se intentó, None si hubo excepción
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {file_path.name}")
    logger.info(f"{'='*60}")

    try:
        # Delegar todo el trabajo al servicio (mismo pipeline que la API)
        result = await sync_service.sync_document_from_file(file_path)

        if result.success:
            logger.info(f"✅ Successfully ingested: {file_path.name}")
            logger.info(f"   Document ID: {result.document_id}")
            logger.info(f"   Chunks created: {result.chunks_created}")
            logger.info(f"   Processing time: {result.processing_time:.2f}s")
        else:
            logger.error(f"❌ Failed to ingest: {file_path.name}")
            logger.error(f"   Error: {result.message}")

        return result

    except Exception as e:
        logger.error(f"❌ Error processing {file_path.name}: {e}", exc_info=True)
        return None


async def ingest_directory(directory_path: Path, sync_service: SyncService):
    """
    Ingesta todos los archivos PDF de un directorio.

    Itera secuencialmente sobre los PDFs encontrados llamando a
    ingest_file() para cada uno. Si un PDF falla, el script continúa
    con los siguientes (no falla todo por un archivo).

    Args:
        directory_path: Ruta al directorio a escanear
        sync_service: Instancia del servicio de sincronización

    Returns:
        list[SyncResult]: Resultados de cada PDF procesado exitosamente
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Scanning directory: {directory_path}")
    logger.info(f"{'='*60}")

    # glob("*.pdf") busca todos los archivos .pdf en el directorio
    # list() materializa el generador en una lista
    pdf_files = list(directory_path.glob("*.pdf"))

    if not pdf_files:
        logger.warning(f"No PDF files found in {directory_path}")
        return []

    logger.info(f"Found {len(pdf_files)} PDF files")

    results = []
    for pdf_file in pdf_files:
        result = await ingest_file(pdf_file, sync_service)
        if result:
            results.append(result)

    return results


# ============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ============================================================================
async def main():
    """
    Función principal del script: parsea argumentos, inicializa servicios
    y orqestra la ingesta.

    Flujo:
        1. Parsear argumentos CLI con argparse
        2. Verificar servicios (check_services)
        3. Inicializar adaptadores y SyncService (misma wiring que main.py)
        4. Detectar modo: fichero individual vs directorio
        5. Ejecutar ingesta
        6. Imprimir resumen
    """
    # ================================================================
    # PARSEO DE ARGUMENTOS CLI (argparse)
    # ================================================================
    # argparse construye automáticamente --help y valida los argumentos.
    # Equivalente JS: const program = new Command(); program.argument(...)
    parser = argparse.ArgumentParser(
        description="Ingest PDF documents into Bibliotecario-IA vector database"
    )
    parser.add_argument(
        "path",
        nargs="?",          # "?" = el argumento es opcional (posicional)
        default=None,       # Si no se proporciona, vale None
        help="Path to PDF file or directory (defaults to ./data)"
    )
    parser.add_argument(
        "--file",
        "-f",               # "-f" es el alias corto de "--file"
        action="store_true", # No recibe valor: si está presente es True, si no False
        help="Treat path as a single file, not a directory"
    )
    parser.add_argument(
        "--collection",
        "-c",
        default=None,
        help="Collection name (defaults to config setting)"
    )

    # parse_args() lee sys.argv y devuelve un objeto con los valores.
    # args.path, args.file, args.collection están disponibles después.
    args = parser.parse_args()

    # Banner visual del script
    print("\n" + "="*60)
    print("📚 Bibliotecario-IA - PDF Ingestion Script")
    print("="*60 + "\n")

    # ================================================================
    # VERIFICACIÓN DE SERVICIOS
    # ================================================================
    # Fallar rápido si algo no está disponible.
    # sys.exit(1) termina el script con código de error (no 0 = fallo).
    if not await check_services():
        logger.error("\n❌ Service checks failed. Please fix the issues above and try again.")
        sys.exit(1)

    # ================================================================
    # INICIALIZACIÓN DE DEPENDENCIAS
    # ================================================================
    # Misma wiring que en main.py: adaptadores → servicio.
    # Se repite aquí porque este script es independiente de la API.
    logger.info("\nInitializing services...")
    chromadb_adapter = ChromaDBAdapter()
    ollama_adapter = OllamaAdapter()
    pdf_processor = PDFProcessorAdapter()

    sync_service = SyncService(
        document_processor=pdf_processor,
        llm=ollama_adapter,
        vector_db=chromadb_adapter
    )

    # ================================================================
    # DETERMINAR LA RUTA A PROCESAR
    # ================================================================
    # Si el usuario no pasa path, usar el directorio por defecto (./data)
    if args.path:
        path = Path(args.path)
    else:
        path = Path(settings.data_directory)
        logger.info(f"Using default data directory: {path}")

    if not path.exists():
        logger.error(f"❌ Path does not exist: {path}")
        sys.exit(1)

    # ================================================================
    # MODO: FICHERO INDIVIDUAL vs DIRECTORIO
    # ================================================================
    # Detecta automáticamente si es un fichero o directorio.
    # El flag --file fuerza modo fichero (útil si el nombre es ambiguo).
    results = []

    if args.file or path.is_file():
        # --- Modo fichero individual ---
        if not path.suffix.lower() == ".pdf":
            logger.error("❌ File must be a PDF")
            sys.exit(1)

        result = await ingest_file(path, sync_service)
        if result:
            results.append(result)

    else:
        # --- Modo directorio ---
        if not path.is_dir():
            logger.error(f"❌ Not a directory: {path}")
            sys.exit(1)

        results = await ingest_directory(path, sync_service)

    # ================================================================
    # RESUMEN DE RESULTADOS
    # ================================================================
    print("\n" + "="*60)
    print("📊 Ingestion Summary")
    print("="*60)

    if results:
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_chunks = sum(r.chunks_created for r in results if r.success)
        total_time = sum(r.processing_time for r in results if r.processing_time)

        print(f"Total files: {len(results)}")
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"📦 Total chunks created: {total_chunks}")
        print(f"⏱️  Total processing time: {total_time:.2f}s")

        if successful > 0:
            print(f"\n✨ Documents are now available for querying!")
            print(f"   Collection: {args.collection or settings.chromadb_collection_name}")
    else:
        print("❌ No documents were processed")

    print("="*60 + "\n")


# ============================================================================
# BLOQUE DE ENTRADA
# ============================================================================
# asyncio.run(main()): puente entre el mundo síncrono (if __name__)
# y el mundo asíncrono (todas las funciones son async).
#
# asyncio.run() crea un event loop, ejecuta la coroutine main(),
# y lo cierra cuando termina. Es el equivalente a:
#   const main = async () => { ... };
#   main().catch(console.error);
#
# KeyboardInterrupt: se captura cuando el usuario hace Ctrl+C.
# sys.exit(0) = salida limpia (código 0 = éxito).
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Ingestion interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n\n❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
