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


class EmbedQueryRequest(BaseModel):
    """POST /embeddings/query istegiyle gonderilen govde."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Vektore cevrilecek kullanici sorgusu",
        examples=["how does authentication work"],
    )


class EmbedQueryResponse(BaseModel):
    """Bir sorgunun vektor karsiligi.

    Alan adi `model_name` degil `embedding_model`; Pydantic `model_` ile
    baslayan adlari kendi ic kullanimi icin ayirmistir.
    """

    embedding_model: str
    dimensions: int
    duration_ms: float
    vector_preview: list[float]


class ChunkEmbeddingSample(BaseModel):
    """Ornek olarak gosterilen tek bir parcanin vektor onizlemesi."""

    chunk_id: str
    vector_preview: list[float]


class EmbedRepositoryResponse(BaseModel):
    """GET /repositories/{owner}/{name}/embeddings cevabi."""

    owner: str
    name: str
    embedding_model: str
    dimensions: int
    chunk_count: int
    duration_ms: float
    chunks_per_second: float
    samples: list[ChunkEmbeddingSample]


class IndexResponse(BaseModel):
    """POST /repositories/{owner}/{name}/index cevabi."""

    owner: str
    name: str
    embedding_model: str
    dimensions: int
    chunk_count: int
    stored_count: int
    embed_duration_ms: float
    store_duration_ms: float


class SearchRequest(BaseModel):
    """POST /repositories/{owner}/{name}/search istegiyle gonderilen govde."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Ingilizce arama sorgusu",
        examples=["how does authentication work"],
    )
    limit: int = Field(
        5,
        ge=1,
        le=20,
        description="Kac sonuc dondurulecek",
    )


class SearchHitOut(BaseModel):
    """Aramadan donen tek bir kod parcasi."""

    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    score: float


class SearchResponse(BaseModel):
    """Arama sonucu ve kaynaklari."""

    owner: str
    name: str
    query: str
    duration_ms: float
    hits: list[SearchHitOut]


class AskRequest(BaseModel):
    """POST /repositories/{owner}/{name}/ask istegiyle gonderilen govde."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Ingilizce soru",
        examples=["how does authentication work"],
    )
    limit: int = Field(
        5,
        ge=1,
        le=10,
        description="LLM'e kac kod parcasi verilecek",
    )


class CitationOut(BaseModel):
    """Cevap metninde gecen bir kaynak referansi ve dogrulama sonucu.

    status degerleri:
      verified     -> referans araligi, verilen bir parcanin icinde
      out_of_range -> dosya verilmis ama aralik parcalarin disina tasiyor
      unknown_file -> dosya modele hic verilmemis (uydurma)
    """

    file_path: str
    start_line: int
    end_line: int
    status: str
    chunk_id: str | None


class AskResponse(BaseModel):
    """LLM cevabi, dayandigi kaynaklar ve citation dogrulamasi."""

    owner: str
    name: str
    question: str
    answer: str
    model: str
    retrieval_ms: float
    generation_ms: float
    sources: list[SearchHitOut]
    citations: list[CitationOut]
    unverified_citations: int
