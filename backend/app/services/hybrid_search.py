"""Hybrid search: anlamsal arama ile kelime aramasini tek listede birlestirir.

Iki yontem farkli seylerde iyi:

  - Anlamsal arama kavrami yakalar. "how does login work" sorgusu, icinde
    "login" kelimesi hic gecmeyen bir `authenticate` fonksiyonunu da bulur.
  - BM25 birebir ismi yakalar. `locate_app` arayan kisi anlamca benzer baska
    bir seyi degil, o fonksiyonun kendisini bulur.

Kullaniciyi ikisi arasinda secim yapmak zorunda birakmak istemiyoruz;
ikisini de calistirip sonuclari birlestiriyoruz.

Neden skorlari toplamiyoruz? Ayni olcekte degiller. Kosinus benzerligi 0-1
arasindadir; BM25 skoru ise sorguya ve koleksiyona gore degisen, ustu acik
bir sayidir. 0.82 ile 14.3'u toplamak anlamsiz olurdu: BM25 her seferinde
digerini ezerdi.

Cozum Reciprocal Rank Fusion (RRF): skorlara degil SIRALARA bakar. Bir parca
bir listede kacinci siradaysa 1/(K + sira) kadar puan alir, iki listede birden
cikiyorsa iki puani toplanir. Boylece olcek sorunu ortadan kalkar ve "her iki
yontemin de buldugu" parcalar dogal olarak one gecer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.services.embedder import embed_query
from app.services.keyword_search import search as search_keywords
from app.services.repository import RepositoryRef
from app.services.vector_store import SearchHit
from app.services.vector_store import search as search_vectors

# RRF'in yumusatma sabiti. Bolende siraya eklenir: buyudukce ilk siralarin
# avantaji azalir, yani 1. sira ile 5. sira arasindaki fark kapanir. 60
# degeri yontemi oneren calismadan gelir ve pratikte iyi bir baslangictir.
RRF_K = 60

# Birlestirmeden once her yontemden kac aday cekilecek. Nihai limitten cok
# daha fazlasini istiyoruz: bir yontemin 12. sirasindaki parca, digerinin
# 3. sirasindaysa birlesimde one cikabilmeli. Listeyi kisa tutarsak bu
# parcayi hic gormeyiz.
CANDIDATE_LIMIT = 20


@dataclass
class _Candidate:
    """Birlestirme sirasinda bir parcanin biriken durumu.

    Ayni parca iki listede de cikabilir; puani toplanir, her iki listedeki
    sirasi da saklanir (sonucta "bunu hangi yontem buldu" diye gosterecegiz).
    """

    hit: SearchHit
    score: float = 0.0
    vector_rank: int | None = None
    keyword_rank: int | None = None


def best_rank(candidate: _Candidate) -> int:
    """Parcanin iki listedeki en iyi (en kucuk) sirasi.

    Esit RRF puanlarinda siralamayi belirlemek icin kullanilir.
    """
    ranks = [
        rank
        for rank in (candidate.vector_rank, candidate.keyword_rank)
        if rank is not None
    ]
    return min(ranks) if ranks else CANDIDATE_LIMIT + 1


def fuse(
    vector_hits: list[SearchHit],
    keyword_hits: list[SearchHit],
    limit: int = 5,
) -> list[SearchHit]:
    """Iki sonuc listesini RRF ile tek siralamada birlestirir.

    Donen parcalarin `score` alani artik kosinus benzerligi veya BM25 skoru
    degil, RRF puanidir; yalnizca ayni sorgu icindeki parcalari birbiriyle
    karsilastirmak icin anlamlidir.
    """
    candidates: dict[str, _Candidate] = {}

    for rank, hit in enumerate(vector_hits, start=1):
        entry = candidates.setdefault(hit.chunk_id, _Candidate(hit=hit))
        entry.vector_rank = rank
        entry.score += 1 / (RRF_K + rank)

    for rank, hit in enumerate(keyword_hits, start=1):
        entry = candidates.setdefault(hit.chunk_id, _Candidate(hit=hit))
        entry.keyword_rank = rank
        entry.score += 1 / (RRF_K + rank)

    # Puani buyuk olan once. Esitlik halinde once en iyi siraya, o da esitse
    # chunk_id'ye bakariz; boylece ayni sorgu her calistiginda ayni sirayi
    # uretir (rastgelelik yok).
    ordered = sorted(
        candidates.values(),
        key=lambda candidate: (
            -candidate.score,
            best_rank(candidate),
            candidate.hit.chunk_id,
        ),
    )

    return [
        replace(
            candidate.hit,
            score=candidate.score,
            vector_rank=candidate.vector_rank,
            keyword_rank=candidate.keyword_rank,
        )
        for candidate in ordered[:limit]
    ]


def search(ref: RepositoryRef, query: str, limit: int = 5) -> list[SearchHit]:
    """Sorguyu iki yontemle birden arar ve birlesik sonucu dondurur."""
    query_vector = embed_query(query)

    vector_hits = search_vectors(ref, query_vector, limit=CANDIDATE_LIMIT)
    keyword_hits = search_keywords(ref, query, limit=CANDIDATE_LIMIT)

    return fuse(vector_hits, keyword_hits, limit=limit)
