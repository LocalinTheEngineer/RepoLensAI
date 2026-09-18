# Decisions

Why this is built the way it is. Every number here came from
`backend/eval/`, measured on one laptop CPU against
[pallets/flask](https://github.com/pallets/flask); none of it is estimated.

## Why RAG instead of fine-tuning

The question is always about *this* repository, and the repository changes.
Fine-tuning a model on a codebase means retraining it every time someone
merges, and the result still can't tell you which file it got an answer from.

Retrieval keeps the code outside the model. The repo is indexed once, changed
files are re-indexed on the next commit, and the answer is assembled from
chunks that were actually retrieved — so every claim has a file and a line
range attached to it, and you can go check.

The cost is that the answer is only as good as the retrieval. That's why most
of the work here went into retrieval quality rather than prompt wording.

## Why Qdrant

It runs embedded. `QdrantClient(path=...)` writes to a local folder with no
server, no Docker, no connection string — so a clone of this repo runs after
`pip install`, which matters more than throughput at this size.

The same client speaks to a real server, so the Compose setup flips it with one
environment variable (`QDRANT_URL`) and nothing else in the code changes.

pgvector would have meant running Postgres from day one. FAISS has no metadata
filtering worth the name, and every chunk here carries a file path and line
range that has to come back with the hit.

The embedded mode has a real limit worth naming: it locks the storage folder,
so exactly one process can hold it. That's why the integration test redirects
`STORAGE_DIR` to a temp folder and closes the client before cleanup.

## Why Tree-sitter

The first version cut files every 120 lines. That splits functions in half, and
half a function retrieved as evidence is worse than useless — it reads as if
the rest doesn't exist.

Tree-sitter parses the file and cuts on function, class and method boundaries
instead, so a retrieved chunk is a whole unit of code with a name attached.
The name is worth as much as the boundary: `symbol_name` gets weighted in the
BM25 index, which is how searching `locate_app` finds the function rather than
the tests that mention it.

Unsupported extensions (`.md`, anything without a grammar) fall back to the
line-based chunker rather than being dropped.

## Why hybrid retrieval

Embedding search matches meaning and misses exact names. BM25 matches exact
names and misses meaning. Measured separately on the same 71 questions, they
score almost identically — and they fail on *different* questions:

| retrieval | Recall@1 | Recall@3 | Recall@5 | MRR | ms/question |
|---|---|---|---|---|---|
| semantic only | 67.6% | 90.1% | 98.6% | 0.801 | 9 |
| BM25 only | 69.0% | 91.5% | 95.8% | 0.802 | 1 |
| hybrid (RRF) | 73.2% | 98.6% | 100% | 0.848 | 11 |
| hybrid + rerank | 76.1% | 98.6% | 100% | 0.864 | 960 |

Combining them is the cheapest win in the project: +4 points of Recall@1,
+8 of Recall@3, for two milliseconds.

They're merged with Reciprocal Rank Fusion rather than by adding scores,
because the scores aren't on the same scale — cosine similarity lives in 0–1
and BM25 is an open-ended positive number, so summing them lets BM25 dominate
by accident. RRF only looks at positions, which sidesteps the problem
entirely, and a chunk both methods ranked well naturally rises.

## Why the reranker is optional

A cross-encoder reads the question and the chunk together instead of comparing
two independently-built vectors, and it does rank better: 76.1% vs 73.2% at
Recall@1.

It also costs 960 ms per question against 11 ms, and the aggregate hides the
interesting part. Per category it isn't uniformly better — it takes `logging`
from 0% to 100% and `testing` from 50% to 100%, and drags `cli` from 86% down
to 57% and `routing` from 88% to 75%. Best guess: it's trained on MS MARCO web
text, so it rewards prose-heavy docstrings over dense code.

So it runs by default where a second doesn't matter (`/ask`, where the LLM
takes longer anyway) and is a checkbox where it would be felt (`/search`).

## Why citations are verified instead of trusted

The model is told to cite what it used, and models will happily cite a file
they were never shown. Every `path.py:12-40` in the answer is parsed out and
checked against the chunks that were actually in the prompt, and comes back as
`verified`, `out_of_range`, or `unknown_file`.

The refusal behaviour is tested rather than assumed: 18 questions about things
Flask does not contain (Redis, GraphQL, an ORM, OAuth2) run through real
retrieval and the real model, and all 18 came back saying the evidence wasn't
there.

## Why re-indexing hashes files instead of diffing commits

Repos are cloned shallow (`--depth 1`), and `git diff old..new` isn't reliable
after a shallow fetch — the old commit's objects may simply not be there.

Hashing each file's contents and comparing against the previous run's hashes
gives the same added/modified/deleted split without depending on clone depth.

## Why the limits are global rather than per user

There's no auth and no tenants, so the thing worth protecting isn't a user's
share of the server — it's the model quota, which is one pool for everyone.
A per-IP limiter would let a single client burn it anyway, so the cap counts
calls globally in a sliding minute.

The answer cache works the same way: keyed by repository and question, cleared
whenever that repository is written to, so a stale index can't serve a stale
answer.

## Why secret-scanning skips whole files

Anything indexed gets embedded, stored, and eventually pasted into a prompt. A
leaked key travelling that path is worse than a missing file, so a file with an
obvious secret is dropped at scan time and reported with the other skip
reasons.

The patterns are deliberately narrow — provider prefixes like `AKIA`, `ghp_`,
`AIza`, and private-key headers — with no "looks like a password" heuristic. A
false positive would silently drop real source code and the answer would get
worse for a reason nobody could see.

## Why background jobs are a dict and not Celery

Indexing Flask takes about 40 seconds, which is too long to hold a request
open, so it moved to FastAPI's `BackgroundTasks` with job state in a plain
dict behind a lock, and the UI polls for it.

That state dies with the process and doesn't survive multiple workers. Redis
and a real queue are the upgrade path when either of those becomes true; today
neither is, and a queue would be one more service to run for no gain.

## What isn't decided yet

**Deployment.** Compose runs everything locally, and the frontend now takes its
API address as a build argument, so nothing in the code pins it to localhost.
What's left is a cost decision: the backend holds two models in memory and
wants ~2 GB of RAM, which is above most free hosting tiers. That's left open
rather than guessed at.

**Non-English questions.** The embedding model is English-only, so questions
have to be English. A multilingual embedding model would fix it and would
require re-indexing everything.

**The evaluation set saturates.** Recall@5 is already 100% for hybrid, so at
k=5 the questions no longer separate the variants. Recall@1 and MRR still do.
Harder questions — or chunk-level labels instead of file-level — are the next
thing that would make the numbers mean more.
