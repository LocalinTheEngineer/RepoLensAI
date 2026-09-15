# RepoLens AI

**AI-Powered Repository Intelligence & Codebase Q&A**

Ask questions about any public GitHub repository and get answers grounded in the
actual source code, with file paths and line numbers cited as evidence.

```text
GitHub repo -> filter files -> chunk code -> embeddings -> vector DB
            -> retrieve relevant chunks -> LLM answer + citations
```

Instead of a generic AI response, RepoLens answers like this:

```text
Authentication is implemented using JWT based authentication.
The login flow starts in AuthController, where credentials are
forwarded to AuthService.

Sources:
  backend/auth/AuthController.java:31-62
  backend/security/JwtAuthenticationFilter.java:27-81
```

## Status

Early development. Currently at **Step 1 of 25**: project skeleton — the React
frontend talks to the FastAPI backend over a `/health` endpoint.
See [CLAUDE.md](CLAUDE.md) for the full step-by-step status list.

## Tech Stack

| Layer     | Technology                     |
| --------- | ------------------------------ |
| Backend   | Python, FastAPI, Uvicorn       |
| Frontend  | React, TypeScript, Vite        |
| Planned   | Qdrant, Tree-sitter, Docker    |

## Project Structure

```text
RepoLensAI/
├── backend/            # Python + FastAPI API
│   ├── app/
│   │   └── main.py     # App entry point, /health endpoint
│   └── requirements.txt
├── frontend/           # React + TypeScript (Vite)
├── docs/               # Design document & development roadmap
├── CLAUDE.md           # Working notes and conventions
└── README.md
```

## Getting Started

### Requirements

- Python 3.11+
- Node.js 18+
- Git

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Runs at `http://127.0.0.1:8000` — interactive API docs at `/docs`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Runs at `http://localhost:5173`. Start the backend first, or the page will
show a connection error.

## Roadmap

| Phase | Steps | Focus                                                  |
| ----- | ----- | ------------------------------------------------------ |
| 1     | 1–8   | Working core: clone -> index -> semantic search -> RAG |
| 2     | 9–16  | Quality: citations, Tree-sitter, hybrid search, evals  |
| 3     | 17–24 | Productization: overview, tests, Docker, deploy        |
| 4     | 25    | Multi-step repository agent                            |

Full roadmap in [`docs/`](docs/).

## License

Not yet chosen.
