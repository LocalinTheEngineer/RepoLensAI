"""API'ye gelen ve API'den donen verilerin sekilleri (Pydantic modelleri)."""

from typing import Literal

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

    # Bunlar TUM secilen dosyalar uzerinden hesaplanir, `files` listesi
    # (MAX_FILES_IN_RESPONSE ile) kirpilmis olsa bile eksiksizdir.
    top_level_dirs: dict[str, int]
    largest_files: list[RepositoryFile]


class ChunkSummary(BaseModel):
    """Tek bir kod parcasinin ozeti (icerik yerine onizleme tasir)."""

    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    line_count: int
    preview: str
    symbol_name: str | None = None
    symbol_type: str | None = None


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

    # TUM parcalar uzerinden hesaplanir, `chunks` listesi (MAX_CHUNKS_IN_RESPONSE
    # ile) kirpilmis olsa bile eksiksizdir.
    symbol_counts: dict[str, int]


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


class DependencyEdge(BaseModel):
    """Tek bir import iliskisi: `source` dosyasi `target` dosyasini import ediyor."""

    source: str
    target: str


class DependencyGraphResponse(BaseModel):
    """GET /repositories/{owner}/{name}/dependencies cevabi.

    Yalnizca reponun KENDI dosyalari arasindaki importlar tutulur; dis
    kutuphaneler (flask, react, os...) grafige girmez.
    """

    owner: str
    name: str
    nodes: list[str]
    edges: list[DependencyEdge]


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
    mode: Literal["semantic", "keyword", "hybrid"] = Field(
        "hybrid",
        description=(
            "hybrid = ikisinin RRF ile birlesimi (varsayilan), "
            "semantic = anlamsal (embedding) arama, "
            "keyword = kelime tabanli (BM25) arama"
        ),
    )
    rerank: bool = Field(
        False,
        description=(
            "true ise once genis bir aday havuzu cekilir, sonra cross-encoder "
            "ile yeniden siralanip en iyi `limit` tanesi dondurulur. Daha "
            "isabetli ama daha yavas."
        ),
    )


class SearchHitOut(BaseModel):
    """Aramadan donen tek bir kod parcasi."""

    chunk_id: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    score: float
    symbol_name: str | None = None
    symbol_type: str | None = None

    # Yalnizca hybrid modda dolu: parcayi hangi yontem kacinci sirada buldu.
    # null = o yontem bu parcayi hic bulmadi.
    vector_rank: int | None = None
    keyword_rank: int | None = None

    # Yalnizca rerank istendiginde dolu: cross-encoder puani. Retrieval
    # skorlariyla ayni olcekte DEGILDIR, ayri bir modelin puanidir.
    rerank_score: float | None = None


class SearchResponse(BaseModel):
    """Arama sonucu ve kaynaklari.

    DIKKAT: skor olcegi moda gore farklidir. semantic modda kosinus
    benzerligi (0-1 arasi), keyword modda BM25 skoru (sinirsiz pozitif sayi),
    hybrid modda RRF puani (0-a yakin kucuk sayilar). Uc olcek birbiriyle
    dogrudan karsilastirilamaz.
    """

    owner: str
    name: str
    query: str
    mode: str
    duration_ms: float

    # Rerank asamasinin suresi; rerank istenmediyse null.
    rerank_ms: float | None = None

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
    rerank_ms: float
    generation_ms: float
    sources: list[SearchHitOut]
    citations: list[CitationOut]
    unverified_citations: int
