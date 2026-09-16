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

The core works end to end: paste a public GitHub URL, it clones the repo,
picks the files worth processing, splits them into chunks that carry their own
file path and line range, embeds them into a vector database, and answers
questions about the code — grounded in the actual files, with the line ranges
it used shown underneath.

If the indexed code doesn't contain the answer, it says so instead of making
one up.

Chunks follow function and class boundaries rather than arbitrary line counts,
so a retrieved excerpt is a whole unit of code with a name attached.

Every `file.py:12-40` reference the model writes is checked against the code
it was actually shown, so a made-up line number gets flagged instead of
quietly trusted.

Step 11 of 25. Questions have to be in English.

## Running it

Backend. You need a Gemini API key first — the free tier at
[aistudio.google.com](https://aistudio.google.com) is enough and doesn't ask
for a card.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then put your key in it
uvicorn app.main:app --reload
```

The first request downloads the embedding model (~90 MB).

Frontend, in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Backend is on :8000, frontend on :5173. Start the backend first, otherwise the
page just shows a connection error.

## Stack

Python + FastAPI on the backend, React + TypeScript on Vite up front.
Embeddings run locally with sentence-transformers (all-MiniLM-L6-v2, 384
dimensions), vectors live in Qdrant, and Gemini writes the answers.
Tree-sitter and Docker are in the plan but not in yet.
