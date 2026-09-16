"""Kodu satir sayisina gore degil, GERCEK YAPISINA gore parcalara ayirir.

Adim 4'te dosyalari kor bir sekilde 120 satirda kesiyorduk; bir fonksiyonun
ortasindan gecebiliyordu. Tree-sitter kaynak kodun agac yapisini (AST)
cikarir, biz de parcalari fonksiyon/class sinirlarinda olustururuz.

Boylece her parca kendi icinde butun olur ve ayrica "bu parca hangi
fonksiyon" bilgisini (symbol_name / symbol_type) tasir.

Desteklenmeyen uzantilar (.md gibi) ve parse edilemeyen dosyalar satir
tabanli yonteme geri duser; hicbir dosya islenmeden kalmaz.
"""

from __future__ import annotations

import threading
from pathlib import Path

import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from app.services.chunker import (
    CHUNK_OVERLAP_LINES,
    CHUNK_SIZE_LINES,
    Chunk,
    ChunkingResult,
    chunk_text,
)
from app.services.file_scanner import read_text_file, scan_repository

# Uzanti -> (dil adi, gramer fonksiyonu)
GRAMMARS = {
    ".py": ("python", tree_sitter_python.language),
    ".js": ("javascript", tree_sitter_javascript.language),
    ".ts": ("typescript", tree_sitter_typescript.language_typescript),
    ".tsx": ("tsx", tree_sitter_typescript.language_tsx),
    ".java": ("java", tree_sitter_java.language),
}

# Kendi basina bir parca olmayi hak eden AST dugum turleri.
SYMBOL_TYPES: dict[str, str] = {
    # Python
    "function_definition": "function",
    "class_definition": "class",
    # JavaScript / TypeScript
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "enum_declaration": "enum",
    # Java
    "method_declaration": "method",
    "constructor_declaration": "constructor",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
}

# Bu dugumler asil tanimi sarar; icine bakip gercek sembolu buluruz.
WRAPPER_TYPES = {"decorated_definition", "export_statement"}

# Bir sembol bu satir sayisini asarsa ikinci seviye bolme uygulanir.
MAX_SYMBOL_LINES = 150

# Ic ice bolmede sonsuz derinlige gitmeyelim.
MAX_SPLIT_DEPTH = 3

_parsers: dict[str, Parser] = {}
_parser_lock = threading.Lock()


def get_parser(extension: str) -> Parser:
    """Uzantiya uygun parser'i dondurur; bir kez olusturulup saklanir."""
    global _parsers

    if extension not in _parsers:
        with _parser_lock:
            if extension not in _parsers:
                _, grammar = GRAMMARS[extension]
                _parsers[extension] = Parser(Language(grammar()))

    return _parsers[extension]


def line_range(node: Node) -> tuple[int, int]:
    """Dugumun 1 tabanli (baslangic, bitis) satir araligi.

    tree-sitter satirlari 0'dan sayar. Ayrica bir dugum bir sonraki satirin
    0. sutununda bitiyorsa aslinda onceki satirda bitmistir; bu durumda
    fazladan bir satir saymamak icin duzeltme yapiyoruz.
    """
    start_row, _ = node.start_point
    end_row, end_column = node.end_point

    if end_column == 0 and end_row > start_row:
        end_row -= 1

    return start_row + 1, end_row + 1


def unwrap(node: Node) -> Node:
    """Sarmalayici dugumlerin (dekorator, export) icindeki asil tanimi bulur."""
    current = node
    for _ in range(4):  # cok derine inmeye gerek yok
        if current.type not in WRAPPER_TYPES:
            return current
        inner = next(
            (child for child in current.named_children if child.type in SYMBOL_TYPES),
            None,
        )
        if inner is None:
            return current
        current = inner
    return current


def symbol_of(node: Node) -> tuple[str, str | None] | None:
    """Dugum bir sembol mu? Oyleyse (tur, isim) dondurur."""
    target = unwrap(node)
    symbol_type = SYMBOL_TYPES.get(target.type)
    if symbol_type is None:
        return None

    name_node = target.child_by_field_name("name")
    name = name_node.text.decode("utf-8", "replace") if name_node else None
    return symbol_type, name


def make_chunk(
    file_path: str,
    lines: list[str],
    start: int,
    end: int,
    symbol_type: str | None,
    symbol_name: str | None,
) -> Chunk | None:
    """Verilen satir araligindan bir Chunk uretir; bosluksa None doner."""
    content = "\n".join(lines[start - 1 : end])
    if not content.strip():
        return None

    return Chunk(
        chunk_id=f"{file_path}:{start}-{end}",
        file_path=file_path,
        start_line=start,
        end_line=end,
        content=content,
        symbol_name=symbol_name,
        symbol_type=symbol_type,
    )


def split_range_by_lines(
    file_path: str,
    lines: list[str],
    start: int,
    end: int,
    symbol_type: str | None,
    symbol_name: str | None,
) -> list[Chunk]:
    """Bir satir araligini sabit boyutlu parcalara boler.

    Alt sembole bolunemeyen devasa fonksiyonlar ve modul seviyesi kod icin.
    Satir numaralari dosyanin tamamina gore (mutlak) kalir.
    """
    step = CHUNK_SIZE_LINES - CHUNK_OVERLAP_LINES
    produced: list[Chunk] = []
    cursor = start

    while cursor <= end:
        piece_end = min(cursor + CHUNK_SIZE_LINES - 1, end)
        chunk = make_chunk(
            file_path, lines, cursor, piece_end, symbol_type, symbol_name
        )
        if chunk is not None:
            produced.append(chunk)

        if piece_end >= end:
            break
        cursor += step

    return produced


def emit_range(
    file_path: str,
    lines: list[str],
    start: int,
    end: int,
    symbol_type: str | None,
    symbol_name: str | None,
) -> list[Chunk]:
    """Bir satir araligini parcaya cevirir; sinirdan uzunsa satir satir boler.

    Sembol icindeki bosluklar ve son kisimlar icin kullanilir. Bunlar AST
    dugumu degil ham satir araligidir, ama boyut sinirina yine uymalidirlar.
    """
    if end - start + 1 <= MAX_SYMBOL_LINES:
        chunk = make_chunk(file_path, lines, start, end, symbol_type, symbol_name)
        return [chunk] if chunk is not None else []

    return split_range_by_lines(
        file_path, lines, start, end, symbol_type, symbol_name
    )


def emit_symbol(
    node: Node,
    file_path: str,
    lines: list[str],
    out: list[Chunk],
    depth: int = 0,
) -> None:
    """Bir sembolu parcaya cevirir; cok buyukse alt sembollerine boler."""
    found = symbol_of(node)
    symbol_type, symbol_name = found if found else (None, None)
    start, end = line_range(node)

    if end - start + 1 <= MAX_SYMBOL_LINES:
        chunk = make_chunk(file_path, lines, start, end, symbol_type, symbol_name)
        if chunk is not None:
            out.append(chunk)
        return

    # Cok buyuk. Icinde kendi basina anlamli alt semboller var mi?
    body = unwrap(node).child_by_field_name("body")
    inner = (
        [child for child in body.named_children if symbol_of(child)] if body else []
    )

    if inner and depth < MAX_SPLIT_DEPTH:
        # Alt sembolleri tek tek yaziyoruz, ama ARALARINDA ve SONDA kalan kod
        # da kaybolmamali: bir React bileseninde ic fonksiyonlarin arasindaki
        # useState cagrilari ve en sondaki JSX return bloku boyle dusuyordu.
        cursor = start

        for child in inner:
            child_start, child_end = line_range(child)

            # Alt sembolden onceki bosluk (class basligi, alan tanimlari...)
            # Bu kisim da cok uzun olabilir (orn. 220 satirlik bir class
            # basligi), o yuzden boyut sinirini burada da uyguluyoruz.
            if child_start > cursor:
                out.extend(
                    emit_range(
                        file_path, lines, cursor, child_start - 1,
                        symbol_type, symbol_name,
                    )
                )

            emit_symbol(child, file_path, lines, out, depth + 1)
            cursor = child_end + 1

        # Son alt sembolden sonra kalan kisim (orn. JSX return bloku)
        if cursor <= end:
            out.extend(
                emit_range(file_path, lines, cursor, end, symbol_type, symbol_name)
            )
        return

    # Alt sembol yok: satir tabanli bol ama sembol bilgisini koru.
    out.extend(
        split_range_by_lines(
            file_path, lines, start, end, symbol_type, symbol_name
        )
    )


def chunk_source(file_path: str, text: str) -> list[Chunk]:
    """Bir dosyayi AST sinirlarinda parcalara ayirir.

    Dil desteklenmiyorsa veya hic sembol bulunamazsa satir tabanli yonteme
    geri duser; hicbir dosya islenmeden kalmaz.
    """
    extension = Path(file_path).suffix.lower()
    if extension not in GRAMMARS:
        return chunk_text(file_path, text)

    try:
        tree = get_parser(extension).parse(text.encode("utf-8"))
    except Exception:
        return chunk_text(file_path, text)

    lines = text.splitlines()
    if not lines:
        return []

    out: list[Chunk] = []
    pending_start: int | None = None
    pending_end = 0

    def flush_pending() -> None:
        """Birikmis modul seviyesi kodu (import, sabit...) parcaya cevirir."""
        nonlocal pending_start
        if pending_start is None:
            return
        out.extend(
            split_range_by_lines(
                file_path, lines, pending_start, pending_end, "module", None
            )
        )
        pending_start = None

    for child in tree.root_node.children:
        start, end = line_range(child)

        if symbol_of(child) is None:
            # Sembol degil: import, sabit, modul seviyesi ifade.
            if pending_start is None:
                pending_start = start
            pending_end = max(pending_end, end)
            continue

        flush_pending()
        emit_symbol(child, file_path, lines, out)

    flush_pending()

    if not out:
        return chunk_text(file_path, text)

    out.sort(key=lambda chunk: (chunk.start_line, chunk.end_line))
    return out


def chunk_repository(repo_path: Path) -> ChunkingResult:
    """Repository'deki islenecek tum dosyalari parcalara ayirir.

    Not: dosyalar tarama sirasinda bir kez, burada bir kez daha okunuyor.
    Alternatif butun repoyu bellekte tutmak olurdu; iki kez okumak daha guvenli.
    """
    scan = scan_repository(repo_path)
    result = ChunkingResult()

    for source in scan.selected:
        text = read_text_file(repo_path / source.path)
        if text is None:
            continue

        produced = chunk_source(source.path, text)
        if produced:
            result.file_count += 1
            result.chunks.extend(produced)

    return result
