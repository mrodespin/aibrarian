# 🚀 Deploying on Render (optional)

Guide to deploying your own instance on [Render](https://render.com) using Groq as the LLM and Chroma Cloud as the vector database, instead of native Ollama + local ChromaDB. See [ADR-007](adr/007-cloud-deployment-groq-chroma.md) for the full reasoning behind this choice.

**This does NOT replace local development.** `docker-compose up -d` with `LLM_PROVIDER=ollama` (the default) keeps working exactly as before — this guide is only for anyone who wants their own instance reachable outside `localhost`, without depending on local hardware (Metal GPU) or on Ollama running.

---

## Prerequisites

1. **A Render account** — [render.com](https://render.com), free tier, no card required for `plan: free` services.
2. **A Groq API key** — [console.groq.com/keys](https://console.groq.com/keys), free, no card.
3. **A Chroma Cloud database** — [trychroma.com](https://www.trychroma.com), free tier up to 1M embeddings, no card required to sign up (verified). Creating the database gives you an `api_key` (and optionally `tenant`/`database`, though they can be left empty if the key is bound to a single DB).
4. **A Postgres database** (for authentication) — [neon.tech](https://neon.tech), free tier, no card required. Copy the connection string from the dashboard after creating the project.

## Steps

### 1. Deploy the blueprint

The repo includes [`render.yaml`](../render.yaml) at the root. In Render's dashboard:

1. **New → Blueprint**
2. Connect this GitHub repository
3. Render detects `render.yaml` and proposes creating **two services**: `aibrarian-api` (Docker, `plan: free`, built from `api/Dockerfile`) and `aibrarian-frontend` (Static Site, built from `frontend/`)
4. Confirm creation

### 2. Create the first user (before filling in the next step's variables)

There's no public signup — the login is created via the CLI, pointing directly at your Neon database (no need for the API to be deployed yet):

```bash
source api/venv/bin/activate
DATABASE_URL="<your Neon connection string>" python scripts/create_user.py --email you@email.com
```

Doing this before the first deploy avoids the API starting up with no user to log in as.

### 3. Fill in the variables marked `sync: false`

`render.yaml` defines which variables each service needs, but the secret ones (`sync: false`) **aren't checked into version control** — Render asks for them when you confirm the blueprint, or you fill them in afterward under each service → **Environment**:

**`aibrarian-api` service:**

| Variable | Value |
|---|---|
| `GROQ_API_KEY` | Your key from console.groq.com |
| `CHROMA_CLOUD_API_KEY` | Your Chroma Cloud key |
| `CHROMA_CLOUD_TENANT` | Your DB's tenant (optional, see below) |
| `CHROMA_CLOUD_DATABASE` | Your DB's name (optional, see below) |
| `NOTION_API_KEY` | Only if you're going to sync Notion |
| `DATABASE_URL` | Neon connection string (the same one from step 2) |
| `JWT_SECRET_KEY` | Generate one: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FRONTEND_URL` | The public URL Render assigned to `aibrarian-frontend` (visible in its dashboard once created) — needed for CORS |

Chroma Cloud's `tenant`/`database` can be left empty: `chromadb.CloudClient` resolves them automatically from the API key if it's bound to a single database.

The rest of the API service's variables (`LLM_PROVIDER=groq`, `VECTOR_DB_PROVIDER=chroma_cloud`, `GROQ_MODEL`, `EMBEDDING_MODEL_NAME`, `JWT_EXPIRATION_MINUTES`) are already set in `render.yaml` — no need to touch them unless you want a different Groq model or session duration.

**`aibrarian-frontend` service:**

| Variable | Value |
|---|---|
| `VITE_API_URL` | The public URL Render assigned to `aibrarian-api` |

This variable is baked in at build time (Vite substitutes it during the build, not at startup) — if you change it later, the frontend needs a manual redeploy for it to take effect.

### 4. First startup and ingestion

The Chroma Cloud database starts out empty — it's a new DB, not a copy of your local ChromaDB (the embeddings aren't compatible either: 384 dims with the ONNX backend vs. 768 with `nomic-embed-text`, see ADR-007). Index documents against the already-deployed API by logging in first:

```bash
# 1. Log in and save the access token for the next requests
TOKEN=$(curl -s -X POST "https://<your-api>.onrender.com/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@email.com", "password": "..."}' \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# 2. Upload a PDF
curl -X POST "https://<your-api>.onrender.com/sync/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@document.pdf"

# 3. Or a Notion page
curl -X POST "https://<your-api>.onrender.com/sync/notion" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"page_id": "..."}'
```

Or more simply: open `aibrarian-frontend`'s URL in a browser, log in, and use the sync panel.

### 5. Verify

```bash
# Public, no login needed (also used as Render's healthcheck):
curl https://<your-api>.onrender.com/health

# Protected — must return 401 with no token:
curl https://<your-api>.onrender.com/stats
```

`services.ollama` in `/health`'s response reflects Groq's availability (the JSON key didn't change, for frontend compatibility, see ADR-007), and `config.llm_provider` should show `"groq"`.

---

## Limitations to keep in mind

- **Cold starts**: Render's `plan: free` services sleep after ~15 min with no traffic; the first request after sleeping can take tens of seconds to respond.
- **Build RAM**: `EMBEDDING_BACKEND=onnx` is used by default (`chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2`), specifically chosen for Render's free tier (512MB RAM) — it doesn't drag in `torch`. If you switch to `EMBEDDING_BACKEND=sentence_transformers` (more accurate, but ~650MB extra on disk for `torch`), the service will likely fail to start from running out of memory on the free tier.
