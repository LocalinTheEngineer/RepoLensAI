"""GitHub repository'sini yerel workspace klasorune indirme islemleri."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Klonlanan repolar backend/workspace/ altina iner.
WORKSPACE_DIR = Path(__file__).resolve().parents[2] / "workspace"

# git clone icin ust sinir. Devasa bir repoda sonsuza kadar beklemeyelim.
CLONE_TIMEOUT_SECONDS = 120

# GitHub kullanici adi: harf/rakam ile baslar ve biter, arasinda tire olabilir,
# en fazla 39 karakter. Repository adi: harf, rakam, nokta, tire, alt cizgi.
GITHUB_PATH_PATTERN = re.compile(
    r"^github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/"
    r"(?P<name>[A-Za-z0-9._-]{1,100})$"
)


class RepositoryError(Exception):
    """Kullaniciya oldugu gibi gosterilebilecek, beklenen bir hata."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class RepositoryRef:
    """Dogrulanmis repository kimligi."""

    owner: str
    name: str


def parse_github_url(raw_url: str) -> RepositoryRef:
    """Kullanicinin yazdigi adresi dogrular ve owner/name bilgisini cikarir.

    Kabul edilen yazimlar:
        https://github.com/owner/repo
        https://github.com/owner/repo.git
        github.com/owner/repo
        www.github.com/owner/repo/
    """
    url = raw_url.strip()
    url = url.removeprefix("https://").removeprefix("http://")
    url = url.removeprefix("www.")
    url = url.removesuffix("/").removesuffix(".git")

    match = GITHUB_PATH_PATTERN.match(url)
    if match is None:
        raise RepositoryError(
            "Gecerli bir GitHub adresi degil. "
            "Ornek: https://github.com/kullanici/repo"
        )

    owner = match.group("owner")
    name = match.group("name")

    # Klasor adi olarak kullanacagimiz icin "." ve ".." kesinlikle yasak.
    if owner in {".", ".."} or name in {".", ".."}:
        raise RepositoryError("Gecersiz repository adi.")

    return RepositoryRef(owner=owner, name=name)


def clone_repository(ref: RepositoryRef) -> tuple[Path, str, bool]:
    """Repository'yi workspace'e klonlar.

    Doner: (klasor yolu, HEAD commit hash'i, daha once indirilmis miydi)
    """
    target = WORKSPACE_DIR / ref.owner / ref.name

    # Zaten indirilmisse tekrar indirmiyoruz.
    if target.exists():
        return target, read_head_commit(target), True

    target.parent.mkdir(parents=True, exist_ok=True)

    # GUVENLIK: adresi kullanicinin yazdigi metinden degil, regex'ten gecmis
    # owner/name parcalarindan yeniden kuruyoruz.
    clone_url = f"https://github.com/{ref.owner}/{ref.name}.git"

    try:
        result = subprocess.run(
            # GUVENLIK: liste olarak veriyoruz, shell=True yok.
            # Boylece kullanici girdisi kabuk komutu olarak yorumlanamaz.
            ["git", "clone", "--depth", "1", "--", clone_url, str(target)],
            capture_output=True,
            text=True,
            timeout=CLONE_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as error:
        raise RepositoryError(
            "Sunucuda git kurulu degil.", status_code=500
        ) from error
    except subprocess.TimeoutExpired as error:
        remove_directory(target)
        raise RepositoryError(
            f"Repository {CLONE_TIMEOUT_SECONDS} saniye icinde indirilemedi. "
            "Repo cok buyuk olabilir.",
            status_code=504,
        ) from error

    if result.returncode != 0:
        remove_directory(target)
        message, status_code = describe_clone_failure(result.stderr)
        raise RepositoryError(message, status_code=status_code)

    return target, read_head_commit(target), False


def describe_clone_failure(stderr: str) -> tuple[str, int]:
    """git'in teknik hata ciktisini kullanicinin anlayacagi mesaja cevirir."""
    lowered = stderr.lower()

    if "could not resolve host" in lowered or "failed to connect" in lowered:
        return ("GitHub'a baglanilamadi. Internet baglantini kontrol et.", 502)

    if "authentication failed" in lowered or "could not read username" in lowered:
        return (
            "Bu repository icin kimlik dogrulama gerekiyor. "
            "Su an yalnizca public repolar destekleniyor.",
            403,
        )

    if "not found" in lowered or "repository does not exist" in lowered:
        return (
            "Repository bulunamadi. Adres yanlis olabilir ya da repo private "
            "olabilir; su an yalnizca public repolar destekleniyor.",
            404,
        )

    return ("Repository indirilemedi. Adresi kontrol edip tekrar dene.", 502)


def pull_latest(path: Path) -> str:
    """Var olan bir klonu GitHub'daki en son commit'e gunceller.

    --depth 1 ile klonlandigi icin gecmis yok; fetch ucu ileri tasir, reset
    calisma agacini ona esitler. Repo yalnizca okunuyor (kullanici burada
    hicbir zaman degisiklik yapmaz), o yuzden reset --hard veri kaybettirmez.
    """
    fetch = subprocess.run(
        ["git", "-C", str(path), "fetch", "--depth", "1", "origin"],
        capture_output=True,
        text=True,
        timeout=CLONE_TIMEOUT_SECONDS,
        check=False,
    )
    if fetch.returncode != 0:
        raise RepositoryError(
            "Repository guncellenemedi (fetch basarisiz).", status_code=502
        )

    reset = subprocess.run(
        ["git", "-C", str(path), "reset", "--hard", "FETCH_HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if reset.returncode != 0:
        raise RepositoryError(
            "Repository guncellenemedi (reset basarisiz).", status_code=502
        )

    return read_head_commit(path)


def read_head_commit(path: Path) -> str:
    """Indirilen repository'nin en son commit hash'ini okur."""
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return "bilinmiyor"
    return result.stdout.strip()


def remove_directory(path: Path) -> None:
    """Yarim kalan clone klasorunu siler."""
    if not path.exists():
        return
    try:
        shutil.rmtree(path, onexc=_make_writable_and_retry)
    except OSError:
        pass


def _make_writable_and_retry(func, path, _error) -> None:
    """Windows'ta .git icindeki salt-okunur dosyalari silebilmek icin."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def build_reference(owner: str, name: str) -> RepositoryRef:
    """URL yerine ayri ayri gelen owner/name parcalarini dogrular.

    Adres cubugundan (path parametresi) gelen degerler de ayni regex'ten
    gectigi icin ".." veya "/" gibi tehlikeli girdiler burada da engellenir.
    """
    return parse_github_url(f"github.com/{owner}/{name}")


def repository_path(ref: RepositoryRef) -> Path:
    """Indirilmis repository'nin klasor yolunu dondurur; yoksa hata firlatir."""
    target = WORKSPACE_DIR / ref.owner / ref.name
    if not target.is_dir():
        raise RepositoryError(
            "Bu repository henuz indirilmemis. Once adresini girip indir.",
            status_code=404,
        )
    return target
