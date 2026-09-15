# RepoLens AI

Ask questions about a GitHub repo and get answers that point back at the actual code.

You give it a repository URL, it indexes the source, and when you ask something
like *"how does authentication work here?"* it answers from what is really in the
files — and tells you which ones:

```text
Authentication goes through JWT. The login flow starts in AuthController,
which hands the credentials to AuthService.

  backend/auth/AuthController.java:31-62
  backend/security/JwtAuthenticationFilter.java:27-81
```

So you can go check whether the answer is actually true.

## Where it's at

Early. You can paste a public GitHub URL and the backend clones it, works out
which files are worth processing, and splits them into chunks that carry their
own file path and line range — step 4 of 25. No embeddings or answers yet.

## Running it

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend, in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Backend is on :8000, frontend on :5173. Start the backend first, otherwise the
page just shows a connection error.

## Stack

Python + FastAPI, React + TypeScript on Vite. Qdrant, Tree-sitter and Docker are
in the plan but not in yet.
