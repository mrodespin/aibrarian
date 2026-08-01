
# /api/Dockerfile

# 1. Use an official lightweight Python image
FROM python:3.11-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy requirements file first (for caching)
COPY requirements.txt .

# 4. Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 4b. Pre-download the local embedding model (used by GroqAdapter, see
# app/adapters/outbound/groq_adapter.py, EMBEDDING_BACKEND=onnx default) so
# it's baked into the image instead of being fetched on first container
# start. ONNXMiniLM_L6_V2 caches to ~/.cache/chroma/onnx_models — same
# $HOME (root) at build time and at runtime, so this is picked up as-is,
# no env var needed to point at it (unlike the sentence-transformers/HF
# path this replaced, see git history: that one needed HF_HUB_OFFLINE to
# stop it re-checking Hugging Face on every startup even when cached).
# If you switch EMBEDDING_BACKEND=sentence_transformers (see settings.py),
# add `pip install sentence-transformers` and a matching pre-download step
# here — deliberately not the default, it adds ~650MB (torch+transformers)
# and risks the same Render free-tier OOM this Dockerfile was fixed for.
RUN python -c "from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2; ONNXMiniLM_L6_V2()(['warmup'])"

# 5. Copy the rest of the application code
# It copies the local './app' folder into the container's '/app/app' folder
COPY ./app /app/app

# 6. Expose the port the API will run on
EXPOSE 8000

# 7. Command to run the application (will be run by docker-compose, or by
# Render with $PORT set to whatever port it assigns — defaults to 8000
# for local/docker-compose use where PORT isn't set).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]