"""Kaynak dosyalari embedding ve retrieval icin yonetilebilir parcalara ayirir.

Adim 4 gecici bir cozumdur: kodu sabit satir sayisiyla boluyoruz.
Adim 11'de Tree-sitter ile fonksiyon/class sinirlarina gore bolunecek.

Her parca (chunk) kendi kaynagini tasir: hangi dosyanin kacinci satirlari.
Bu metadata ileride "cevap su dosyanin su satirlarindan geldi" diyebilmemizin
temeli olacak.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Bir parcanin hedef satir sayisi. Yol haritasi 100-150 araligini oneriyor.
CHUNK_SIZE_LINES = 120

# Ardisik parcalarin paylastigi satir sayisi.
# Neden? Bir fonksiyon tam parca sinirinda ikiye bolunurse iki parcanin da
# yarim kalmasini engeller; her parca komsusundan biraz baglam tasir.
CHUNK_OVERLAP_LINES = 20

# Her adimda kac satir ilerliyoruz.
CHUNK_STEP_LINES = CHUNK_SIZE_LINES - CHUNK_OVERLAP_LINES

# Cevapta en fazla bu kadar parca donulur; JSON gereksiz sismesin.
MAX_CHUNKS_IN_RESPONSE = 100

# Parca onizlemesinde gosterilecek karakter sayisi.
PREVIEW_CHARS = 200


@dataclass(frozen=True)
class Chunk:
    """Tek bir kod parcasi ve kaynak bilgisi.

    symbol_name / symbol_type yalnizca AST ile bolunmus parcalarda dolu olur
    (orn. "get_signing_serializer" / "function"). Satir tabanli bolmede
    ikisi de None kalir.
    """

    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    symbol_name: str | None = None
    symbol_type: str | None = None

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    @property
    def preview(self) -> str:
        """Parcanin basindan kisa bir onizleme."""
        if len(self.content) <= PREVIEW_CHARS:
            return self.content
        return self.content[:PREVIEW_CHARS] + "..."


@dataclass
class ChunkingResult:
    """Bir repository'nin tamaminin parcalanma ozeti."""

    file_count: int = 0
    chunks: list[Chunk] = field(default_factory=list)


def chunk_text(file_path: str, text: str) -> list[Chunk]:
    """Tek bir dosyanin metnini sabit boyutlu parcalara ayirir.

    Satir numaralari 1 tabanlidir; editorler ve GitHub da oyle sayar.
    Bosluktan ibaret parcalar atlanir.
    """
    lines = text.splitlines()
    if not lines:
        return []

    chunks: list[Chunk] = []
    start = 0

    while start < len(lines):
        end = min(start + CHUNK_SIZE_LINES, len(lines))
        piece = lines[start:end]
        content = "\n".join(piece)

        # Tamami bosluk olan parcanin AI icin bir degeri yok.
        if content.strip():
            start_line = start + 1
            chunks.append(
                Chunk(
                    chunk_id=f"{file_path}:{start_line}-{end}",
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end,
                    content=content,
                )
            )

        # Dosyanin sonuna geldiysek dur; yoksa sonsuz donguye gireriz.
        if end >= len(lines):
            break

        start += CHUNK_STEP_LINES

    return chunks
