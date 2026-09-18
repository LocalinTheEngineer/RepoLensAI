"""Bulunan kod parcalarindan LLM ile cevap uretir (RAG'in "G" kismi).

RAG = Retrieval Augmented Generation:
  Retrieval  -> vector_store.search()  (ilgili kod parcalarini bul)
  Augmented  -> bu parcalari prompt'a koy
  Generation -> LLM yalnizca bu parcalara dayanarak cevap yazsin

En kritik kural prompt icindedir: model yalnizca verilen koddan cevaplar,
kanit bulamazsa uydurmak yerine bulamadigini soyler.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.services.repository import RepositoryError, RepositoryRef
from app.services.vector_store import SearchHit

# .env dosyasinin yolunu ACIKCA veriyoruz. Parametresiz load_dotenv() dosyayi
# cagiran kodun konumundan yukari dogru arar; bu her ortamda calismaz.
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_PATH)

# Model adi .env'den degistirilebilir; varsayilan calistigi dogrulanmis model.
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Ucretsiz katmanda modeller zaman zaman "503 yogun" dondurur. Bu gecici bir
# kapasite sorunudur ve modele gore degisir; ana model mesgulse sirayla
# yedeklere geciyoruz.
FALLBACK_MODELS = [
    model.strip()
    for model in os.getenv(
        "GEMINI_FALLBACK_MODELS", "gemini-3.1-flash-lite,gemini-3.8-flash"
    ).split(",")
    if model.strip()
]

# Cevabin uzamasini sinirla; uzun cevap genelde savrulma demek.
MAX_OUTPUT_TOKENS = 1200

# 0.0 = en tutarli/tahmin edilebilir. Kaynakli cevapta yaraticilik istemiyoruz.
TEMPERATURE = 0.0

SYSTEM_PROMPT = """You are a code analysis assistant for a specific GitHub repository.

Follow these rules strictly:

1. Answer ONLY from the code excerpts given to you. Do not use general knowledge
   about the library, framework or language, even if you are confident.
2. If the excerpts do not contain enough evidence, say plainly that you could not
   find enough evidence in the indexed code, and stop. Never guess.
3. Never invent file paths, function names, class names or line numbers. Only
   mention identifiers that literally appear in the excerpts.
4. Be concrete and brief. Describe the actual mechanism, not generalities.
5. Every answer that describes code MUST contain at least one citation written
   as `path:start-end`. You may narrow the range to the exact lines you mean,
   but the range must stay INSIDE the excerpt's own range. Never cite a line
   number outside the excerpts you were given. (The only answer allowed with
   no citation is the one where you report finding no evidence.)
6. Answer in English."""

_client: genai.Client | None = None
_client_lock = threading.Lock()


@dataclass(frozen=True)
class Answer:
    """Uretilen cevap ve kullanilan kaynaklar."""

    text: str
    model: str


def is_retriable_error(error: Exception) -> bool:
    """Baska bir modelle tekrar denemeye deger bir hata mi?

    503 = model su an yogun (gecici kapasite sorunu).
    429 = istek siniri; ucretsiz katmanda limitler MODEL BASINA ayri tutulur,
          bu yuzden baska bir model calisabiliyor.
    """
    message = str(error)
    return any(
        kod in message
        for kod in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED")
    )


def get_client() -> genai.Client:
    """Gemini istemcisini ilk kullanimda olusturur ve bellekte tutar."""
    global _client

    if _client is None:
        with _client_lock:
            if _client is None:
                api_key = os.getenv("GEMINI_API_KEY", "").strip()
                if not api_key:
                    raise RepositoryError(
                        "GEMINI_API_KEY bulunamadi. backend/.env dosyasini "
                        "olusturup anahtarini yazdin mi?",
                        status_code=503,
                    )
                _client = genai.Client(api_key=api_key)

    return _client


def build_prompt(question: str, hits: list[SearchHit]) -> str:
    """Kod parcalarini ve soruyu tek bir metne donusturur.

    Her parcanin basligi dosya yolu ve satir araligidir; modelin kaynak
    gosterirken uyduramamasi icin bu bilgiyi aynen kopyalamasini istiyoruz.
    """
    bolumler = []
    for index, hit in enumerate(hits, start=1):
        # Parca bir fonksiyon/class ise adini da baslikta veriyoruz.
        # Modelin "neye baktigini" bilmesi cevabin isabetini artirir.
        etiket = ""
        if hit.symbol_name:
            etiket = f" ({hit.symbol_type or 'symbol'} {hit.symbol_name})"

        bolumler.append(
            f"--- Excerpt {index}: "
            f"{hit.file_path}:{hit.start_line}-{hit.end_line}{etiket} ---\n"
            f"{hit.content}"
        )

    excerpts = "\n\n".join(bolumler) if bolumler else "(no excerpts found)"

    return (
        f"Code excerpts from the repository:\n\n{excerpts}\n\n"
        f"Question: {question}"
    )


def describe_api_failure(error: Exception) -> tuple[str, int]:
    """Gemini hatasini kullanicinin anlayacagi mesaja cevirir."""
    message = str(error)

    if "429" in message or "RESOURCE_EXHAUSTED" in message:
        return (
            "Istek siniri asildi. Ucretsiz katmanda dakikada sinirli sayida "
            "soru sorulabilir; bir dakika bekleyip tekrar dene.",
            429,
        )
    if "503" in message or "UNAVAILABLE" in message:
        return (
            "Model su an yogun. Birkac saniye sonra tekrar dene.",
            503,
        )
    if "404" in message or "NOT_FOUND" in message:
        return (
            f"'{MODEL_NAME}' modeli bulunamadi. backend/.env icindeki "
            "GEMINI_MODEL ayarini kontrol et.",
            502,
        )
    if "401" in message or "403" in message or "PERMISSION" in message:
        return (
            "API anahtari reddedildi. backend/.env icindeki GEMINI_API_KEY "
            "dogru mu?",
            502,
        )

    return ("Cevap uretilemedi. Daha sonra tekrar dene.", 502)


def generate_answer(
    ref: RepositoryRef, question: str, hits: list[SearchHit]
) -> Answer:
    """Verilen kod parcalarina dayanarak soruyu cevaplar."""
    if not hits:
        return Answer(
            text=(
                "I could not find any relevant code in the indexed repository "
                f"({ref.owner}/{ref.name}) for this question."
            ),
            model=MODEL_NAME,
        )

    client = get_client()
    prompt = build_prompt(question, hits)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    last_error: Exception | None = None

    # Once ana model, mesgulse sirayla yedekler.
    for model_name in [MODEL_NAME, *FALLBACK_MODELS]:
        try:
            response = client.models.generate_content(
                model=model_name, contents=prompt, config=config
            )
        except Exception as error:
            last_error = error
            if is_retriable_error(error):
                continue  # bu model yogun, sonrakini dene
            message, status_code = describe_api_failure(error)
            raise RepositoryError(message, status_code=status_code) from error

        text = (response.text or "").strip()
        if text:
            return Answer(
                text=text,
                model=model_name,
            )

        last_error = RuntimeError("bos cevap")

    # Butun modeller denendi, hicbiri cevap veremedi.
    if last_error is not None and is_retriable_error(last_error):
        raise RepositoryError(
            "Denenen modellerin hepsi su an mesgul ya da istek sinirina "
            "takildi. Birkac dakika bekleyip tekrar dene.",
            status_code=503,
        ) from last_error

    raise RepositoryError(
        "Model bos cevap dondurdu. Tekrar dene.", status_code=502
    )
