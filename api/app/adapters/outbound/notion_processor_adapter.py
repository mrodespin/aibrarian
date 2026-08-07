# /api/app/adapters/outbound/notion_processor_adapter.py
"""
Notion Processing Adapter - AIbrarian

Concrete implementation of DocumentProcessorPort for Notion pages. This
is the adapter that turns a Notion page into chunks for the RAG system.

Differences from the PDF adapter?
- PDF: reads local files from disk
- Notion: makes calls to Notion's remote API
- PDF: the text comes pre-extracted by PyPDFLoader
- Notion: the text has to be manually extracted block by block

What is Notion's block structure?
A Notion page isn't plain text. It's a list of typed blocks:
    [paragraph] "This is a paragraph..."
    [heading_1] "Main title"
    [code]      "const x = 5;"
    [quote]     "An important quote"

Each block has a type and contains "rich text" (formatted text).

What is rich text?
Notion doesn't return plain text. Each fragment is an object:
    [{"plain_text": "This is ", "bold": false},
     {"plain_text": "important", "bold": true}]
Only the plain_text is extracted and joined: "This is important"

Extra method vs. PDF:
- load_database_pages(): loads ALL pages of a Notion database.
  Doesn't exist for PDFs because PDFs are individual files.

TypeScript equivalent:
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

# NotionDBLoader: loads content from Notion databases (LangChain)
from langchain_community.document_loaders import NotionDBLoader
# Same splitter as the PDF adapter
from langchain_text_splitters import RecursiveCharacterTextSplitter
# Notion's official client for interacting with its API
from notion_client import Client as NotionClient

# Import the PORT (interface) we're implementing
from app.core.ports.document_processor_port import DocumentProcessorPort
from app.core.domain.models import Document, Chunk, DocumentSource
from app.config.settings import settings


logger = logging.getLogger(__name__)


# ============================================================================
# NOTION ADAPTER
# ============================================================================
class NotionProcessorAdapter(DocumentProcessorPort):
    """
    Concrete implementation of DocumentProcessorPort for Notion.

    This class is the ONLY place that knows how to talk to Notion's API.
    Everywhere else in the system only talks to the
    DocumentProcessorPort interface.

    Requires a Notion API key to authenticate. The key comes from
    settings or is passed directly to the constructor.
    """

    def __init__(self, notion_api_key: Optional[str] = None):
        """
        Initializes the Notion processor.

        The API key can come from two sources:
        1. Direct parameter (useful for testing)
        2. settings.notion_api_key (environment variable, default)

        The "or" operator picks the first one that isn't None/empty.

        Args:
            notion_api_key: Notion API key (optional, uses settings if not given)
        """
        # notion_api_key or settings.notion_api_key:
        # If an API key is passed, use it. Otherwise, look in settings (env vars)
        self._api_key = notion_api_key or settings.notion_api_key
        self._client = None          # Notion client (lazy initialization)
        self._text_splitter = None

        # Early warning if no API key is configured
        if not self._api_key:
            logger.warning("Notion API key not configured")

    def _get_client(self) -> NotionClient:
        """
        Gets or creates the Notion client (Lazy Singleton).

        The client needs the API key to authenticate.
        If there's no key, it raises an explanatory error.

        Returns:
            NotionClient: Client authenticated against Notion's API
        """
        if self._client is None:
            if not self._api_key:
                raise ValueError("Notion API key is required")
            # NotionClient(auth=key): creates an authenticated client
            self._client = NotionClient(auth=self._api_key)
            logger.info("Initialized Notion client")
        return self._client

    def _get_text_splitter(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None
    ) -> RecursiveCharacterTextSplitter:
        """
        Creates the same RecursiveCharacterTextSplitter as the PDF adapter.

        The text-splitting logic is IDENTICAL between PDF and Notion.
        Only how the text is OBTAINED differs (file vs. API).

        Args:
            chunk_size: Target size per chunk (None = uses settings)
            chunk_overlap: Overlap between chunks (None = uses settings)

        Returns:
            A configured RecursiveCharacterTextSplitter
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
    # MAIN METHODS - DocumentProcessorPort implementation
    # ========================================================================

    async def load_document(self, source: str | Path) -> Document:
        """
        Loads a Notion page and extracts all its text.

        Internal process:
        1. Extracts the page_id from the URL (if it's a URL) or uses it directly
        2. Gets the page's metadata (title, dates, etc.)
        3. Gets the content block by block (_get_page_content)
        4. Creates a Document object

        Why is the document's ID notion_{page_id} instead of a uuid?
        Because Notion pages already have a unique ID.
        This lets you re-ingest the same page without creating duplicates.

        Args:
            source: Notion page ID or URL
                   Examples:
                   - "a1b2c3d4e5f6..." (32 characters, the page_id)
                   - "https://www.notion.so/My-Page-a1b2c3d4e5f6..."

        Returns:
            Document: with the extracted content and Notion metadata
        """
        try:
            # Extracts the clean page_id (works with a URL or a direct ID)
            page_id = self._extract_page_id(str(source))

            client = self._get_client()

            # pages.retrieve: gets the page's metadata (not its content)
            page = client.pages.retrieve(page_id=page_id)

            # Extract the title from the page's properties
            title = self._extract_title(page)

            # Extract content from DB properties (columns like Name, Content, etc.)
            properties_content = self._extract_properties_content(page)

            # Get the block content (paragraphs within the page)
            blocks_content = await self._get_page_content(page_id)

            # Combine: prominent title + properties + blocks
            content_parts = []

            # Add the title as a heading for better semantic search
            if title and title != "Untitled":
                content_parts.append(f"# {title}")

            if properties_content:
                content_parts.append(properties_content)
            if blocks_content:
                content_parts.append(blocks_content)
            content = "\n\n".join(content_parts)

            # Create the Document object with Notion metadata
            document = Document(
                id=f"notion_{page_id}",        # Deterministic ID (same page_id)
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
        Extracts the text of a Notion page, block by block.

        PRIVATE METHOD — this is where the real work of parsing Notion happens.

        Notion's API returns the content as a list of blocks. Each block
        has a "type" and specific content depending on that type.

        Supported block types:
        - paragraph, heading_1/2/3, bulleted_list_item, numbered_list_item
            → text extracted directly
        - code → wrapped in ``` to preserve formatting
        - quote → prefixed with ">" for quote formatting

        Unsupported types (ignored):
        - image, file, embed, divider, table, etc.
        - We only process blocks that contain text

        Args:
            page_id: The Notion page's ID

        Returns:
            str: All of the page's text, joined with \n\n
        """
        client = self._get_client()

        try:
            # blocks.children.list: gets all of the page's blocks
            # Returns an object with "results" (list of blocks)
            blocks = client.blocks.children.list(block_id=page_id)

            content_parts = []

            for block in blocks.get("results", []):
                block_type = block.get("type")

                # Standard text blocks: paragraphs, headings, lists
                if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
                    text_content = self._extract_text_from_block(block)
                    if text_content:
                        content_parts.append(text_content)

                # Code blocks: wrapped in ``` to preserve formatting
                elif block_type == "code":
                    code_block = block.get("code", {})
                    code_text = self._extract_rich_text(code_block.get("rich_text", []))
                    if code_text:
                        content_parts.append(f"```\n{code_text}\n```")

                # Quote blocks: prefixed with ">"
                elif block_type == "quote":
                    quote_block = block.get("quote", {})
                    quote_text = self._extract_rich_text(quote_block.get("rich_text", []))
                    if quote_text:
                        content_parts.append(f"> {quote_text}")

                # Other types (image, divider, etc.) are silently ignored

            # Joins all the blocks with a paragraph separator
            final_content = "\n\n".join(content_parts)
            if not final_content:
                logger.warning(f"Page {page_id}: no text content extracted (may contain only images/embeds)")
            return final_content

        except Exception as e:
            logger.error(f"Failed to get page content: {e}")
            raise

    def _extract_text_from_block(self, block: Dict[str, Any]) -> str:
        """
        Extracts text from a generic Notion block.

        A block's structure looks like:
            {
                "type": "paragraph",
                "paragraph": {           ← the content is under a key
                    "rich_text": [...]    ← named the same as "type"
                }
            }

        block.get(block_type, {}) gets the content using the type as the
        key's name. It's a generic trick that works for paragraph,
        heading_1, bulleted_list_item, etc.

        Args:
            block: Block object from Notion's API

        Returns:
            str: Text extracted from the block
        """
        block_type = block.get("type")
        # The content is under a key with the same name as the type
        block_content = block.get(block_type, {})
        rich_text = block_content.get("rich_text", [])
        return self._extract_rich_text(rich_text)

    def _extract_rich_text(self, rich_text_array: List[Dict[str, Any]]) -> str:
        """
        Extracts plain text from a Notion rich text array.

        Notion represents formatted text as a list of objects:
            [
                {"plain_text": "This is ", "annotations": {"bold": false}},
                {"plain_text": "important", "annotations": {"bold": true}},
                {"plain_text": ".", "annotations": {"bold": false}}
            ]

        We only care about plain_text, ignoring the formatting (bold, italic, etc.)
        Result: "This is important."

        JS equivalent:
            richTextArray.map(t => t.plain_text).join("")

        Args:
            rich_text_array: Array of Notion rich text objects

        Returns:
            str: Plain, unformatted text
        """
        # List comprehension + join: extracts plain_text from each object and joins it
        return "".join([text.get("plain_text", "") for text in rich_text_array])

    def _extract_properties_content(self, page: Dict[str, Any]) -> str:
        """
        Extracts text from a Notion database page's properties.

        When pages come from a database, the columns are "properties"
        holding structured data (text, numbers, selects, etc.).

        This method extracts the text content from relevant properties
        to include it in the indexable document.

        Supported property types:
        - title: the page's title
        - rich_text: formatted text (e.g. "Content", "Description")
        - number: numbers (e.g. "Year" → "Year: 2024")
        - select: single choice (e.g. "Director" → "Director: Spielberg")
        - multi_select: multiple choice (e.g. "Genres" → "Genres: Action, Drama")
        - date: dates
        - url: URLs
        - email: emails
        - phone_number: phone numbers

        Args:
            page: Page object returned by Notion's API

        Returns:
            str: Content extracted from the properties, formatted as "Property: value"
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
                    value = "Yes" if checked else "No"

            # If there's a value, add it formatted as "Property: value"
            if value:
                # Put the title/name first for better indexing
                if prop_type == "title":
                    content_parts.insert(0, f"Title: {value}")
                else:
                    content_parts.append(f"{prop_name}: {value}")

        return "\n".join(content_parts)

    def _extract_title(self, page: Dict[str, Any]) -> str:
        """
        Extracts a Notion page's title.

        In Notion, the title is a special property of type "title" — but
        the NAME of that property (the column the user sees) is
        arbitrary: it can be called "Name", "Movie", "Book", "Title",
        whatever. Notion doesn't guarantee the name, only that exactly
        ONE property with type=="title" exists per page (whether or not
        it comes from a database).

        That's why this method does NOT guess column names (the previous
        version tried a fixed list ["title", "Title", "Name", "name",
        "Nombre"], which failed as soon as the database used any other
        name — it returned "Untitled" for all 12 pages of a real
        database whose column was named something else). Instead it
        searches by type, the same way _extract_properties_content()
        already does a few lines below — same criterion in both places
        that read the title.

        If the title property exists but is empty (nobody wrote anything
        in that Notion cell), it still returns "Untitled" as a fallback.

        Args:
            page: Page object returned by Notion's API

        Returns:
            str: The page's title, or "Untitled"
        """
        properties = page.get("properties", {})

        # Looks for the property with type=="title", regardless of its name
        for prop_data in properties.values():
            if prop_data.get("type") == "title":
                title_array = prop_data.get("title", [])
                title = self._extract_rich_text(title_array)
                if title:
                    return title

        return "Untitled"

    def _extract_page_id(self, source: str) -> str:
        """
        Extracts the page_id from a Notion URL, or returns it as-is if
        it's already an ID.

        Notion URLs look like this:
            https://www.notion.so/Page-Title-a1b2c3d4e5f6789...
            └─────────────────────────────────────┘└──── 32 chars ────┘

        The page_id is the last 32 hexadecimal characters.

        If the source is already an ID (32 chars with no dashes), it's
        cleaned up and returned.
        Notion IDs can come with dashes: "a1b2c3d4-e5f6-..." which get stripped.

        Args:
            source: A Notion URL or a direct page_id

        Returns:
            str: Clean 32-character ID
        """
        # If it's a Notion URL, extract the ID from the end
        if "notion.so" in source or "notion.site" in source:
            # Format: https://www.notion.so/Page-Title-{32-char-id}
            # split("-") splits on dashes, the last element is the ID
            parts = source.split("-")
            if len(parts) > 0:
                # The last part may have query params (?v=...)
                potential_id = parts[-1].split("?")[0]
                if len(potential_id) == 32:
                    return potential_id

        # If it's not a URL, strip dashes if it has any
        # Notion IDs are 32 chars: with or without dashes
        clean_id = source.replace("-", "")
        return clean_id

    async def split_into_chunks(
        self,
        document: Document,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> List[Chunk]:
        """
        Splits the Notion page's content into chunks.

        The logic is IDENTICAL to the PDF adapter's. Once we have the
        text extracted from Notion, the chunking process is exactly the
        same.

        This shows the value of the DocumentProcessorPort interface: the
        chunking logic is the same regardless of the source.

        Args:
            document: Document already loaded from Notion
            chunk_size: Target size per chunk in characters
            chunk_overlap: Overlap characters between chunks

        Returns:
            List[Chunk]: List of chunks with no embeddings
        """
        try:
            text_splitter = self._get_text_splitter(chunk_size, chunk_overlap)

            # Splits the text extracted from Notion into fragments
            text_chunks = text_splitter.split_text(document.content)

            # Creates Chunk objects with Notion metadata
            chunks = []
            for i, chunk_text in enumerate(text_chunks):
                chunk = Chunk(
                    # Traceable ID: "notion_{page_id}_chunk_0"
                    id=f"{document.id}_chunk_{i}",
                    document_id=document.id,
                    content=chunk_text,
                    embedding=None,  # Added later in SyncService
                    metadata={
                        **document.metadata,            # Inherits Notion metadata (title, url, etc.)
                        "chunk_index": i,               # Chunk position
                        "chunk_total": len(text_chunks) # Total number of chunks
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
        Full pipeline: loads the Notion page and splits it into chunks.

        A convenience method combining load_document() + split_into_chunks().
        This is the one SyncService calls.

        Args:
            source: Notion page ID or URL
            chunk_size: Chunk size
            chunk_overlap: Overlap between chunks

        Returns:
            tuple[Document, List[Chunk]]: The document and its chunks
        """
        try:
            # Step 1: Load the page from Notion's API
            document = await self.load_document(source)

            # Step 2: Split into chunks
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
        Checks whether the source is a valid Notion page.

        Unlike the PDF adapter (which checks the file extension), here
        we check whether it's a Notion URL or a valid ID.

        Validation criteria:
        1. Contains "notion.so" or "notion.site" → it's a Notion URL
        2. Is a 32-character alphanumeric string → it's a page_id

        isalnum(): returns True if every character is alphanumeric
        JS equivalent: /^[a-zA-Z0-9]+$/.test(cleanId)

        Args:
            file_path: The source to check (URL or page_id)

        Returns:
            bool: True if it looks like a Notion page
        """
        source = str(file_path)

        # Check whether it's a Notion URL
        if "notion.so" in source or "notion.site" in source:
            return True

        # Check whether it's a valid page_id (32 alphanumeric chars)
        # Notion IDs can come with dashes, strip them first
        clean_id = source.replace("-", "")
        if len(clean_id) == 32 and clean_id.isalnum():
            return True

        return False

    # ========================================================================
    # EXTRA METHOD - Doesn't exist in the PDF adapter
    # ========================================================================

    async def load_database_pages(
        self,
        database_id: str,
        max_pages: Optional[int] = None
    ) -> List[Document]:
        """
        Loads all pages of a Notion database.

        EXTRA METHOD that doesn't exist in the DocumentProcessorPort
        interface. Notion-specific because only Notion has the concept
        of "databases" (like tables whose rows are pages).

        Useful when you have a database with many articles and want to
        ingest them all at once.

        Why page_size = min(max_pages, 100)?
        Notion's API has a limit of 100 results per request. If you ask
        for more, you'd need pagination (not implemented here in this MVP).

        Per-page error handling:
        If a page fails, the error is logged but the loop CONTINUES with
        the remaining pages (continue). A single page doesn't fail the whole run.

        Args:
            database_id: Notion database ID
            max_pages: Maximum number of pages to load (None = all)

        Returns:
            List[Document]: List of successfully loaded documents
        """
        try:
            client = self._get_client()

            # Prepare the query's parameters
            query_params = {}
            if max_pages:
                # Cap page_size at the min of max_pages and 100 (Notion's limit)
                query_params["page_size"] = min(max_pages, 100)

            # databases.query: finds every page in the database
            response = client.databases.query(database_id=database_id, **query_params)

            documents = []

            # Get the results, capped by max_pages if given
            # [:max_pages] is slicing: takes the first N elements
            pages = response.get("results", [])[:max_pages] if max_pages else response.get("results", [])

            for page in pages:
                try:
                    page_id = page["id"]
                    # Loads each page individually
                    document = await self.load_document(page_id)
                    documents.append(document)
                except Exception as e:
                    # If a page fails, it's logged but the loop continues
                    # "continue" jumps to the next loop iteration
                    logger.error(f"Failed to load page {page.get('id')}: {e}")
                    continue

            logger.info(f"Loaded {len(documents)} pages from database {database_id}")
            return documents

        except Exception as e:
            logger.error(f"Failed to load database pages: {e}")
            raise
