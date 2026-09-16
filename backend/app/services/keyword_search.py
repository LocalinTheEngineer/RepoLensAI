"""Kelime tabanli (lexical) arama: BM25.

Anlamsal arama kavram eslestirir ama BIREBIR isim aramaz. Olctuk:
"how does the CLI find the app" sorgusunda ilk 3 sonucun ucu de test
dosyasiydi; gercek `locate_app` fonksiyonu listede yoktu.

BM25 tam tersini yapar: anlamla ilgilenmez, kelimelerin gecip gecmedigine
bakar. `JwtService` arayan kisi o sinifin kendisini bulur.

Kodda ozel bir zorluk var: isimler bitisik yazilir (`JwtService`,
`create_token`). Kullanici ikisini de arayabilmeli, o yuzden hem tam hali
hem parcalari indekslenir.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.services.repository import RepositoryError, RepositoryRef
from app.services.vector_store import SearchHit, collection_name, load_payloads

# Kod icindeki tanimlayicilari yakalar: harf veya alt cizgi ile baslar.
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")

# camelCase / PascalCase sinirlari:
#   JwtService    -> Jwt | Service
#   parseHTTPUrl  -> parse | HTTP | Url
CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# Sembol adi indekste kac kez tekrarlanacak.
# Amac: "locate_app" aramasinda gercek fonksiyonu, adinda ayni kelimeler
# gecen test fonksiyonlarinin onune gecirmek.
SYMBOL_BOOST = 3

# Kurulan indeksler repository basina bellekte tutulur.
_indexes: dict[str, "KeywordIndex"] = {}
_index_lock = threading.Lock()


@dataclass
class KeywordIndex:
    """Bir repository icin kurulmus BM25 indeksi."""

    bm25: BM25Okapi
    payloads: list[dict]


def tokenize(text: str) -> list[str]:
    """Metni BM25'in karsilastirabilecegi kelimelere ayirir.

    Her tanimlayici hem TAM hali hem de parcalariyla eklenir:
        JwtService   -> jwtservice, jwt, service
        create_token -> create_token, create, token

    Boylece kullanici `JwtService` de yazsa `jwt service` de yazsa eslesir.
    """
    tokens: list[str] = []

    for match in IDENTIFIER.finditer(text):
        raw = match.group(0)
        full = raw.lower()
        tokens.append(full)

        # Once alt cizgiden, sonra camelCase sinirlarindan bol.
        for piece in raw.split("_"):
            if not piece:
                continue
            for part in CAMEL_BOUNDARY.split(piece):
                lowered = part.lower()
                if lowered and lowered != full:
                    tokens.append(lowered)

    return tokens


def build_document(payload: dict) -> list[str]:
    """Bir parcadan indekslenecek kelime listesini uretir.

    Dosya yolu ve sembol adi da dahil edilir; sembol adi SYMBOL_BOOST kez
    tekrarlanarak agirliklandirilir.
    """
    parts = [payload.get("file_path", ""), payload.get("content", "")]

    symbol_name = payload.get("symbol_name")
    if symbol_name:
        parts.extend([symbol_name] * SYMBOL_BOOST)

    return tokenize(" ".join(parts))


def build_index(ref: RepositoryRef) -> KeywordIndex:
    """Repository icin BM25 indeksini kurar."""
    payloads = load_payloads(ref)
    if not payloads:
        raise RepositoryError(
            "Bu repository henuz indekslenmemis. Once indeksle.",
            status_code=404,
        )

    documents = [build_document(payload) for payload in payloads]
    return KeywordIndex(bm25=BM25Okapi(documents), payloads=payloads)


def get_index(ref: RepositoryRef) -> KeywordIndex:
    """Indeksi bellekten verir; yoksa kurar.

    Kurmak butun parcalari okuyup kelimelere ayirmayi gerektirir, bu yuzden
    her aramada tekrar yapilmaz.
    """
    key = collection_name(ref)

    if key not in _indexes:
        with _index_lock:
            if key not in _indexes:
                _indexes[key] = build_index(ref)

    return _indexes[key]


def invalidate(ref: RepositoryRef) -> None:
    """Repository yeniden indekslendiginde eski BM25 indeksini atar."""
    key = collection_name(ref)
    with _index_lock:
        _indexes.pop(key, None)


def search(ref: RepositoryRef, query: str, limit: int = 5) -> list[SearchHit]:
    """Sorgudaki kelimeleri iceren kod parcalarini siralar.

    Not: BM25 skorlari kosinus benzerligi gibi 0-1 arasinda DEGILDIR;
    sorguya ve koleksiyona gore degisen pozitif sayilardir. Adim 13'te
    (hybrid search) iki skoru birlestirmeden once normalize edecegiz.
    """
    tokens = tokenize(query)
    if not tokens:
        return []

    index = get_index(ref)
    scores = index.bm25.get_scores(tokens)

    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    hits: list[SearchHit] = []
    for position in order[:limit]:
        score = float(scores[position])
        # Skoru sifir olan parca sorgudaki hicbir kelimeyi icermiyor demektir.
        if score <= 0:
            continue

        payload = index.payloads[position]
        hits.append(
            SearchHit(
                chunk_id=payload.get("chunk_id", ""),
                file_path=payload.get("file_path", ""),
                start_line=payload.get("start_line", 0),
                end_line=payload.get("end_line", 0),
                content=payload.get("content", ""),
                score=score,
                symbol_name=payload.get("symbol_name"),
                symbol_type=payload.get("symbol_type"),
            )
        )

    return hits
