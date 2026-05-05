# How to run this project

Quick reference: start the **API** first, then the **React (Vite)** UI.

## One-time setup

From the project root (folder that contains `backend/`, `frontend-react/`, `requirements.txt`):

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

## Run frontend (React / Vite)

Use a **second** terminal:

```powershell
cd frontend-react
npm install
npm run dev
```

Vite opens in the browser (default **http://localhost:5173**).

The React app uses a dev proxy so it can call the backend as `/api/*` (configured in `frontend-react/vite.config.ts`).
