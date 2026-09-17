"""Cross-encoder reranker: LLM'e gitmeden once adaylari yeniden siralar.

Hybrid retrieval hizlidir ama kabadir. Sorguyu ve kod parcasini AYRI AYRI
vektore cevirip vektorleri karsilastirir; yani parca, sorgunun ne sordugunu
hic gormeden puanlanmistir.

Cross-encoder tam tersini yapar: sorgu ile kod parcasini tek bir metin gibi
BIRLIKTE okur ve "bu parca bu soruyu cevapliyor mu" diye tek bir puan uretir.
Cok daha isabetlidir, ama her aday icin modeli bir kez calistirmak gerekir;
butun repository uzerinde bunu yapmak imkansiz olurdu.

Bu yuzden ikisi sirayla kullanilir:

    hybrid ile 20 aday  ->  cross-encoder ile yeniden sirala  ->  en iyi 5

Sonucta LLM'e daha az ama daha alakali context gider.
"""

from __future__ import annotations

import threading
from dataclasses import replace

from sentence_transformers import CrossEncoder

from app.services.repository import RepositoryError
from app.services.vector_store import SearchHit

# MS MARCO uzerinde egitilmis, kucuk ve yerelde calisan bir reranker.
# Ilk kullanimda ~90 MB indirir; sonrasinda onbellekten acilir.
MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Reranker'a kac aday gonderilecek. Yol haritasi 15-30 arasini oneriyor:
# az olursa reranker'in duzeltecek bir seyi kalmaz, cok olursa gecikme artar.
CANDIDATE_LIMIT = 20

# Model tek seferde kac (sorgu, parca) ciftini birlikte isleyecek.
BATCH_SIZE = 16

# Cross-encoder sinirli uzunlukta metin okur, fazlasini kirpar. Cok uzun bir
# parcanin bastan yarisini vermek, tamamini verip modelin kendi kirpmasina
# birakmaktan daha ongorulebilir.
MAX_CONTENT_CHARS = 2000

# Model nesnesi bir kez yuklenir ve bellekte tutulur.
_model: CrossEncoder | None = None
_model_lock = threading.Lock()


def get_model() -> CrossEncoder:
    """Modeli ilk kullanimda yukler, sonrasinda bellekten verir.

    embedder.get_model() ile ayni mantik: acilista degil gerektiginde yukle,
    ayni anda gelen iki istek modeli iki kez yuklemesin diye kilit kullan.
    """
    global _model

    if _model is None:
        with _model_lock:
            # Kilidi beklerken baska bir thread yuklemis olabilir, tekrar bak.
            if _model is None:
                try:
                    _model = CrossEncoder(MODEL_NAME)
                except Exception as online_error:
                    # Model onbellekte olsa bile kutuphane acilista Hugging
                    # Face'e "guncelleme var mi" diye sorar; internet koparsa
                    # bu istek patlar. Onbellekteki kopyayla tekrar dene.
                    try:
                        _model = CrossEncoder(MODEL_NAME, local_files_only=True)
                    except Exception:
                        raise RepositoryError(
                            f"Reranker modeli yuklenemedi ({MODEL_NAME}). "
                            "Model onbellekte de bulunamadi; ilk calistirmada "
                            "indirilmesi icin internet baglantisi gerekir.",
                            status_code=503,
                        ) from online_error

    return _model


def build_document(hit: SearchHit) -> str:
    """Parcayi reranker'a verilecek metne cevirir.

    Ham icerigin basina dosya yolu ve sembol adi eklenir: "bu kod nerede
    yasiyor ve adi ne" bilgisi, modelin alaka kararini belirgin sekilde
    kolaylastirir.
    """
    header = hit.file_path
    if hit.symbol_name:
        header = f"{header} - {hit.symbol_name}"

    return f"{header}\n{hit.content[:MAX_CONTENT_CHARS]}"


def rerank(query: str, hits: list[SearchHit], limit: int = 5) -> list[SearchHit]:
    """Adaylari sorguya gore yeniden puanlar ve en iyi `limit` tanesini verir.

    Donen parcalarin `score` alanina dokunulmaz (retrieval'dan geldigi gibi
    kalir); cross-encoder'in puani ayri bir alanda, `rerank_score` icinde
    durur. Boylece "retrieval ne dedi, reranker ne dedi" karsilastirilabilir.
    """
    if not hits:
        return []

    model = get_model()
    pairs = [(query, build_document(hit)) for hit in hits]

    scores = model.predict(
        pairs,
        batch_size=BATCH_SIZE,
        show_progress_bar=False,
    )

    scored = [
        replace(hit, rerank_score=float(score))
        for hit, score in zip(hits, scores)
    ]

    # Puani buyuk olan once; esitlikte chunk_id ile deterministik siralama.
    scored.sort(key=lambda hit: (-(hit.rerank_score or 0.0), hit.chunk_id))

    return scored[:limit]
