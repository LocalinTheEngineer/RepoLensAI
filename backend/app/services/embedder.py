"""Kod parcalarini ve kullanici sorgularini sayisal vektore cevirir.

Embedding, bir metni sabit uzunlukta bir sayi dizisine donusturmektir.
Anlamca yakin metinler birbirine yakin vektorler uretir; bu sayede
"kullanici girisi" sorgusu ile "def login(...)" kodu eslesebilir.

Model tamamen YERELDE calisir: internet baglantisi yalnizca ilk indirme
icin gerekir, API anahtari veya ucret yoktur.
"""

from __future__ import annotations

import threading

from sentence_transformers import SentenceTransformer

from app.services.repository import RepositoryError

# Kucuk, hizli ve yerelde calisabilen bir model.
# Adim 14'te daha iyi bir modelle degistirilebilir; tek yapilacak bu sabiti
# ve EMBEDDING_DIMENSIONS degerini guncellemek.
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Modelin urettigi vektorun uzunlugu. Adim 6'da Qdrant'a bu deger bildirilecek.
EMBEDDING_DIMENSIONS = 384

# Model tek seferde kac metni birlikte isleyecek.
BATCH_SIZE = 32

# Model nesnesi bir kez yuklenir ve bellekte tutulur.
_model: SentenceTransformer | None = None
_model_lock = threading.Lock()


def get_model() -> SentenceTransformer:
    """Modeli ilk kullanimda yukler, sonrasinda bellekten verir.

    Neden import aninda degil? Model yuklemek saniyeler surer ve birkac yuz MB
    bellek tutar. Sunucu her acildiginda degil, gercekten gerektiginde yuklensin.

    Kilit (lock) neden var? FastAPI normal `def` endpoint'leri ayri thread'lerde
    calistirir. Ayni anda gelen iki istek modeli iki kez yuklemeye calisabilir;
    kilit bunu engeller.
    """
    global _model

    if _model is None:
        with _model_lock:
            # Kilidi beklerken baska bir thread yuklemis olabilir, tekrar bak.
            if _model is None:
                try:
                    _model = SentenceTransformer(MODEL_NAME)
                except Exception as online_error:
                    # Model onbellekte olsa bile sentence-transformers acilista
                    # Hugging Face'e "guncelleme var mi" diye sorar. Internet
                    # koparsa bu istek patlar. Onbellekteki kopyayla tekrar dene.
                    try:
                        _model = SentenceTransformer(
                            MODEL_NAME, local_files_only=True
                        )
                    except Exception:
                        raise RepositoryError(
                            f"Embedding modeli yuklenemedi ({MODEL_NAME}). "
                            "Model onbellekte de bulunamadi; ilk calistirmada "
                            "indirilmesi icin internet baglantisi gerekir.",
                            status_code=503,
                        ) from online_error

    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Birden fazla metni tek seferde vektore cevirir.

    normalize_embeddings=True her vektoru birim uzunluga getirir. Boylece
    iki vektorun nokta carpimi dogrudan kosinus benzerligini verir; Adim 6 ve
    7'de arama yaparken bu isimizi kolaylastiracak.
    """
    if not texts:
        return []

    model = get_model()
    vectors = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [vector.tolist() for vector in vectors]


def embed_query(text: str) -> list[float]:
    """Tek bir kullanici sorgusunu vektore cevirir."""
    return embed_texts([text])[0]


def cosine_similarity(first: list[float], second: list[float]) -> float:
    """Iki vektorun benzerligi: 1.0 tamamen ayni yon, 0.0 alakasiz.

    Vektorler normalize edildigi icin nokta carpimi kosinus benzerligine esittir;
    ayrica bolme islemi yapmaya gerek kalmaz.
    """
    if len(first) != len(second):
        raise ValueError("Vektor boyutlari ayni olmali.")
    return sum(a * b for a, b in zip(first, second))
