"""Adim 20: indeksleme islerini API isteginden ayirmak.

Roadmap'in onerdigi gibi once en basit yol: FastAPI'nin kendi
BackgroundTasks'i + process-ici bir durum sozlugu. Redis/Celery gibi ayri
bir worker mimarisine gecis ancak birden fazla backend sureci calistiginda
(orn. birden fazla uvicorn worker'i) gerekli olur; tek surecli yerel
kullanimda bu yeterli.

Durumlar: queued, parsing, embedding, ready, failed. Roadmap "cloning"i de
sayiyor ama bu akista repo /index cagrildiginda zaten klonlanmis oluyor -
hic girilmeyen bir durumu tasimak yerine, clone da arka plana alinirsa o gun
eklenir.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Literal

from app.services.ast_chunker import chunk_repository
from app.services.embedder import embed_texts
from app.services.repository import RepositoryRef, repository_path
from app.services.vector_store import store_chunks, stored_count

JobState = Literal["queued", "parsing", "embedding", "ready", "failed"]


@dataclass
class IndexJob:
    state: JobState = "queued"
    error: str | None = None
    chunk_count: int = 0
    stored_count: int = 0
    embed_duration_ms: float = 0.0
    store_duration_ms: float = 0.0


# ponytail: process-ici dict + lock, tek surecli yerel kullanim icin yeterli;
# birden fazla worker sureci calistirilirsa (prod) Redis gibi paylasimli bir
# duruma tasi.
_jobs: dict[str, IndexJob] = {}
_lock = threading.Lock()


def _key(ref: RepositoryRef) -> str:
    return f"{ref.owner}/{ref.name}"


def get_job(ref: RepositoryRef) -> IndexJob | None:
    with _lock:
        return _jobs.get(_key(ref))


def start_job(ref: RepositoryRef) -> IndexJob:
    """Isi 'queued' durumuyla kaydeder. Gercek is `run_job` icinde, arka planda calisir."""
    job = IndexJob(state="queued")
    with _lock:
        _jobs[_key(ref)] = job
    return job


def run_job(ref: RepositoryRef) -> None:
    """BackgroundTasks tarafindan cagrilir: parcala, embed et, kaydet."""
    job = get_job(ref)
    if job is None:
        return

    try:
        job.state = "parsing"
        result = chunk_repository(repository_path(ref))
        job.chunk_count = len(result.chunks)

        job.state = "embedding"
        embed_started = time.perf_counter()
        vectors = embed_texts([chunk.content for chunk in result.chunks])
        job.embed_duration_ms = round((time.perf_counter() - embed_started) * 1000, 1)

        store_started = time.perf_counter()
        store_chunks(ref, result.chunks, vectors)
        job.store_duration_ms = round((time.perf_counter() - store_started) * 1000, 1)

        job.stored_count = stored_count(ref)
        job.state = "ready"
    except Exception as error:  # ponytail: is hicbir sekilde asili/sessiz kalmamali
        job.state = "failed"
        job.error = str(error)
