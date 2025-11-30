# Civil AI

A lightweight FastAPI backend with a Next.js frontend for reinforced concrete design checks (beams, slabs, columns, and footings). The backend serves calculation results plus generated reports/drawings, while the frontend provides a tabbed UI to collect inputs and visualize responses.

## Prerequisites
- Python 3.10+
- Node.js 18+

## Backend (FastAPI)
1. Install dependencies:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. (Optional) Copy `.env.example` to `.env` and adjust:
   - `BACKEND_ALLOW_ORIGINS` (comma-separated CORS origins; defaults to common localhost ports)
   - `BACKEND_HOST` / `BACKEND_PORT` for local development
3. Start the server (default: http://127.0.0.1:8010):
   ```bash
   uvicorn app:app --reload --host 0.0.0.0 --port 8010
   ```
   Uvicorn also respects the `BACKEND_HOST` / `BACKEND_PORT` environment variables when running via `python app.py`.
4. Reports and drawing assets are written to the repository-level `reports/` folder and exposed under `/reports`.

## Frontend (Next.js)
1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```
2. Copy the sample environment file and adjust the backend URL if needed (no trailing slash):
   ```bash
   cp .env.example .env
   ```
   `NEXT_PUBLIC_BACKEND_URL` should point to the running FastAPI instance.
3. Run the dev server:
   ```bash
   npm run dev
   ```
4. Visit http://localhost:3000 to use the UI.

## Linting
- Frontend: `npm run lint`

## Notes
- The frontend defaults to `http://127.0.0.1:8010` if no environment variable is provided.
- CORS in the backend defaults to common localhost origins; override via `BACKEND_ALLOW_ORIGINS` if you deploy elsewhere.
