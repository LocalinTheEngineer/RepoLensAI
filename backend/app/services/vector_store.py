"""Uretilen vektorleri saklar ve "en yakin komsu" aramasini yapar.

Qdrant YEREL modda calisir: ayri bir sunucu veya Docker gerekmez, veri
dogrudan diske yazilir. Adim 22'de gercek sunucuya gecmek icin yalnizca
istemcinin kuruldugu satir degisecek:

    QdrantClient(path=...)                     # su anki yerel mod
    QdrantClient(url="http://localhost:6333")  # Docker'daki sunucu

Komutlar ve veri modeli iki modda da aynidir.
"""

from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Filter,
    FilterSelector,
    PointStruct,
    VectorParams,
)

from app.services.chunker import Chunk
from app.services.embedder import EMBEDDING_DIMENSIONS
from app.services.repository import RepositoryError, RepositoryRef

# Veritabani dosyalari backend/qdrant_data/ altinda tutulur.
STORAGE_DIR = Path(__file__).resolve().parents[2] / "qdrant_data"

# Her repository kendi koleksiyonuna yazilir; silmek ve yeniden indekslemek
# boylece kolay olur, repolar birbirine karismaz.
COLLECTION_PREFIX = "repo_"

# Koleksiyon adinda yalnizca harf, rakam ve alt cizgi kullanilabilir.
UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9_]")

# Ayni chunk_id her zaman ayni kimligi uretsin diye sabit bir namespace.
# Boylece yeniden indeksleme kayit eklemez, mevcut kaydin uzerine yazar.
POINT_NAMESPACE = uuid.UUID("6f2a9c74-1f4e-5b8a-9d33-7c1e2b4a6d05")

# Tek seferde Qdrant'a gonderilecek kayit sayisi.
UPSERT_BATCH_SIZE = 128

_client: QdrantClient | None = None
_client_lock = threading.Lock()


@dataclass(frozen=True)
class SearchHit:
    """Aramadan donen tek bir sonuc."""

    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    score: float
    symbol_name: str | None = None
    symbol_type: str | None = None


def get_client() -> QdrantClient:
    """Qdrant istemcisini ilk kullanimda acar ve bellekte tutar.

    Yerel mod veri klasorunu kilitler; ayni klasoru ikinci bir islem acamaz.
    Bu yuzden istemci tek bir kez olusturulur.
    """
    global _client

    if _client is None:
        with _client_lock:
            if _client is None:
                STORAGE_DIR.mkdir(parents=True, exist_ok=True)
                try:
                    _client = QdrantClient(path=str(STORAGE_DIR))
                except Exception as error:
                    raise RepositoryError(
                        "Vektor veritabani acilamadi. Baska bir islem "
                        f"{STORAGE_DIR} klasorunu kullaniyor olabilir.",
                        status_code=503,
                    ) from error

    return _client


def collection_name(ref: RepositoryRef) -> str:
    """Repository icin koleksiyon adi uretir: repo_owner_name."""
    owner = UNSAFE_NAME_CHARS.sub("_", ref.owner)
    name = UNSAFE_NAME_CHARS.sub("_", ref.name)
    return f"{COLLECTION_PREFIX}{owner}_{name}"


def point_id(chunk_id: str) -> str:
    """chunk_id'den her zaman ayni kimligi uretir.

    Qdrant kimlik olarak sayi veya UUID ister; bizim chunk_id'miz
    "src/flask/app.py:1-120" gibi bir metin. uuid5 ayni metinden her zaman
    ayni UUID'yi uretir, bu da yeniden indekslemeyi guvenli kilar.
    """
    return str(uuid.uuid5(POINT_NAMESPACE, chunk_id))


def ensure_collection(ref: RepositoryRef, reset: bool = False) -> str:
    """Repository icin koleksiyonu olusturur.

    reset=True ise once mevcut koleksiyonu siler. Indeksleme her zaman
    reponun TAMAMINI isledigi icin bu dogru davranistir: parcalama yontemi
    degistiginde (orn. satir tabanlidan AST'ye gecis) eski parcalar farkli
    chunk_id tasir ve silinmezse veritabaninda oluru kalirdi.

    Adim 19'da (incremental indexing) yalnizca degisen dosyalari guncelleyen
    bir yol eklenecek; o zaman bu sifirlama secenege baglanacak.

    DIKKAT: Qdrant yerel modunda `delete_collection()` yeterli DEGILDIR.
    Koleksiyonu kayittan dusuruyor (`collection_exists` False donuyor) ama
    diskteki veriyi silmiyor; yeniden olusturuldugunda eski kayitlar geri
    geliyor. Bu yuzden noktalari bos filtreyle tek tek siliyoruz.
    """
    client = get_client()
    name = collection_name(ref)

    if reset and client.collection_exists(name):
        client.delete(
            collection_name=name,
            points_selector=FilterSelector(filter=Filter()),
        )
        return name

    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=EMBEDDING_DIMENSIONS,
                # Vektorleri normalize ettigimiz icin kosinus mesafesi kullaniyoruz.
                distance=Distance.COSINE,
            ),
        )

    return name


def store_chunks(
    ref: RepositoryRef, chunks: list[Chunk], vectors: list[list[float]]
) -> int:
    """Parcalari ve vektorlerini veritabanina yazar.

    Metadata olarak file_path, start_line, end_line ve content saklanir;
    arama sonucunda kaynak gosterebilmemiz bunlara bagli.
    """
    if len(chunks) != len(vectors):
        raise RepositoryError(
            "Parca sayisi ile vektor sayisi ayni olmali.", status_code=500
        )

    client = get_client()
    # Tam yeniden indeksleme: eski parcalar kalmasin.
    name = ensure_collection(ref, reset=True)

    points = [
        PointStruct(
            id=point_id(chunk.chunk_id),
            vector=vector,
            payload={
                "chunk_id": chunk.chunk_id,
                "file_path": chunk.file_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content": chunk.content,
                "symbol_name": chunk.symbol_name,
                "symbol_type": chunk.symbol_type,
            },
        )
        for chunk, vector in zip(chunks, vectors)
    ]

    for start in range(0, len(points), UPSERT_BATCH_SIZE):
        client.upsert(
            collection_name=name,
            points=points[start : start + UPSERT_BATCH_SIZE],
        )

    return len(points)


def stored_count(ref: RepositoryRef) -> int:
    """Koleksiyonda kac kayit oldugunu dondurur; koleksiyon yoksa 0."""
    client = get_client()
    name = collection_name(ref)
    if not client.collection_exists(name):
        return 0
    return client.count(collection_name=name, exact=True).count


def search(
    ref: RepositoryRef, query_vector: list[float], limit: int = 5
) -> list[SearchHit]:
    """Sorgu vektorune en yakin kod parcalarini dondurur."""
    client = get_client()
    name = collection_name(ref)

    if not client.collection_exists(name):
        raise RepositoryError(
            "Bu repository henuz indekslenmemis. Once indeksle.",
            status_code=404,
        )

    response = client.query_points(
        collection_name=name,
        query=query_vector,
        limit=limit,
        with_payload=True,
    )

    hits: list[SearchHit] = []
    for point in response.points:
        payload = point.payload or {}
        hits.append(
            SearchHit(
                chunk_id=payload.get("chunk_id", ""),
                file_path=payload.get("file_path", ""),
                start_line=payload.get("start_line", 0),
                end_line=payload.get("end_line", 0),
                content=payload.get("content", ""),
                score=float(point.score),
                symbol_name=payload.get("symbol_name"),
                symbol_type=payload.get("symbol_type"),
            )
        )
    return hits
