"""Adim 19: repository'yi bastan degil, yalnizca degisen dosyalarla gunceller.

Akis:
  1. klonu en son commit'e guncelle (`pull_latest`)
  2. commit onceki indekslemeyle AYNIYSA hicbir sey yapma (erken cikis)
  3. degilse: mevcut dosyalarin icerik hash'lerini son indekslemedekiyle
     karsilastir -> eklenen / degisen / silinen dosya listesi
  4. eklenen ve degisen dosyalari yeniden parcala, embed et, upsert et
  5. degisen ve silinen dosyalarin ESKI parcalarini Qdrant'tan sil
  6. yeni durumu (commit + hash'ler) kaydet

Neden `git diff <eski>..<yeni>` degil de icerik hash'i? Repo `--depth 1` ile
(shallow) klonlaniyor; bir sonraki `git fetch --depth 1` gecmisi yeni ucun
gerisine tasir ve eski commit'in nesneleri her zaman erisilebilir kalmayabilir.
Dosya icerigini hash'leyip karsilastirmak, klonun derinligine bagli olmadigi
icin daha saglam bir sonuc verir; maliyeti de zaten okunan dosyalari bir kez
daha taramaktan ibarettir.

Ilk indeksleme (daha once hic state yoksa) tam indekslemeye esdegerdir -
karsilastiracak bir onceki durum olmadigi icin butun dosyalar "eklenmis"
sayilir ve mevcut `store_chunks` (full reset) yolu kullanilir.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.services.ast_chunker import chunk_source
from app.services.chunker import Chunk
from app.services.embedder import embed_texts
from app.services.file_scanner import read_text_file, scan_repository
from app.services.index_state import IndexState, hash_content, load_state, save_state
from app.services.repository import RepositoryRef, pull_latest, repository_path
from app.services.vector_store import delete_file_chunks, store_chunks, upsert_chunks


@dataclass
class ReindexResult:
    """Bir guncelleme calismasinin ozeti."""

    previous_commit: str | None
    commit: str
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unchanged_count: int = 0
    chunk_count: int = 0
    embed_ms: float = 0.0
    store_ms: float = 0.0


def diff_files(
    old_hashes: dict[str, str], new_hashes: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """(added, modified, deleted) - saf fonksiyon, kolayca test edilebilir."""
    added = sorted(path for path in new_hashes if path not in old_hashes)
    modified = sorted(
        path
        for path in new_hashes
        if path in old_hashes and old_hashes[path] != new_hashes[path]
    )
    deleted = sorted(path for path in old_hashes if path not in new_hashes)
    return added, modified, deleted


def reindex_repository(ref: RepositoryRef) -> ReindexResult:
    """Repository'yi gunceller ve yalnizca degisen dosyalari yeniden indeksler."""
    path = repository_path(ref)
    previous_state = load_state(ref)

    new_commit = pull_latest(path)

    if previous_state is not None and new_commit == previous_state.commit:
        return ReindexResult(
            previous_commit=previous_state.commit,
            commit=new_commit,
            unchanged_count=len(previous_state.file_hashes),
        )

    scan = scan_repository(path)
    contents: dict[str, str] = {}
    for item in scan.selected:
        text = read_text_file(path / item.path)
        if text is not None:
            contents[item.path] = text

    new_hashes = {file_path: hash_content(text) for file_path, text in contents.items()}

    if previous_state is None:
        return _full_index(ref, new_commit, contents, new_hashes)
    return _incremental_index(ref, previous_state, new_commit, contents, new_hashes)


def _full_index(
    ref: RepositoryRef,
    commit: str,
    contents: dict[str, str],
    new_hashes: dict[str, str],
) -> ReindexResult:
    """Ilk indeksleme: her dosya "eklenmis" sayilir, mevcut tam-indeksleme yolu kullanilir."""
    chunks: list[Chunk] = []
    for file_path, text in contents.items():
        chunks.extend(chunk_source(file_path, text))

    embed_started = time.perf_counter()
    vectors = embed_texts([chunk.content for chunk in chunks])
    embed_ms = (time.perf_counter() - embed_started) * 1000

    store_started = time.perf_counter()
    store_chunks(ref, chunks, vectors)
    store_ms = (time.perf_counter() - store_started) * 1000

    save_state(ref, commit, new_hashes)
    return ReindexResult(
        previous_commit=None,
        commit=commit,
        added=sorted(contents),
        chunk_count=len(chunks),
        embed_ms=round(embed_ms, 1),
        store_ms=round(store_ms, 1),
    )


def _incremental_index(
    ref: RepositoryRef,
    previous_state: IndexState,
    commit: str,
    contents: dict[str, str],
    new_hashes: dict[str, str],
) -> ReindexResult:
    added, modified, deleted = diff_files(previous_state.file_hashes, new_hashes)

    embed_ms = 0.0
    store_started = time.perf_counter()
    for file_path in modified + deleted:
        delete_file_chunks(ref, file_path)
    store_ms = (time.perf_counter() - store_started) * 1000

    chunks: list[Chunk] = []
    for file_path in added + modified:
        chunks.extend(chunk_source(file_path, contents[file_path]))

    if chunks:
        embed_started = time.perf_counter()
        vectors = embed_texts([chunk.content for chunk in chunks])
        embed_ms = (time.perf_counter() - embed_started) * 1000

        upsert_started = time.perf_counter()
        upsert_chunks(ref, chunks, vectors)
        store_ms += (time.perf_counter() - upsert_started) * 1000

    save_state(ref, commit, new_hashes)
    return ReindexResult(
        previous_commit=previous_state.commit,
        commit=commit,
        added=added,
        modified=modified,
        deleted=deleted,
        unchanged_count=len(new_hashes) - len(added) - len(modified),
        chunk_count=len(chunks),
        embed_ms=round(embed_ms, 1),
        store_ms=round(store_ms, 1),
    )


def _demo() -> None:
    """diff_files'in saf mantigini gercek dosya sistemine dokunmadan dogrular."""
    old = {"a.py": "h1", "b.py": "h2", "c.py": "h3"}
    new = {"a.py": "h1", "b.py": "h2-changed", "d.py": "h4"}

    added, modified, deleted = diff_files(old, new)
    assert added == ["d.py"], added
    assert modified == ["b.py"], modified
    assert deleted == ["c.py"], deleted

    # Hicbir sey degismemis: uc liste de bos.
    added, modified, deleted = diff_files(old, dict(old))
    assert (added, modified, deleted) == ([], [], [])

    print("incremental_index: tum kontroller gecti")


if __name__ == "__main__":
    _demo()
