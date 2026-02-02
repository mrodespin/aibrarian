# 📁 Data Directory

Esta carpeta está destinada a almacenar los **documentos PDF** que serán procesados e ingestados en la base de datos vectorial del sistema Bibliotecario-IA.

## 📝 Uso

1. **Coloca tus archivos PDF aquí**: Copia los documentos PDF que deseas indexar en esta carpeta.

2. **Ejecuta el script de ingesta**:
   ```bash
   # Procesa todos los PDFs en /data
   python scripts/ingest_pdfs.py

   # O especifica un directorio diferente
   python scripts/ingest_pdfs.py /ruta/a/otros/pdfs

   # O procesa un archivo específico
   python scripts/ingest_pdfs.py --file documento.pdf
   ```

3. **O usa la API**:
   ```bash
   curl -X POST "http://localhost:8000/sync" \
     -H "Content-Type: application/json" \
     -d '{"file_path": "./data/documento.pdf"}'

   # O sincroniza todo el directorio
   curl -X POST "http://localhost:8000/sync/directory"
   ```

## ⚙️ Proceso de Ingesta

Cuando ejecutas el script de ingesta o usas la API, el sistema:

1. **Carga** el PDF y extrae su contenido de texto
2. **Divide** el texto en chunks (fragmentos) de ~1000 caracteres
3. **Genera** embeddings (vectores) para cada chunk usando Ollama
4. **Almacena** los chunks con sus embeddings en ChromaDB

Después de la ingesta, los documentos estarán disponibles para consultas a través del endpoint `/ask`.

## 📊 Ejemplo

```
/data
├── README.md              (este archivo)
├── manual_usuario.pdf
├── documentacion_api.pdf
└── guia_instalacion.pdf
```

## ⚠️ Notas Importantes

- Solo se procesan archivos con extensión `.pdf`
- Los archivos grandes pueden tardar varios minutos en procesarse
- Asegúrate de que Ollama y ChromaDB estén corriendo antes de ingestar documentos
- Los nombres de archivo se incluyen en los metadatos para referencia

## 🔍 Verificar Ingesta

Para verificar que los documentos se ingirieron correctamente:

```bash
# Consulta las estadísticas de la colección
curl http://localhost:8000/stats
```

---

**Parte del proyecto**: TFM Bibliotecario-IA
**Fase**: MVP (Ingesta de documentos)
