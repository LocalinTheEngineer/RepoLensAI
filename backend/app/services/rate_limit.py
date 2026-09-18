"""LLM cagiran endpointler icin hiz siniri.

Sinir IP basina degil GLOBAL: kisitli kaynak sunucunun CPU'su degil, Gemini
kotasi. Tek kullanici bile bunu bitirebiliyor - bir agent arastirmasi tek
soruda ona yakin model cagrisi yapiyor, ve kota dolunca sistem 429 yiyip
kullanilamaz hale geliyor.

Kayan pencere: son `WINDOW_SECONDS` icindeki cagri zamanlari tutulur, pencere
disinda kalanlar dusulur. Sayac bellekte durur; tek surecli calisma icin
yeterli.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from app.services.repository import RepositoryError

# Pencere uzunlugu ve bu pencerede izin verilen LLM cagrisi sayisi.
# Gemini'nin ucretsiz katmani dakikada sinirli istek veriyor; buradaki sinir
# ondan onde davranip anlasilir bir hata dondurmeyi amacliyor.
WINDOW_SECONDS = 60.0
MAX_CALLS_PER_WINDOW = 10

_calls: deque[float] = deque()
_lock = threading.Lock()


def _prune(now: float) -> None:
    while _calls and now - _calls[0] >= WINDOW_SECONDS:
        _calls.popleft()


def check() -> None:
    """Bir LLM cagrisi icin izin ister; sinir asildiysa hata firlatir."""
    now = time.monotonic()

    with _lock:
        _prune(now)

        if len(_calls) >= MAX_CALLS_PER_WINDOW:
            bekleme = WINDOW_SECONDS - (now - _calls[0])
            raise RepositoryError(
                f"Dakikada en fazla {MAX_CALLS_PER_WINDOW} soru sorulabilir "
                f"(model kotasini korumak icin). {bekleme:.0f} saniye sonra "
                "tekrar dene.",
                status_code=429,
            )

        _calls.append(now)


def reset() -> None:
    """Sayaci sifirlar - testler icin."""
    with _lock:
        _calls.clear()
