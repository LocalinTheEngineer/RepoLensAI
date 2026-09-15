"""Klonlanan repository icinden islenecek kaynak dosyalari secer.

Amac: AI sistemine yalnizca anlamli kaynak kodu ve dokumantasyon vermek.
Binary dosyalar, uretilmis klasorler ve desteklenmeyen uzantilar elenir.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.services.repository import RepositoryError

# Adim 3'te desteklenen uzantilar. Ileride genisletilecek.
ALLOWED_EXTENSIONS = frozenset({".py", ".java", ".js", ".ts", ".tsx", ".md"})

# Bu klasorlerin altindaki hicbir dosya islenmez.
IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".github",
        "node_modules",
        "dist",
        "build",
        "target",
        "out",
        "bin",
        "obj",
        "venv",
        ".venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
        "vendor",
        "coverage",
        ".next",
        ".nuxt",
        "migrations",
    }
)

# 1 MB ustu metin dosyalari genelde minified veya otomatik uretilmis olur.
MAX_FILE_SIZE_BYTES = 1_000_000

# Cevapta en fazla bu kadar dosya donulur; JSON gereksiz sismesin.
MAX_FILES_IN_RESPONSE = 200

# git ls-files icin ust sinir (saniye).
LIST_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class ScannedFile:
    """Islenmeye uygun bulunan tek bir kaynak dosyasi."""

    path: str
    extension: str
    size_bytes: int
    lines: int


@dataclass
class ScanResult:
    """Bir repository taramasinin ozeti."""

    total_tracked: int = 0
    selected: list[ScannedFile] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1


def list_tracked_files(repo_path: Path) -> list[str]:
    """git'in takip ettigi dosyalarin listesini dondurur.

    `git ls-files` kullanmak bize bedava bir avantaj saglar: repository'nin
    KENDI .gitignore kurallarina takilan dosyalar zaten bu listede yoktur.
    Yani .gitignore'u elle ayristirmamiza gerek kalmaz.

    -z bayragi ciktiyi null karakterle ayirir; boylece icinde bosluk veya
    Turkce karakter olan dosya adlari bozulmadan gelir.
    """
    result = subprocess.run(
        ["git", "-C", str(repo_path), "ls-files", "-z"],
        capture_output=True,
        text=True,
        timeout=LIST_TIMEOUT_SECONDS,
        check=False,
    )

    if result.returncode != 0:
        raise RepositoryError(
            "Repository dosyalari listelenemedi.", status_code=500
        )

    return [entry for entry in result.stdout.split("\0") if entry]


def is_in_ignored_directory(relative_path: str) -> bool:
    """Dosyanin yolunda elenmesi gereken bir klasor var mi?"""
    folders = Path(relative_path).parts[:-1]
    return any(folder in IGNORED_DIRECTORIES for folder in folders)


def read_text_file(path: Path) -> str | None:
    """Dosyayi metin olarak okur. Binary veya cozulemiyorsa None doner."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None

    # Null byte iceren dosya neredeyse her zaman binary'dir.
    if b"\0" in raw:
        return None

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def count_lines(text: str) -> int:
    """Metindeki satir sayisini hesaplar."""
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def scan_repository(repo_path: Path) -> ScanResult:
    """Repository'yi tarar ve islenecek dosyalarin listesini cikarir."""
    tracked = list_tracked_files(repo_path)
    result = ScanResult(total_tracked=len(tracked))

    for relative in tracked:
        if is_in_ignored_directory(relative):
            result.skip("uretilmis_klasor")
            continue

        extension = Path(relative).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            result.skip("desteklenmeyen_uzanti")
            continue

        absolute = repo_path / relative
        try:
            size_bytes = absolute.stat().st_size
        except OSError:
            result.skip("okunamadi")
            continue

        if size_bytes > MAX_FILE_SIZE_BYTES:
            result.skip("cok_buyuk")
            continue

        text = read_text_file(absolute)
        if text is None:
            result.skip("binary_veya_bozuk")
            continue

        result.selected.append(
            ScannedFile(
                path=relative,
                extension=extension,
                size_bytes=size_bytes,
                lines=count_lines(text),
            )
        )

    # Dosyalari yol adina gore sirali tut; ayni repo her zaman ayni sirayla gelsin.
    result.selected.sort(key=lambda item: item.path)
    return result


def count_by_extension(files: list[ScannedFile]) -> dict[str, int]:
    """Secilen dosyalarin uzantiya gore dagilimi (coktan aza sirali)."""
    counts: dict[str, int] = {}
    for item in files:
        counts[item.extension] = counts.get(item.extension, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))
