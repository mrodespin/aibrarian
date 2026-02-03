# /api/app/adapters/outbound/notion_processor_adapter.py
"""
Adaptador de procesamiento de Notion - TFM Bibliotecario-IA

Implementación concreta de DocumentProcessorPort para páginas de Notion.
Es el adaptador que convierte una página de Notion en chunks para el sistema RAG.

¿Diferencias con el adaptador PDF?
- PDF: lee archivos locales del disco
- Notion: hace llamadas a la API remota de Notion
- PDF: el texto viene pre-extraído por PyPDFLoader
- Notion: el texto tiene que extraerse bloque a bloque manualmente

¿Qué es la estructura de bloques de Notion?
Una página de Notion no es texto plano. Es una lista de bloques tipados:
    [paragraph] "Este es un párrafo..."
    [heading_1] "Título principal"
    [code]      "const x = 5;"
    [quote]     "Una cita importante"

Cada bloque tiene un tipo y contiene "rich text" (texto con formato).

¿Qué es rich text?
Notion no devuelve texto plano. Cada fragmento es un objeto:
    [{"plain_text": "Este es ", "bold": false},
     {"plain_text": "importante", "bold": true}]
Se extrae solo el plain_text y se une: "Este es importante"

Método extra vs PDF:
- load_database_pages(): carga TODAS las páginas de una base de datos de Notion
  No existe en el PDF porque los PDFs son archivos individuales

Equivalente en TypeScript:
    class NotionProcessorAdapter implements DocumentProcessorPort {
        constructor(private notionApiKey?: string) {}
        async loadDocument(source: string | Path): Promise<Document> { ... }
        async splitIntoChunks(doc: Document, size?, overlap?): Promise<Chunk[]> { ... }
        async processDocument(source: string | Path): Promise<[Document, Chunk[]]> { ... }
        supportsFormat(filePath: string | Path): boolean { ... }
        async loadDatabasePages(databaseId: string, maxPages?: number): Promise<Document[]> { ... }
    }
"""

# ============================================================================
# IMPORTS
# ============================================================================
from typing import List, Optional, Dict, Any
from pathlib import Path
import logging
import uuid

# NotionDBLoader: carga contenido de bases de datos de Notion (LangChain)
from langchain_community.document_loaders import NotionDBLoader
# Mismo splitter que en el adaptador PDF
from langchain_text_splitters import RecursiveCharacterTextSplitter
# Cliente oficial de Notion para interactuar con su API
from notion_client import Client as NotionClient

# Importamos el PUERTO (interfaz) que implementamos
from app.core.ports.document_processor_port import DocumentProcessorPort
from app.core.domain.models import Document, Chunk, DocumentSource
from app.config.settings import settings


logger = logging.getLogger(__name__)


# ============================================================================
# ADAPTADOR NOTION
# ============================================================================
class NotionProcessorAdapter(DocumentProcessorPort):
    """
    Implementación concreta de DocumentProcessorPort para Notion.

    Esta clase es el ÚNICO lugar que conoce cómo comunicarse con la API de Notion.
    El resto del sistema solo habla con la interfaz DocumentProcessorPort.

    Requiere una API key de Notion para autenticarse.
    La key se obtiene de settings o se pasa directamente al constructor.
    """

    def __init__(self, notion_api_key: Optional[str] = None):
        """
        Inicializa el procesador de Notion.

        La API key puede venir de dos fuentes:
        1. Parámetro directo (útil para testing)
        2. settings.notion_api_key (variable de entorno, por defecto)

        El operador "or" selecciona el primero que no sea None/vacío.

        Args:
            notion_api_key: API key de Notion (opcional, usa settings si no se da)
        """
        # notion_api_key or settings.notion_api_key:
        # Si se pasa API key, la usa. Si no, busca en settings (env vars)
        self._api_key = notion_api_key or settings.notion_api_key
        self._client = None          # Cliente Notion (lazy initialization)
        self._text_splitter = None

        # Advertencia temprana si no hay API key configurada
        if not self._api_key:
            logger.warning("Notion API key not configured")

    def _get_client(self) -> NotionClient:
        """
        Obtiene o crea el cliente de Notion (Lazy Singleton).

        El cliente necesita la API key para autenticarse.
        Si no hay key, lanza un error explicativo.

        Returns:
            NotionClient: Cliente autenticado con la API de Notion
        """
        if self._client is None:
            if not self._api_key:
                raise ValueError("Notion API key is required")
            # NotionClient(auth=key): crea cliente autenticado
            self._client = NotionClient(auth=self._api_key)
            logger.info("Initialized Notion client")
        return self._client

    def _get_text_splitter(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None
    ) -> RecursiveCharacterTextSplitter:
        """
        Crea el mismo RecursiveCharacterTextSplitter que el adaptador PDF.

        La lógica de dividir texto es IDÉNTICA entre PDF y Notion.
        Solo difiere cómo se OBTIENE el texto (archivo vs API).

        Args:
            chunk_size: Tamaño objetivo por chunk (None = usa settings)
            chunk_overlap: Overlap entre chunks (None = usa settings)

        Returns:
            RecursiveCharacterTextSplitter configurado
        """
        actual_chunk_size = chunk_size or settings.chunk_size
        actual_overlap = chunk_overlap or settings.chunk_overlap

        return RecursiveCharacterTextSplitter(
            chunk_size=actual_chunk_size,
            chunk_overlap=actual_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )

    # ========================================================================
    # MÉTODOS PRINCIPALES - Implementación de DocumentProcessorPort
    # ========================================================================

    async def load_document(self, source: str | Path) -> Document:
        """
        Carga una página de Notion y extrae todo su texto.

        Proceso interno:
        1. Extrae el page_id de la URL (si es URL) o lo usa directamente
        2. Obtiene metadatos de la página (título, fechas, etc.)
        3. Obtiene el contenido bloque a bloque (_get_page_content)
        4. Crea un objeto Document

        ¿Por qué el ID del documento es notion_{page_id} y no un uuid?
        Porque las páginas de Notion ya tienen ID único.
        Esto permite re-ingestar la misma página sin crear duplicados.

        Args:
            source: ID de página o URL de Notion
                   Ejemplos:
                   - "a1b2c3d4e5f6..." (32 caracteres, el page_id)
                   - "https://www.notion.so/Mi-Pagina-a1b2c3d4e5f6..."

        Returns:
            Document: con contenido extraído y metadatos de Notion
        """
        try:
            # Extrae el page_id limpio (funciona con URL o ID directo)
            page_id = self._extract_page_id(str(source))

            client = self._get_client()

            # pages.retrieve: obtiene metadatos de la página (no el contenido)
            page = client.pages.retrieve(page_id=page_id)

            # Extraer título de las propiedades de la página
            title = self._extract_title(page)

            # Extraer contenido de propiedades de BD (columnas como Nombre, Contenido, etc.)
            properties_content = self._extract_properties_content(page)

            # Obtener el contenido de bloques (párrafos dentro de la página)
            blocks_content = await self._get_page_content(page_id)

            # Combinar: título prominente + propiedades + bloques
            content_parts = []

            # Añadir título como encabezado para mejor búsqueda semántica
            if title and title != "Untitled":
                content_parts.append(f"# {title}")

            if properties_content:
                content_parts.append(properties_content)
            if blocks_content:
                content_parts.append(blocks_content)
            content = "\n\n".join(content_parts)

            # Crear objeto Document con metadatos de Notion
            document = Document(
                id=f"notion_{page_id}",        # ID determinista (mismo page_id)
                source=DocumentSource.NOTION,
                content=content,
                metadata={
                    "notion_page_id": page_id,
                    "title": title,
                    "url": page.get("url", ""),
                    "created_time": page.get("created_time", ""),
                    "last_edited_time": page.get("last_edited_time", "")
                }
            )

            logger.info(f"Loaded Notion page: {title}")
            return document

        except Exception as e:
            logger.error(f"Failed to load Notion page from {source}: {e}")
            raise

    async def _get_page_content(self, page_id: str) -> str:
        """
        Extrae el texto de una página de Notion bloque a bloque.

        MÉTODO PRIVADO - es donde ocurre el trabajo real de parsear Notion.

        La API de Notion devuelve el contenido como una lista de bloques.
        Cada bloque tiene un "type" y contenido específico según ese tipo.

        Tipos de bloque soportados:
        - paragraph, heading_1/2/3, bulleted_list_item, numbered_list_item
            → se extrae el texto directamente
        - code → se envuelve en ``` para mantener formato
        - quote → se añade ">" para formato de cita

        Tipos NO soportados (se ignoran):
        - image, file, embed, divider, table, etc.
        - Solo procesamos bloques que contienen texto

        Args:
            page_id: ID de la página de Notion

        Returns:
            str: Todo el texto de la página unido con \n\n
        """
        client = self._get_client()

        try:
            # blocks.children.list: obtiene todos los bloques de la página
            # Retorna un objeto con "results" (lista de bloques)
            blocks = client.blocks.children.list(block_id=page_id)

            content_parts = []

            for block in blocks.get("results", []):
                block_type = block.get("type")

                # Bloques de texto estándar: párrafos, títulos, listas
                if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
                    text_content = self._extract_text_from_block(block)
                    if text_content:
                        content_parts.append(text_content)

                # Bloques de código: se envuelven en ``` para preservar formato
                elif block_type == "code":
                    code_block = block.get("code", {})
                    code_text = self._extract_rich_text(code_block.get("rich_text", []))
                    if code_text:
                        content_parts.append(f"```\n{code_text}\n```")

                # Bloques de cita: se añade ">" al inicio
                elif block_type == "quote":
                    quote_block = block.get("quote", {})
                    quote_text = self._extract_rich_text(quote_block.get("rich_text", []))
                    if quote_text:
                        content_parts.append(f"> {quote_text}")

                # Otros tipos (image, divider, etc.) se ignoran silenciosamente

            # Une todos los bloques con separador de párrafo
            final_content = "\n\n".join(content_parts)
            if not final_content:
                logger.warning(f"Page {page_id}: no text content extracted (may contain only images/embeds)")
            return final_content

        except Exception as e:
            logger.error(f"Failed to get page content: {e}")
            raise

    def _extract_text_from_block(self, block: Dict[str, Any]) -> str:
        """
        Extrae texto de un bloque genérico de Notion.

        La estructura de un bloque es:
            {
                "type": "paragraph",
                "paragraph": {           ← el contenido está bajo una key
                    "rich_text": [...]    ← con nombre igual al "type"
                }
            }

        block.get(block_type, {}) obtiene el contenido usando el tipo
        como nombre de la clave. Es un truco genérico que funciona para
        paragraph, heading_1, bulleted_list_item, etc.

        Args:
            block: Objeto bloque de la API de Notion

        Returns:
            str: Texto extraído del bloque
        """
        block_type = block.get("type")
        # El contenido está en una clave con el mismo nombre que el tipo
        block_content = block.get(block_type, {})
        rich_text = block_content.get("rich_text", [])
        return self._extract_rich_text(rich_text)

    def _extract_rich_text(self, rich_text_array: List[Dict[str, Any]]) -> str:
        """
        Extrae texto plano de un array de rich text de Notion.

        Notion representa texto con formato como una lista de objetos:
            [
                {"plain_text": "Este es ", "annotations": {"bold": false}},
                {"plain_text": "importante", "annotations": {"bold": true}},
                {"plain_text": ".", "annotations": {"bold": false}}
            ]

        Solo nos interesa el plain_text, ignoramos el formato (bold, italic, etc.)
        Resultado: "Este es importante."

        Equivalente JS:
            richTextArray.map(t => t.plain_text).join("")

        Args:
            rich_text_array: Array de objetos rich text de Notion

        Returns:
            str: Texto plano sin formato
        """
        # List comprehension + join: extrae plain_text de cada objeto y lo une
        return "".join([text.get("plain_text", "") for text in rich_text_array])

    def _extract_properties_content(self, page: Dict[str, Any]) -> str:
        """
        Extrae texto de las propiedades de una página de base de datos de Notion.

        Cuando las páginas vienen de una BD, las columnas son "propiedades"
        que contienen datos estructurados (texto, números, selects, etc.).

        Este método extrae el contenido de texto de propiedades relevantes
        para incluirlo en el documento indexable.

        Tipos de propiedad soportados:
        - title: título de la página
        - rich_text: texto enriquecido (ej: "Contenido", "Descripción")
        - number: números (ej: "Año" → "Año: 2024")
        - select: selección única (ej: "Director" → "Director: Spielberg")
        - multi_select: selección múltiple (ej: "Géneros" → "Géneros: Acción, Drama")
        - date: fechas
        - url: URLs
        - email: emails
        - phone_number: teléfonos

        Args:
            page: Objeto página devuelto por la API de Notion

        Returns:
            str: Contenido extraído de las propiedades, formateado como "Propiedad: valor"
        """
        properties = page.get("properties", {})
        content_parts = []

        for prop_name, prop_data in properties.items():
            prop_type = prop_data.get("type")
            value = None

            if prop_type == "title":
                title_array = prop_data.get("title", [])
                value = self._extract_rich_text(title_array)

            elif prop_type == "rich_text":
                rich_text_array = prop_data.get("rich_text", [])
                value = self._extract_rich_text(rich_text_array)

            elif prop_type == "number":
                num = prop_data.get("number")
                if num is not None:
                    value = str(num)

            elif prop_type == "select":
                select_data = prop_data.get("select")
                if select_data:
                    value = select_data.get("name", "")

            elif prop_type == "multi_select":
                multi_select = prop_data.get("multi_select", [])
                if multi_select:
                    value = ", ".join(item.get("name", "") for item in multi_select)

            elif prop_type == "date":
                date_data = prop_data.get("date")
                if date_data:
                    start = date_data.get("start", "")
                    end = date_data.get("end", "")
                    value = f"{start} - {end}" if end else start

            elif prop_type == "url":
                value = prop_data.get("url")

            elif prop_type == "email":
                value = prop_data.get("email")

            elif prop_type == "phone_number":
                value = prop_data.get("phone_number")

            elif prop_type == "checkbox":
                checked = prop_data.get("checkbox")
                if checked is not None:
                    value = "Sí" if checked else "No"

            # Si hay valor, añadirlo con formato "Propiedad: valor"
            if value:
                # Poner título/nombre al principio para mejor indexación
                if prop_type == "title":
                    content_parts.insert(0, f"Título: {value}")
                else:
                    content_parts.append(f"{prop_name}: {value}")

        return "\n".join(content_parts)

    def _extract_title(self, page: Dict[str, Any]) -> str:
        """
        Extrae el título de una página de Notion.

        En Notion, el título es una propiedad especial de tipo "title".
        El nombre de esa propiedad puede variar: "title", "Title", "Name", "name".
        Este método prueba los nombres más comunes.

        Si no encuentra título, retorna "Untitled" como fallback.

        Args:
            page: Objeto página devuelto por la API de Notion

        Returns:
            str: Título de la página o "Untitled"
        """
        properties = page.get("properties", {})

        # Prueba nombres comunes de la propiedad título
        for key in ["title", "Title", "Name", "name", "Nombre"]:
            if key in properties:
                title_prop = properties[key]
                if title_prop.get("type") == "title":
                    title_array = title_prop.get("title", [])
                    return self._extract_rich_text(title_array)

        return "Untitled"

    def _extract_page_id(self, source: str) -> str:
        """
        Extrae el page_id de una URL de Notion o lo retorna tal cual si ya es un ID.

        Las URLs de Notion tienen este formato:
            https://www.notion.so/Titulo-De-La-Pagina-a1b2c3d4e5f6789...
            └─────────────────────────────────────┘└──── 32 chars ────┘

        El page_id son los últimos 32 caracteres hexadecimales.

        Si el source ya es un ID (32 chars sin guiones), lo limpia y lo retorna.
        Los IDs de Notion pueden venir con guiones: "a1b2c3d4-e5f6-..." que se elimina.

        Args:
            source: URL de Notion o page_id directo

        Returns:
            str: ID limpio de 32 caracteres
        """
        # Si es una URL de Notion, extraer el ID del final
        if "notion.so" in source or "notion.site" in source:
            # Formato: https://www.notion.so/Page-Title-{32-char-id}
            # split("-") divide por guiones, el último elemento es el ID
            parts = source.split("-")
            if len(parts) > 0:
                # El último part puede tener query params (?v=...)
                potential_id = parts[-1].split("?")[0]
                if len(potential_id) == 32:
                    return potential_id

        # Si no es URL, eliminar guiones si los tiene
        # Los IDs de Notion son 32 chars: con o sin guiones
        clean_id = source.replace("-", "")
        return clean_id

    async def split_into_chunks(
        self,
        document: Document,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> List[Chunk]:
        """
        Divide el contenido de la página de Notion en chunks.

        La lógica es IDÉNTICA a la del adaptador PDF.
        Una vez que tenemos el texto extraído de Notion, el proceso
        de dividir en chunks es exactamente el mismo.

        Esto demuestra la utilidad de la interfaz DocumentProcessorPort:
        la lógica de chunking es la misma independientemente de la fuente.

        Args:
            document: Documento ya cargado desde Notion
            chunk_size: Tamaño objetivo por chunk en caracteres
            chunk_overlap: Caracteres de overlap entre chunks

        Returns:
            List[Chunk]: Lista de chunks sin embeddings
        """
        try:
            text_splitter = self._get_text_splitter(chunk_size, chunk_overlap)

            # Divide el texto extraído de Notion en fragmentos
            text_chunks = text_splitter.split_text(document.content)

            # Crea objetos Chunk con metadatos de Notion
            chunks = []
            for i, chunk_text in enumerate(text_chunks):
                chunk = Chunk(
                    # ID trazable: "notion_{page_id}_chunk_0"
                    id=f"{document.id}_chunk_{i}",
                    document_id=document.id,
                    content=chunk_text,
                    embedding=None,  # Se añade después en SyncService
                    metadata={
                        **document.metadata,            # Hereda metadatos de Notion (title, url, etc.)
                        "chunk_index": i,               # Posición del chunk
                        "chunk_total": len(text_chunks) # Total de chunks
                    }
                )
                chunks.append(chunk)

            logger.info(f"Split Notion document {document.id} into {len(chunks)} chunks")
            return chunks

        except Exception as e:
            logger.error(f"Failed to split document: {e}")
            raise

    async def process_document(
        self,
        source: str | Path,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> tuple[Document, List[Chunk]]:
        """
        Pipeline completo: carga la página de Notion y la divide en chunks.

        Método de conveniencia que combina load_document() + split_into_chunks().
        Es el que lo llama el SyncService.

        Args:
            source: ID de página o URL de Notion
            chunk_size: Tamaño de chunks
            chunk_overlap: Overlap entre chunks

        Returns:
            tuple[Document, List[Chunk]]: Documento y sus chunks
        """
        try:
            # Paso 1: Cargar página desde la API de Notion
            document = await self.load_document(source)

            # Paso 2: Dividir en chunks
            chunks = await self.split_into_chunks(document, chunk_size, chunk_overlap)

            logger.info(
                f"Processed Notion document {document.id}: "
                f"{len(chunks)} chunks from '{document.metadata.get('title', 'Untitled')}'"
            )

            return document, chunks

        except Exception as e:
            logger.error(f"Failed to process Notion document: {e}")
            raise

    def supports_format(self, file_path: str | Path) -> bool:
        """
        Verifica si el source es una página de Notion válida.

        A diferencia del PDF (que verifica extensión de archivo),
        aquí verificamos si es una URL de Notion o un ID válido.

        Criterios de validación:
        1. Contiene "notion.so" o "notion.site" → es una URL de Notion
        2. Es un string de 32 caracteres alfanuméricos → es un page_id

        isalnum(): retorna True si todos los caracteres son alfanuméricos
        Equivalente JS: /^[a-zA-Z0-9]+$/.test(cleanId)

        Args:
            file_path: Source a verificar (URL o page_id)

        Returns:
            bool: True si parece ser una página de Notion
        """
        source = str(file_path)

        # Verificar si es URL de Notion
        if "notion.so" in source or "notion.site" in source:
            return True

        # Verificar si es un page_id válido (32 chars alfanuméricos)
        # Los IDs de Notion pueden venir con guiones, los eliminamos primero
        clean_id = source.replace("-", "")
        if len(clean_id) == 32 and clean_id.isalnum():
            return True

        return False

    # ========================================================================
    # MÉTODO EXTRA - No existe en el adaptador PDF
    # ========================================================================

    async def load_database_pages(
        self,
        database_id: str,
        max_pages: Optional[int] = None
    ) -> List[Document]:
        """
        Carga todas las páginas de una base de datos de Notion.

        MÉTODO EXTRA que no existe en la interfaz DocumentProcessorPort.
        Es específico de Notion porque solo Notion tiene el concepto
        de "bases de datos" (como tablas con filas que son páginas).

        Útil cuando tienes una base de datos con muchos artículos
        y quieres ingestarlos todos de una vez.

        ¿Por qué page_size = min(max_pages, 100)?
        La API de Notion tiene un límite de 100 resultados por petición.
        Si pides más, necesitarías paginación (no implementada aquí en MVP).

        Manejo de errores por página:
        Si una página falla, se loguea el error pero el bucle CONTINÚA
        con las siguientes páginas (continue). No falla todo por una página.

        Args:
            database_id: ID de la base de datos de Notion
            max_pages: Máximo de páginas a cargar (None = todas)

        Returns:
            List[Document]: Lista de documentos cargados exitosamente
        """
        try:
            client = self._get_client()

            # Preparar parámetros de la query
            query_params = {}
            if max_pages:
                # Limitar page_size al mínimo entre max_pages y 100 (límite de Notion)
                query_params["page_size"] = min(max_pages, 100)

            # databases.query: busca todas las páginas en la base de datos
            response = client.databases.query(database_id=database_id, **query_params)

            documents = []

            # Obtener resultados, limitado por max_pages si se especifica
            # [:max_pages] es slicing: toma los primeros N elementos
            pages = response.get("results", [])[:max_pages] if max_pages else response.get("results", [])

            for page in pages:
                try:
                    page_id = page["id"]
                    # Carga cada página individualmente
                    document = await self.load_document(page_id)
                    documents.append(document)
                except Exception as e:
                    # Si una página falla, se loguea pero se continúa con las siguientes
                    # "continue" salta a la siguiente iteración del bucle
                    logger.error(f"Failed to load page {page.get('id')}: {e}")
                    continue

            logger.info(f"Loaded {len(documents)} pages from database {database_id}")
            return documents

        except Exception as e:
            logger.error(f"Failed to load database pages: {e}")
            raise
