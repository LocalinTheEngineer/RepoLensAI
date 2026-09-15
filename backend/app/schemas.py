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
