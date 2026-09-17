"""Dosyalar arasindaki import iliskilerinden dosya-seviyesi bir bagimlilik
grafigi kurar.

Adim 18: yol haritasi "ilk asamada yalnizca dosya/modul seviyesinde kal"
diyor - yani "hangi fonksiyon hangi fonksiyonu cagiriyor" degil, "hangi dosya
hangi dosyayi import ediyor". Dis kutuphaneler (flask, react, os...) grafige
girmez; yalnizca reponun KENDI dosyalarina giden kenarlar tutulur, cunku
disaridaki bir paketin repo icinde karsiligi olan bir dosyasi yok.

Python icin stdlib `ast` modulu yeterli (Adim 11'deki tree-sitter, sembol
sinirlarini bulmak icindir; import ayristirmak icin ayri bir grammar'a hic
gerek yok). JS/TS icin bu projede henuz bir JS/TS AST parser'i kullanilmiyor;
yalnizca GORECELI importlari ('./x', '../x') hedefleyen basit bir duzenli
ifade yeterli, cunku paket importlari ('react', 'lodash'...) zaten repo
disinda kalir ve ayiklamamiza gerek yok.
"""

from __future__ import annotations

import ast
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.services.file_scanner import read_text_file, scan_repository

# import '<relative>' / import x from '<relative>' / export ... from '<relative>'
# / dynamic import('<relative>'). Yalnizca '.' ile baslayan (goreceli) yollar
# yakalanir; paket adlari ('react' gibi) repo icinde bir dosyaya karsilik
# gelmedigi icin zaten ilgi alanimiz disinda.
JS_RELATIVE_IMPORT_RE = re.compile(
    r"""(?:from\s+|import\s*\(\s*)['"](\.[^'"]+)['"]"""
)

# JS/TS'te bir goreceli yol dosya sistemine cevrilirken denenecek uzantilar/
# index dosyalari, sirayla.
JS_RESOLVE_SUFFIXES = (
    "",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    "/index.ts",
    "/index.tsx",
    "/index.js",
    "/index.jsx",
)


@dataclass
class DependencyGraph:
    """Dosya seviyesinde bagimlilik grafigi."""

    nodes: list[str] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)


def extract_python_imports(text: str) -> list[tuple[int, str | None]]:
    """Bir Python dosyasindaki import'lari (level, module) ciftleri olarak cikartir.

    level=0       -> mutlak import ("import a.b", "from a.b import c")
    level=1, 2...  -> goreceli import ("from . import x" -> 1, "from ..a import b" -> 2)
    module=None   -> yalnizca "from . import x" gibi salt noktali importlarda
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    found: list[tuple[int, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((0, alias.name))
        elif isinstance(node, ast.ImportFrom):
            found.append((node.level, node.module))
    return found


def _python_module_key(file_path: str) -> str | None:
    """Dosya yolunu (uzantisiz) import-anahtarina cevirir.

    '__init__.py' bir paketin kendisidir, kendi klasoruyle temsil edilir;
    repo kokundeki bir '__init__.py' hicbir paketi temsil etmez.
    """
    if file_path.endswith("/__init__.py"):
        return file_path[: -len("/__init__.py")]
    if file_path == "__init__.py":
        return None
    if file_path.endswith(".py"):
        return file_path[: -len(".py")]
    return None


def build_python_index(python_files: list[str]) -> dict[str, str]:
    """Her dosya icin, o dosyaya isaret edebilecek butun 'suffix' anahtarlarini kurar.

    Ornek: 'src/flask/app.py' -> anahtarlar 'src/flask/app', 'flask/app', 'app'.
    'from flask.app import X' gibi mutlak importlar repo kokunu bilmez (repo
    'src/' altinda olabilir), suffix eslesmesi bu farki yok sayar.

    Iki farkli dosya ayni suffix'i uretirse (orn. gercek 'src/flask/__init__.py'
    paketi ile testlerdeki bir 'tests/fixtures/.../flask.py' dosyasi), koke en
    yakin (modul yolu en kisa) olan kazanir - "import flask" neredeyse hep
    ust duzey paketi kastediyordur, testin ic ice gecmis fixture'ini degil.
    """
    index: dict[str, str] = {}
    shortest: dict[str, int] = {}
    for path in python_files:
        module_key = _python_module_key(path)
        if module_key is None:
            continue
        parts = module_key.split("/") if module_key else []
        for i in range(len(parts)):
            suffix = "/".join(parts[i:])
            if suffix not in shortest or len(parts) < shortest[suffix]:
                shortest[suffix] = len(parts)
                index[suffix] = path
    return index


def _resolve_relative_python_target(
    current_file: str, level: int, module: str | None
) -> str | None:
    """Goreceli bir import'un hedef anahtarini (mutlak importla ayni bicimde) hesaplar."""
    directory_parts = current_file.split("/")[:-1]
    up = level - 1
    if up > len(directory_parts):
        return None
    base_parts = directory_parts[: len(directory_parts) - up] if up else directory_parts

    target_parts = base_parts + module.split(".") if module else base_parts
    return "/".join(target_parts) if target_parts else None


def _python_edges_for_file(
    path: str, text: str, index: dict[str, str]
) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for level, module in extract_python_imports(text):
        target_key = (
            _resolve_relative_python_target(path, level, module)
            if level > 0
            else (module.replace(".", "/") if module else None)
        )
        if not target_key:
            continue
        resolved = index.get(target_key)
        if resolved and resolved != path:
            edges.add((path, resolved))
    return edges


def _resolve_js_relative(current_file: str, raw_import: str, files: set[str]) -> str | None:
    joined = posixpath.normpath(
        posixpath.join(posixpath.dirname(current_file), raw_import)
    )
    for suffix in JS_RESOLVE_SUFFIXES:
        candidate = f"{joined}{suffix}"
        if candidate in files:
            return candidate
    return None


def _js_edges_for_file(path: str, text: str, files: set[str]) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for match in JS_RELATIVE_IMPORT_RE.finditer(text):
        raw_import = match.group(1)
        resolved = _resolve_js_relative(path, raw_import, files)
        if resolved and resolved != path:
            edges.add((path, resolved))
    return edges


def build_dependency_graph(repo_path: Path) -> DependencyGraph:
    """Repository'nin dosya-seviyesi import grafigini kurar."""
    scan = scan_repository(repo_path)
    all_paths = {item.path for item in scan.selected}
    python_index = build_python_index(
        [path for path in all_paths if path.endswith(".py")]
    )

    edges: set[tuple[str, str]] = set()
    for item in scan.selected:
        text = read_text_file(repo_path / item.path)
        if text is None:
            continue

        if item.extension == ".py":
            edges |= _python_edges_for_file(item.path, text, python_index)
        elif item.extension in (".js", ".ts", ".tsx"):
            edges |= _js_edges_for_file(item.path, text, all_paths)

    return DependencyGraph(nodes=sorted(all_paths), edges=sorted(edges))


def _demo() -> None:
    """Gercek dosya sistemine dokunmadan cozumleme mantigini dogrular."""
    index = build_python_index(
        ["src/flask/app.py", "src/flask/__init__.py", "src/flask/sansio/scaffold.py"]
    )

    # Mutlak import, repo koku (src/) bilinmeden de bulunmali.
    edges = _python_edges_for_file(
        "src/flask/cli.py", "from flask.app import Flask\n", index
    )
    assert edges == {("src/flask/cli.py", "src/flask/app.py")}, edges

    # Disaridaki bir paket (repo'da karsiligi yok) kenar uretmemeli.
    edges = _python_edges_for_file(
        "src/flask/cli.py", "import click\n", index
    )
    assert edges == set(), edges

    # Goreceli import, mevcut dosyanin klasorune gore cozulmeli.
    edges = _python_edges_for_file(
        "src/flask/sansio/scaffold.py", "from ..app import Flask\n", index
    )
    assert edges == {("src/flask/sansio/scaffold.py", "src/flask/app.py")}, edges

    files = {"frontend/src/api.ts", "frontend/src/App.tsx"}
    resolved = _resolve_js_relative("frontend/src/App.tsx", "./api", files)
    assert resolved == "frontend/src/api.ts", resolved

    # Ayni suffix'i ureten iki dosya varsa (gercek paket + testlerdeki bir
    # fixture), koke daha yakin olan (kisa modul yolu) kazanmali.
    ambiguous_index = build_python_index(
        [
            "src/flask/__init__.py",
            "tests/test_apps/cliapp/inner1/inner2/flask.py",
        ]
    )
    assert ambiguous_index["flask"] == "src/flask/__init__.py", ambiguous_index["flask"]

    print("dependency_graph: tum kontroller gecti")


if __name__ == "__main__":
    _demo()
