# 📁 Data Directory

This folder is where **PDF documents** go to be processed and ingested into AIbrarian's vector database.

## 📝 Usage

1. **Put your PDF files here**: copy the PDF documents you want indexed into this folder.

2. **Run the ingestion script**:
   ```bash
   # Process every PDF in /data
   python scripts/ingest_pdfs.py

   # Or specify a different directory
   python scripts/ingest_pdfs.py /path/to/other/pdfs

   # Or process a specific file
   python scripts/ingest_pdfs.py --file document.pdf
   ```

3. **Or use the API**:
   ```bash
   curl -X POST "http://localhost:8000/sync" \
     -H "Content-Type: application/json" \
     -d '{"file_path": "./data/document.pdf"}'

   # Or sync the whole directory
   curl -X POST "http://localhost:8000/sync/directory"
   ```

## ⚙️ Ingestion Process

When you run the ingestion script or use the API, the system:

1. **Loads** the PDF and extracts its text content
2. **Splits** the text into ~1000-character chunks
3. **Generates** embeddings (vectors) for each chunk using Ollama
4. **Stores** the chunks with their embeddings in ChromaDB

After ingestion, the documents become available for queries through the `/ask` endpoint.

## 📊 Example

```
/data
├── README.md              (this file)
├── user_manual.pdf
├── api_documentation.pdf
└── installation_guide.pdf
```

## ⚠️ Important Notes

- Only files with a `.pdf` extension are processed
- Large files can take several minutes to process
- Make sure Ollama and ChromaDB are running before ingesting documents
- File names are included in the metadata for reference

## 🔍 Verify Ingestion

To verify documents were ingested correctly:

```bash
# Check the collection's statistics
curl http://localhost:8000/stats
```
