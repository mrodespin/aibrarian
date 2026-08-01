
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
# app/adapters/outbound/groq_adapter.py) so it's baked into the image
# instead of being fetched from Hugging Face on first container start.
# Must match settings.embedding_model_name's default (app/config/settings.py)
# and render.yaml's EMBEDDING_MODEL_NAME. HF_HOME pins the cache to the
# default lookup path sentence-transformers uses at runtime.
ENV HF_HOME=/root/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# HF_HUB_OFFLINE set AFTER the download above (not before, or the download
# itself would fail): at runtime this stops sentence-transformers from
# making Hugging Face network calls to check for updated metadata — it was
# doing this on every warm-up despite the model already being cached from
# the RUN step above. Runtime now loads purely from the baked-in cache.
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1

# 5. Copy the rest of the application code
# It copies the local './app' folder into the container's '/app/app' folder
COPY ./app /app/app

# 6. Expose the port the API will run on
EXPOSE 8000

# 7. Command to run the application (will be run by docker-compose, or by
# Render with $PORT set to whatever port it assigns — defaults to 8000
# for local/docker-compose use where PORT isn't set).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]