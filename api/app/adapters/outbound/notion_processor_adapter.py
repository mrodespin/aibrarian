# /api/app/adapters/outbound/notion_processor_adapter.py

"""
Notion document processor adapter using LangChain.
"""

from typing import List, Optional, Dict, Any
from pathlib import Path
import logging
import uuid

from langchain_community.document_loaders import NotionDBLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from notion_client import Client as NotionClient

from app.core.ports.document_processor_port import DocumentProcessorPort
from app.core.domain.models import Document, Chunk, DocumentSource
from app.config.settings import settings


logger = logging.getLogger(__name__)


class NotionProcessorAdapter(DocumentProcessorPort):
    """Notion processor implementation using LangChain."""

    def __init__(self, notion_api_key: Optional[str] = None):
        """
        Initialize Notion processor.

        Args:
            notion_api_key: Notion API key (defaults to settings)
        """
        self._api_key = notion_api_key or settings.notion_api_key
        self._client = None
        self._text_splitter = None

        if not self._api_key:
            logger.warning("Notion API key not configured")

    def _get_client(self) -> NotionClient:
        """Get or create Notion client."""
        if self._client is None:
            if not self._api_key:
                raise ValueError("Notion API key is required")
            self._client = NotionClient(auth=self._api_key)
            logger.info("Initialized Notion client")
        return self._client

    def _get_text_splitter(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None
    ) -> RecursiveCharacterTextSplitter:
        """Get or create text splitter with specified parameters."""
        actual_chunk_size = chunk_size or settings.chunk_size
        actual_overlap = chunk_overlap or settings.chunk_overlap

        return RecursiveCharacterTextSplitter(
            chunk_size=actual_chunk_size,
            chunk_overlap=actual_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )

    async def load_document(self, source: str | Path) -> Document:
        """
        Load a Notion page by ID.

        Args:
            source: Notion page ID or URL

        Returns:
            Document object with content and metadata
        """
        try:
            # Extract page ID from URL if necessary
            page_id = self._extract_page_id(str(source))

            client = self._get_client()

            # Retrieve page content
            page = client.pages.retrieve(page_id=page_id)

            # Get page properties
            title = self._extract_title(page)

            # Get page content blocks
            content = await self._get_page_content(page_id)

            # Create Document object
            document = Document(
                id=f"notion_{page_id}",
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
        Get text content from a Notion page.

        Args:
            page_id: Notion page ID

        Returns:
            Combined text content
        """
        client = self._get_client()

        try:
            # Get all blocks (content) of the page
            blocks = client.blocks.children.list(block_id=page_id)

            content_parts = []

            for block in blocks.get("results", []):
                block_type = block.get("type")

                # Extract text based on block type
                if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
                    text_content = self._extract_text_from_block(block)
                    if text_content:
                        content_parts.append(text_content)

                elif block_type == "code":
                    code_block = block.get("code", {})
                    code_text = self._extract_rich_text(code_block.get("rich_text", []))
                    if code_text:
                        content_parts.append(f"```\n{code_text}\n```")

                elif block_type == "quote":
                    quote_block = block.get("quote", {})
                    quote_text = self._extract_rich_text(quote_block.get("rich_text", []))
                    if quote_text:
                        content_parts.append(f"> {quote_text}")

            return "\n\n".join(content_parts)

        except Exception as e:
            logger.error(f"Failed to get page content: {e}")
            raise

    def _extract_text_from_block(self, block: Dict[str, Any]) -> str:
        """Extract text from a block."""
        block_type = block.get("type")
        block_content = block.get(block_type, {})
        rich_text = block_content.get("rich_text", [])
        return self._extract_rich_text(rich_text)

    def _extract_rich_text(self, rich_text_array: List[Dict[str, Any]]) -> str:
        """Extract plain text from Notion rich text array."""
        return "".join([text.get("plain_text", "") for text in rich_text_array])

    def _extract_title(self, page: Dict[str, Any]) -> str:
        """Extract title from a Notion page."""
        properties = page.get("properties", {})

        # Try common title property names
        for key in ["title", "Title", "Name", "name"]:
            if key in properties:
                title_prop = properties[key]
                if title_prop.get("type") == "title":
                    title_array = title_prop.get("title", [])
                    return self._extract_rich_text(title_array)

        return "Untitled"

    def _extract_page_id(self, source: str) -> str:
        """
        Extract page ID from Notion URL or return as-is if already an ID.

        Args:
            source: Notion page ID or URL

        Returns:
            Clean page ID
        """
        # If it's a URL, extract the ID
        if "notion.so" in source or "notion.site" in source:
            # Format: https://www.notion.so/Page-Title-{32-char-id}
            parts = source.split("-")
            if len(parts) > 0:
                potential_id = parts[-1].split("?")[0]  # Remove query params
                if len(potential_id) == 32:
                    return potential_id

        # Remove hyphens if present (Notion IDs are 32 chars without hyphens)
        clean_id = source.replace("-", "")
        return clean_id

    async def split_into_chunks(
        self,
        document: Document,
        chunk_size: int = 1000,
        chunk_overlap: int = 200
    ) -> List[Chunk]:
        """Split document into chunks."""
        try:
            text_splitter = self._get_text_splitter(chunk_size, chunk_overlap)

            # Split text
            text_chunks = text_splitter.split_text(document.content)

            # Create Chunk objects
            chunks = []
            for i, chunk_text in enumerate(text_chunks):
                chunk = Chunk(
                    id=f"{document.id}_chunk_{i}",
                    document_id=document.id,
                    content=chunk_text,
                    embedding=None,  # Embeddings will be added later
                    metadata={
                        **document.metadata,
                        "chunk_index": i,
                        "chunk_total": len(text_chunks)
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
        """Complete pipeline: load and split Notion document."""
        try:
            # Load document
            document = await self.load_document(source)

            # Split into chunks
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
        Check if source is a Notion page.
        For Notion, we check if it's a valid page ID or URL.
        """
        source = str(file_path)

        # Check if it's a Notion URL
        if "notion.so" in source or "notion.site" in source:
            return True

        # Check if it's a 32-character ID (with or without hyphens)
        clean_id = source.replace("-", "")
        if len(clean_id) == 32 and clean_id.isalnum():
            return True

        return False

    async def load_database_pages(
        self,
        database_id: str,
        max_pages: Optional[int] = None
    ) -> List[Document]:
        """
        Load all pages from a Notion database.

        Args:
            database_id: Notion database ID
            max_pages: Maximum number of pages to load (None for all)

        Returns:
            List of Document objects
        """
        try:
            client = self._get_client()

            # Query database
            query_params = {}
            if max_pages:
                query_params["page_size"] = min(max_pages, 100)

            response = client.databases.query(database_id=database_id, **query_params)

            documents = []
            for page in response.get("results", [])[:max_pages] if max_pages else response.get("results", []):
                try:
                    page_id = page["id"]
                    document = await self.load_document(page_id)
                    documents.append(document)
                except Exception as e:
                    logger.error(f"Failed to load page {page.get('id')}: {e}")
                    continue

            logger.info(f"Loaded {len(documents)} pages from database {database_id}")
            return documents

        except Exception as e:
            logger.error(f"Failed to load database pages: {e}")
            raise
