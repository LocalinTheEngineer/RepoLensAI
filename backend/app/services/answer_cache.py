"""Ayni soru ikinci kez sorulunca LLM'i tekrar calistirmayan onbellek.

Bir cevap uretmek retrieval + rerank + model cagrisi demek; en pahali kismi
model cagrisi ve pahali olan sey para degil KOTA. Ayni soruyu tekrar sormak
(demo sirasinda, ekran goruntusu alirken, sayfayi yenilerken) bunu bos yere
harciyordu.

Onbellek repository degistiginde gecersiz olmali: yeniden indeksleme sonrasi
eski cevap artik yanlis parcalara dayaniyor olabilir. `vector_store` yazma
islemlerinde bizi cagirir - BM25 indeksi icin zaten yaptigi seyin aynisi.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

from app.services.repository import RepositoryRef

# ponytail: sinirsiz buyumemesi icin basit bir LRU; sayfa yenilemeleri ve
# demo tekrarlari icin fazlasiyla yeterli, daha fazlasi gerekirse Redis.
MAX_ENTRIES = 64

_entries: OrderedDict[tuple, Any] = OrderedDict()
_lock = threading.Lock()


def _key(ref: RepositoryRef, *parts: Any) -> tuple:
    return (ref.owner, ref.name, *parts)


def get(ref: RepositoryRef, *parts: Any) -> Any | None:
    """Onbellekteki cevabi verir; yoksa None."""
    with _lock:
        key = _key(ref, *parts)
        if key not in _entries:
            return None
        _entries.move_to_end(key)
        return _entries[key]


def put(ref: RepositoryRef, *parts: Any, value: Any) -> None:
    """Cevabi onbellege koyar, en eskiyi gerekirse atar."""
    with _lock:
        _entries[_key(ref, *parts)] = value
        _entries.move_to_end(_key(ref, *parts))
        while len(_entries) > MAX_ENTRIES:
            _entries.popitem(last=False)


def invalidate(ref: RepositoryRef) -> None:
    """Repository yeniden indekslendiginde o repoya ait cevaplari atar."""
    with _lock:
        for key in [k for k in _entries if k[0] == ref.owner and k[1] == ref.name]:
            del _entries[key]


def clear() -> None:
    """Tumunu atar - testler icin."""
    with _lock:
        _entries.clear()
