"""LLM cevabindaki kaynak referanslarini bulur ve DOGRULAR.

Yol haritasi Adim 9: "Citation bilgisinin LLM'in uydurmasina izin verme."

Model cevabinda `src/flask/config.py:101-220` gibi referanslar yazar. Bu
referanslarin gercekten kendisine verilen kod parcalarina ait olup olmadigini
kontrol etmezsek, model var olmayan bir dosya veya satir araligi uydurdugunda
kullanici bunu fark edemez.

Model genelde parca sinirlarini aynen kopyalamaz; daha dar ve kesin
araliklar yazar (orn. verilen parca 301-385 iken cevapta 306-311). Bu
DAHA FAYDALIDIR ve mesrudur, cunku o satirlar modele gercekten gosterildi.
Bu yuzden dogrulama "birebir esitlik" degil "KAPSANMA" ile yapilir.

Uc sonuc olabilir:
  verified     -> referans araligi, verilen bir parcanin ICINDE
  out_of_range -> dosya verilmis ama aralik hicbir parcanin icine sigmiyor
                  (model gormedigi satirlara atifta bulunuyor)
  unknown_file -> dosya hic verilmemis (tamamen uydurma)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.vector_store import SearchHit

# "yol/dosya.uzanti:baslangic-bitis" kalibi.
# Uzanti sart; boylece "adim 9:1-3" gibi metinler yanlislikla eslesmez.
CITATION_PATTERN = re.compile(
    r"(?P<path>[A-Za-z0-9_][A-Za-z0-9_./\-]*\.[A-Za-z0-9]+)"
    r":(?P<start>\d+)-(?P<end>\d+)"
)


@dataclass(frozen=True)
class Citation:
    """Cevapta gecen tek bir kaynak referansi ve dogrulama sonucu."""

    file_path: str
    start_line: int
    end_line: int
    status: str
    chunk_id: str | None


def extract_citations(text: str) -> list[tuple[str, int, int]]:
    """Cevap metnindeki tum kaynak referanslarini cikarir.

    Ayni referans birden fazla gecerse bir kez dondurulur; siralama korunur.
    """
    bulunanlar: list[tuple[str, int, int]] = []
    gorulen: set[tuple[str, int, int]] = set()

    for match in CITATION_PATTERN.finditer(text):
        anahtar = (
            match.group("path"),
            int(match.group("start")),
            int(match.group("end")),
        )
        if anahtar not in gorulen:
            gorulen.add(anahtar)
            bulunanlar.append(anahtar)

    return bulunanlar


def find_containing_chunk(
    path: str, start: int, end: int, hits: list[SearchHit]
) -> SearchHit | None:
    """Referans araligini tamamen kapsayan parcayi bulur; yoksa None."""
    for hit in hits:
        if (
            hit.file_path == path
            and hit.start_line <= start
            and end <= hit.end_line
        ):
            return hit
    return None


def verify_citations(text: str, hits: list[SearchHit]) -> list[Citation]:
    """Cevaptaki referanslari, modele verilen kod parcalariyla karsilastirir."""
    verilen_dosyalar = {hit.file_path for hit in hits}

    sonuclar: list[Citation] = []
    for path, start, end in extract_citations(text):
        kapsayan = find_containing_chunk(path, start, end, hits)
        chunk_id = kapsayan.chunk_id if kapsayan else None

        if kapsayan is not None:
            status = "verified"
        elif path in verilen_dosyalar:
            status = "out_of_range"
        else:
            status = "unknown_file"

        sonuclar.append(
            Citation(
                file_path=path,
                start_line=start,
                end_line=end,
                status=status,
                chunk_id=chunk_id,
            )
        )

    return sonuclar


def count_unverified(citations: list[Citation]) -> int:
    """Dogrulanamayan referans sayisi."""
    return sum(1 for c in citations if c.status != "verified")
