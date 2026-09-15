"""API'ye gelen ve API'den donen verilerin sekilleri (Pydantic modelleri)."""

from pydantic import BaseModel, Field


class CloneRequest(BaseModel):
    """POST /repositories istegiyle gonderilen govde."""

    url: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Public GitHub repository adresi",
        examples=["https://github.com/LocalinTheEngineer/RepoLensAI"],
    )


class CloneResponse(BaseModel):
    """Clone islemi basarili oldugunda donen cevap."""

    owner: str
    name: str
    path: str
    commit: str
    already_cloned: bool


class RepositoryFile(BaseModel):
    """Islenmeye uygun bulunan tek bir kaynak dosyasi."""

    path: str
    extension: str
    size_bytes: int
    lines: int


class FileScanResponse(BaseModel):
    """GET /repositories/{owner}/{name}/files cevabi."""

    owner: str
    name: str
    total_tracked: int
    selected_count: int
    skipped_count: int
    skipped_reasons: dict[str, int]
    by_extension: dict[str, int]
    total_lines: int
    files: list[RepositoryFile]
    truncated: bool


class ChunkSummary(BaseModel):
    """Tek bir kod parcasinin ozeti (icerik yerine onizleme tasir)."""

    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    line_count: int
    preview: str


class ChunkResponse(BaseModel):
    """GET /repositories/{owner}/{name}/chunks cevabi."""

    owner: str
    name: str
    file_count: int
    chunk_count: int
    total_lines: int
    average_lines_per_chunk: float
    chunk_size_lines: int
    chunk_overlap_lines: int
    chunks: list[ChunkSummary]
    truncated: bool
