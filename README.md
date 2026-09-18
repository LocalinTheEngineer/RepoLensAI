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
so a retrieved excerpt is a whole unit of code with a name attached. Search
runs both ways at once — by meaning, and by keyword with BM25 for when
you know the exact identifier you want. The two result lists get merged by
rank rather than by score, since a cosine similarity and a BM25 score are not
on the same scale, so a chunk that both methods found rises to the top.

What that produces is a wide pool of candidates, not an answer. A cross-encoder
then reads the question and each candidate together, rather than as two
separate vectors, and scores how well that code answers that question. The
model ends up with five chunks that earned their place instead of twenty that
happened to match.

None of this is taken on faith. `backend/eval/` holds 71 questions about a real
repository, each labelled with the files that actually answer it, and a script
that replays them across every retrieval variant. Searching both ways lifts
Recall@1 from 68 to 73 percent and Recall@3 from 90 to 99, and costs two
milliseconds. The cross-encoder adds three more points and costs about a second
per question, and it is not a clean win: it fixes some categories outright and
makes others worse.

Every `file.py:12-40` reference the model writes is checked against the code
it was actually shown, so a made-up line number gets flagged instead of
quietly trusted.

That flagging is tested directly, not assumed: `backend/eval/` also holds 18
questions about things the indexed repository does not actually have — Redis,
GraphQL, an ORM, OAuth2 — run through the real retrieval and the real model.
All 18 came back saying the evidence wasn't there instead of inventing an
answer.

Before asking anything, the sidebar already shows what got indexed: which
top-level directories the files came from, how many functions and classes
Tree-sitter found, and which files are the largest. Those counts run over
every file and every chunk, not just the slice the UI happens to list.

There's also a file-level dependency graph: which file imports which,
drawn with Cytoscape.js. Python imports are resolved with the standard
`ast` module, relative TypeScript/JavaScript imports with a small regex;
external packages (flask, react, ...) never show up, since they don't
correspond to a file in the repo.

Re-indexing after a commit doesn't start over. It pulls the latest commit,
hashes every file's content, and only re-embeds what actually changed;
a deleted file's old chunks are removed from Qdrant instead of lingering.
If nothing changed, it says so and does no embedding work at all.

Indexing doesn't block the request either. Kicking it off returns immediately
with a job id, the work runs in the background, and the UI polls for the state
it's in — queued, parsing, embedding, ready, failed.

`backend/tests/` holds the checks: unit tests for filtering, chunking, symbol
parsing and citation verification, and one integration test that runs the real
pipeline end to end on a throwaway git repo — index, search, ask — with only
the LLM call faked. `python -m unittest discover tests`.

The whole stack runs with one command. `docker compose up --build` brings up
Qdrant, the API and the built frontend on the same ports the local setup uses,
so nothing in the code has to change between the two. Qdrant switches from
embedded to server mode by an environment variable and nothing else.

Every push runs the checks on GitHub Actions: lint and the full test suite on
the backend, eslint and a type-checked build on the frontend, and both Docker
images built to prove they still build.

Step 24 of 25. Questions have to be in English.

## How it works

```text
GitHub URL
    │
    ├─ clone (shallow)          repository.py
    ├─ pick the files           file_scanner.py     git ls-files, extension + size filters
    ├─ cut into chunks          ast_chunker.py      Tree-sitter: function/class boundaries
    ├─ embed                    embedder.py         all-MiniLM-L6-v2, local, 384 dims
    └─ store                    vector_store.py     Qdrant (embedded, or a server)

question
    │
    ├─ embed ──────┐
    │              ├─ merge by rank (RRF)   hybrid_search.py
    ├─ BM25 ───────┘
    ├─ rerank 20 → 5            reranker.py         ms-marco-MiniLM-L-6-v2 cross-encoder
    ├─ answer from those        answerer.py         Gemini, "cite or say you don't know"
    └─ verify every citation    citations.py        against the chunks actually shown
```

Re-indexing compares file content hashes and only touches what changed;
indexing runs as a background job the UI polls.

## Numbers

71 labelled questions over [pallets/flask](https://github.com/pallets/flask),
scored at file level. Reproduce with `python eval/run_eval.py --index`.

| retrieval | Recall@1 | Recall@3 | Recall@5 | MRR | ms/question |
|---|---|---|---|---|---|
| semantic only | 67.6% | 90.1% | 98.6% | 0.801 | 9 |
| BM25 only | 69.0% | 91.5% | 95.8% | 0.802 | 1 |
| hybrid (RRF) | 73.2% | 98.6% | 100% | 0.848 | 11 |
| hybrid + rerank | 76.1% | 98.6% | 100% | 0.864 | 960 |

Plus 18 questions about things Flask doesn't have: 18/18 refused instead of
inventing an answer.

Measured on one laptop CPU. [DECISIONS.md](DECISIONS.md) explains the
trade-offs behind each of these — including where the reranker makes things
worse.

## Running it

Either way you need a Gemini API key first — the free tier at
[aistudio.google.com](https://aistudio.google.com) is enough and doesn't ask
for a card. Copy `backend/.env.example` to `backend/.env` and put the key in it.

With Docker, that's the only setup step:

```powershell
docker compose up --build
```

Frontend on :5173, API on :8000. The first build is slow (it installs PyTorch);
the first question is slow too, since the models download then.

Without Docker, backend first:

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
Tree-sitter parses the code. Embeddings and reranking both run locally with
sentence-transformers (all-MiniLM-L6-v2 for embeddings, ms-marco-MiniLM-L-6-v2
for reranking), vectors live in Qdrant, and Gemini writes the answers.
Cytoscape.js draws the dependency graph, and Docker Compose runs the lot.
