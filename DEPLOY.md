# Deploy for free (end-to-end)

Recommended **$0/month** stack:

| Part | Service | Free tier |
|------|---------|-----------|
| **Frontend** (React) | [Vercel](https://vercel.com) | Static hosting |
| **Backend** (FastAPI) | [Render](https://render.com) | Web service (sleeps after ~15 min idle) |
| **Database** (users, chats) | [Neon](https://neon.tech) | PostgreSQL |
| **AI** | OpenAI | Pay-as-you-go (not free; you need `OPENAI_API_KEY`) |

**Note:** FAISS vectors live on the **Render disk** (ephemeral on free tier). After a **redeploy or long idle restart**, users must **upload & index documents again**. Chat history in Neon **persists**.

---

## 1. PostgreSQL on Neon (free)

1. Sign up at [neon.tech](https://neon.tech) → **New project**.
2. Copy the connection string (starts with `postgresql://...`).
3. For SQLAlchemy + psycopg3, change the prefix to:
   ```
   postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require
   ```
4. Save this as `DATABASE_URL` (you will paste it into Render).

---

## 2. Backend on Render (free)

1. Push your repo to **GitHub** (if not already).
2. [render.com](https://render.com) → **New → Web Service** → connect the repo.
3. Settings:
   - **Runtime:** Python 3
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
   - **Health check path:** `/health`
4. **Environment variables:**

   | Key | Value |
   |-----|--------|
   | `OPENAI_API_KEY` | your OpenAI key |
   | `DATABASE_URL` | Neon URL (`postgresql+psycopg://...`) |
   | `CORS_ORIGINS` | your Vercel URL, e.g. `https://your-app.vercel.app` |
   | `PYTHON_VERSION` | `3.12.7` (optional) |

   Optional: `GEMINI_API_KEY`, `RAG_TOP_K=5`

5. Deploy → copy the public URL, e.g. `https://ai-business-assistant-api.onrender.com`

**Test:** open `https://YOUR-API.onrender.com/health` → `{"status":"ok"}`

**Free tier:** first request after sleep can take **30–60 seconds** (cold start).

---

## 3. Frontend on Vercel (free)

1. [vercel.com](https://vercel.com) → **Add New Project** → import the same GitHub repo.
2. **Root Directory:** `frontend-react`
3. **Framework Preset:** Vite
4. **Build command:** `npm run build`
5. **Output directory:** `dist`
6. **Environment variable:**

   | Key | Value |
   |-----|--------|
   | `VITE_API_BASE_URL` | `https://YOUR-API.onrender.com` (no trailing slash) |

7. Deploy → open the Vercel URL.

7. Update Render **`CORS_ORIGINS`** to your exact Vercel URL if you didn’t already.

---

## 4. Demo flow (production)

1. Open Vercel URL (wait if API was sleeping).
2. Download sample HR FAQ from sidebar.
3. Upload & index to knowledge base.
4. Ask: *“What is the PTO carryover limit?”*

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| CORS error in browser | Set `CORS_ORIGINS` on Render to your Vercel origin (no trailing slash). |
| “Cannot connect to server” | API cold start — wait ~1 min; check Render logs. |
| Chat works but no doc answers | Re-upload & index (FAISS cleared after redeploy). |
| Build fails on Render (memory) | Free tier is 512 MB; remove unused deps or use a paid plan. |
| PyMuPDF errors | PDF **text** still works; chart captions may be skipped. Use `.txt` for demos. |

---

## Cost summary

- Vercel, Render web, Neon Postgres: **$0/month** on free tiers.
- OpenAI API: **usage-based** (embeddings + chat per request).

---

## Alternative: run backend locally, frontend on Vercel

Set `VITE_API_BASE_URL` to a tunnel (ngrok) — useful for testing only, not a stable production setup.
