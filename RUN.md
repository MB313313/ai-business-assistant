# How to run this project

Quick reference: start the **API** first, then the **Streamlit** UI.

## One-time setup

From the project root (folder that contains `backend/`, `frontend/`, `requirements.txt`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set at least `OPENAI_API_KEY` (and any other keys your features need).

## Run backend (FastAPI)

**From project root** (recommended):

```powershell
uvicorn backend.app.main:app --reload
```

API default URL: **http://127.0.0.1:8000** — docs at **http://127.0.0.1:8000/docs**

Alternative, from inside `backend/`:

```powershell
cd backend
uvicorn app.main:app --reload
```

## Run frontend (Streamlit)

Use a **second** terminal, project root, venv activated:

```powershell
streamlit run frontend/app.py
```

Streamlit opens in the browser (default **http://localhost:8501**).

## Optional

If the API is not on `http://127.0.0.1:8000`, set **`API_BASE_URL`** in `.env` so the Streamlit app points at the right server.
