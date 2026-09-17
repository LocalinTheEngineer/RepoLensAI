"""Adim 19: hangi commit'in, hangi dosya icerikleriyle en son indekslendigini saklar.

Tek bir JSON dosyasi yeterli - ayri bir veritabani gerekmez, veri kucuk
(dosya basina bir hash) ve tek sorusu var: "bir onceki indeksleme neydi?"
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from app.services.repository import RepositoryRef
from app.services.vector_store import collection_name

# qdrant_data/ ile ayni yerde tutuluyor: ikisi de "bu repo nasil indekslendi"
# durumunun parcasi ve ikisi de .gitignore'da zaten (bkz. backend/qdrant_data/).
STATE_DIR = Path(__file__).resolve().parents[2] / "qdrant_data" / "index_state"


@dataclass(frozen=True)
class IndexState:
    """En son indekslemenin anlik goruntusu."""

    commit: str
    file_hashes: dict[str, str]


def hash_content(text: str) -> str:
    """Bir dosyanin icerigini kisa bir parmak izine cevirir."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _state_path(ref: RepositoryRef) -> Path:
    return STATE_DIR / f"{collection_name(ref)}.json"


def load_state(ref: RepositoryRef) -> IndexState | None:
    """Daha once indekslenmemisse None doner (ilk indeksleme sinyali)."""
    path = _state_path(ref)
    if not path.is_file():
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    return IndexState(commit=data["commit"], file_hashes=data["file_hashes"])


def save_state(ref: RepositoryRef, commit: str, file_hashes: dict[str, str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _state_path(ref).write_text(
        json.dumps({"commit": commit, "file_hashes": file_hashes}, indent=2),
        encoding="utf-8",
    )
