"""RepoLens AI - Backend giris noktasi.

Yol haritasi:
  Adim 1: /health         -> frontend ile backend konusabiliyor
  Adim 2: /repositories   -> verilen GitHub URL'sindeki repo clone ediliyor
  Adim 3: .../files       -> repodan yalnizca islenecek kaynak dosyalar
  Adim 4: .../chunks      -> dosyalar satir araligi bilgisiyle parcalara ayrilir
  Adim 5: .../embeddings  -> parcalar ve sorgular sayisal vektore cevrilir
  Adim 6: .../index       -> vektorler Qdrant'a yazilir
          .../search      -> sorguya en yakin kod parcalari getirilir
  Adim 8: .../ask         -> bulunan parcalardan LLM kaynakli cevap uretir
"""

import time

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    AgentStepOut,
    AskRequest,
    AskResponse,
    CitationOut,
    ChunkResponse,
    ChunkSummary,
    CloneRequest,
    CloneResponse,
    DependencyEdge,
    DependencyGraphResponse,
    FileScanResponse,
    IndexJobStatus,
    InvestigateRequest,
    InvestigateResponse,
    ReindexResponse,
    RepositoryFile,
    SearchHitOut,
    SearchRequest,
    SearchResponse,
)
from app.services.embedder import (
    embed_query,
)
from app.services.ast_chunker import chunk_repository
from app.services.dependency_graph import build_dependency_graph
from app.services.incremental_index import reindex_repository
from app.services.index_jobs import IndexJob, get_job, run_job, start_job
from app.services.chunker import (
    CHUNK_OVERLAP_LINES,
    CHUNK_SIZE_LINES,
    MAX_CHUNKS_IN_RESPONSE,
    count_symbols,
)
from app.services.file_scanner import (
    MAX_FILES_IN_RESPONSE,
    count_by_extension,
    count_by_top_level_dir,
    largest_files,
    scan_repository,
)
from app.services.agent import investigate
from app.services.answerer import generate_answer
from app.services.citations import count_unverified, verify_citations
from app.services.hybrid_search import search as search_hybrid
from app.services.keyword_search import search as search_keywords
from app.services.reranker import CANDIDATE_LIMIT as RERANK_CANDIDATES
from app.services.reranker import rerank
from app.services.vector_store import search as search_vectors
from app.services.vector_store import SearchHit
from app.services.repository import (
    RepositoryError,
    build_reference,
    clone_repository,
    parse_github_url,
    repository_path,
)

# Uygulama nesnesi. title/description/version degerleri
# otomatik olusan API dokumantasyonunda (/docs) gorunur.
app = FastAPI(
    title="RepoLens AI API",
    description="GitHub repository'lerini analiz eden AI developer tool'un backend servisi.",
    version="0.8.0",
)

# Tarayicidaki frontend'in bu API'ye istek atmasina izin verilen adresler.
# Vite gelistirme sunucusu varsayilan olarak 5173 portunda calisir.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RepositoryError)
async def repository_error_handler(
    request: Request, error: RepositoryError
) -> JSONResponse:
    """Servis katmaninin hatasini HTTP cevabina cevirir.

    Onceden her endpoint ayni try/except'i tekrar ediyordu (12 kez). Tek
    yerde durunca yeni bir endpoint yazarken unutulmasi da mumkun degil.
    """
    return JSONResponse(
        status_code=error.status_code, content={"detail": error.message}
    )


@app.get("/health")
def health() -> dict[str, str]:
    """Servisin ayakta olup olmadigini bildirir."""
    return {"status": "ok"}


# Not: bilerek "async def" degil "def" kullaniyoruz. git clone islemi
# uzun surer ve beklerken CPU'yu birakmaz; FastAPI normal "def"
# fonksiyonlarini ayri bir thread'de calistirdigi icin sunucu bu sirada
# diger isteklere cevap vermeye devam eder.
@app.post("/repositories", response_model=CloneResponse)
def create_repository(payload: CloneRequest) -> CloneResponse:
    """Verilen public GitHub adresindeki repository'yi yerel workspace'e indirir."""
    ref = parse_github_url(payload.url)
    path, commit, already_cloned = clone_repository(ref)

    return CloneResponse(
        owner=ref.owner,
        name=ref.name,
        path=str(path),
        commit=commit,
        already_cloned=already_cloned,
    )


@app.get(
    "/repositories/{owner}/{name}/files",
    response_model=FileScanResponse,
)
def list_repository_files(owner: str, name: str) -> FileScanResponse:
    """Indirilmis repository icinden islenecek kaynak dosyalari listeler."""
    ref = build_reference(owner, name)
    path = repository_path(ref)
    result = scan_repository(path)

    skipped_count = sum(result.skipped.values())
    shown = result.selected[:MAX_FILES_IN_RESPONSE]

    return FileScanResponse(
        owner=ref.owner,
        name=ref.name,
        total_tracked=result.total_tracked,
        selected_count=len(result.selected),
        skipped_count=skipped_count,
        skipped_reasons=result.skipped,
        by_extension=count_by_extension(result.selected),
        total_lines=sum(item.lines for item in result.selected),
        files=[
            RepositoryFile(
                path=item.path,
                extension=item.extension,
                size_bytes=item.size_bytes,
                lines=item.lines,
            )
            for item in shown
        ],
        truncated=len(result.selected) > len(shown),
        top_level_dirs=count_by_top_level_dir(result.selected),
        largest_files=[
            RepositoryFile(
                path=item.path,
                extension=item.extension,
                size_bytes=item.size_bytes,
                lines=item.lines,
            )
            for item in largest_files(result.selected)
        ],
    )


@app.get(
    "/repositories/{owner}/{name}/chunks",
    response_model=ChunkResponse,
)
def list_repository_chunks(owner: str, name: str) -> ChunkResponse:
    """Repository'nin kaynak dosyalarini satir araligi bilgisiyle parcalara ayirir."""
    ref = build_reference(owner, name)
    path = repository_path(ref)
    result = chunk_repository(path)

    total_lines = sum(chunk.line_count for chunk in result.chunks)
    chunk_count = len(result.chunks)
    shown = result.chunks[:MAX_CHUNKS_IN_RESPONSE]

    return ChunkResponse(
        owner=ref.owner,
        name=ref.name,
        file_count=result.file_count,
        chunk_count=chunk_count,
        total_lines=total_lines,
        average_lines_per_chunk=(
            round(total_lines / chunk_count, 1) if chunk_count else 0.0
        ),
        chunk_size_lines=CHUNK_SIZE_LINES,
        chunk_overlap_lines=CHUNK_OVERLAP_LINES,
        chunks=[
            ChunkSummary(
                chunk_id=chunk.chunk_id,
                file_path=chunk.file_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                line_count=chunk.line_count,
                preview=chunk.preview,
                symbol_name=chunk.symbol_name,
                symbol_type=chunk.symbol_type,
            )
            for chunk in shown
        ],
        truncated=chunk_count > len(shown),
        symbol_counts=count_symbols(result.chunks),
    )


@app.get(
    "/repositories/{owner}/{name}/dependencies",
    response_model=DependencyGraphResponse,
)
def get_dependency_graph(owner: str, name: str) -> DependencyGraphResponse:
    """Repository'nin dosya-seviyesi import grafigini dondurur."""
    ref = build_reference(owner, name)
    graph = build_dependency_graph(repository_path(ref))

    return DependencyGraphResponse(
        owner=ref.owner,
        name=ref.name,
        nodes=graph.nodes,
        edges=[DependencyEdge(source=s, target=t) for s, t in graph.edges],
    )


def _job_to_response(owner: str, name: str, job: IndexJob) -> IndexJobStatus:
    return IndexJobStatus(
        owner=owner,
        name=name,
        state=job.state,
        error=job.error,
        chunk_count=job.chunk_count,
        stored_count=job.stored_count,
        embed_duration_ms=job.embed_duration_ms,
        store_duration_ms=job.store_duration_ms,
    )


@app.post("/repositories/{owner}/{name}/index", response_model=IndexJobStatus)
def index_repository(
    owner: str, name: str, background_tasks: BackgroundTasks
) -> IndexJobStatus:
    """Repository'yi indeksleme isini arka plana atar, aninda durumu dondurur.

    Adim 20: parcalama+embedding+kaydetme buyuk repolarda uzun surebiliyor;
    bu istek onu beklemek yerine bir is baslatir. Ilerlemeyi ogrenmek icin
    GET .../index/status kullanilir. Ayni repository tekrar indekslenirse
    kayitlar cogalmaz; her parca kendi chunk_id'sinden uretilen sabit bir
    kimlige sahiptir, uzerine yazilir.
    """
    ref = build_reference(owner, name)
    repository_path(ref)  # repo indirilmemisse burada 404 firlar

    job = start_job(ref)
    background_tasks.add_task(run_job, ref)
    return _job_to_response(ref.owner, ref.name, job)


@app.get("/repositories/{owner}/{name}/index/status", response_model=IndexJobStatus)
def index_status(owner: str, name: str) -> IndexJobStatus:
    """En son baslatilan indeksleme isinin guncel durumunu dondurur."""
    ref = build_reference(owner, name)

    job = get_job(ref)
    if job is None:
        raise HTTPException(
            status_code=404, detail="Bu repository icin henuz indeksleme baslatilmadi."
        )
    return _job_to_response(ref.owner, ref.name, job)


@app.post("/repositories/{owner}/{name}/reindex", response_model=ReindexResponse)
def reindex_repository_endpoint(owner: str, name: str) -> ReindexResponse:
    """Repository'yi son commit'e gunceller, yalnizca degisen dosyalari yeniden indeksler.

    Adim 19: `/index` (yukarida) her zaman TAM indeksleme yapar - eval
    betikleri (Adim 15/16) bu davranisa dayanir ve sabit bir commit'i
    olctugu icin buradan etkilenmemelidir. Bu endpoint ayri bir yoldur:
    klonu gunceller, degisiklikleri tespit eder, yalnizca onlari isler.
    """
    ref = build_reference(owner, name)
    result = reindex_repository(ref)

    return ReindexResponse(
        owner=ref.owner,
        name=ref.name,
        previous_commit=result.previous_commit,
        commit=result.commit,
        added=result.added,
        modified=result.modified,
        deleted=result.deleted,
        unchanged_count=result.unchanged_count,
        chunk_count=result.chunk_count,
        embed_duration_ms=result.embed_ms,
        store_duration_ms=result.store_ms,
    )


def to_hit_out(hit: SearchHit) -> SearchHitOut:
    """Servis katmanindaki arama sonucunu API modeline cevirir.

    Hem /search hem /ask ayni donusumu yapiyordu. Tek yerde durunca yeni bir
    alan eklendiginde (orn. Adim 13-un vector_rank / keyword_rank alanlari)
    iki endpointten birini guncellemeyi unutma riski kalmiyor.
    """
    return SearchHitOut(
        chunk_id=hit.chunk_id,
        file_path=hit.file_path,
        start_line=hit.start_line,
        end_line=hit.end_line,
        content=hit.content,
        # RRF puanlari 0.03 civari kucuk sayilardir; 4 hanede birbirine cok
        # yakin siralar ayirt edilemiyordu, o yuzden 6 hane.
        score=round(hit.score, 6),
        symbol_name=hit.symbol_name,
        symbol_type=hit.symbol_type,
        vector_rank=hit.vector_rank,
        keyword_rank=hit.keyword_rank,
        rerank_score=hit.rerank_score,
    )


@app.post("/repositories/{owner}/{name}/search", response_model=SearchResponse)
def search_repository(
    owner: str, name: str, payload: SearchRequest
) -> SearchResponse:
    """Sorguya en alakali kod parcalarini, secilen arama moduyla dondurur."""
    started = time.perf_counter()
    rerank_ms: float | None = None
    ref = build_reference(owner, name)

    # Reranker kullanilacaksa retrieval daha genis bir havuz cekmeli;
    # asil eleme ikinci asamada, cross-encoder ile yapilacak.
    retrieve_limit = RERANK_CANDIDATES if payload.rerank else payload.limit

    if payload.mode == "keyword":
        hits = search_keywords(ref, payload.query, limit=retrieve_limit)
    elif payload.mode == "hybrid":
        hits = search_hybrid(ref, payload.query, limit=retrieve_limit)
    else:
        query_vector = embed_query(payload.query)
        hits = search_vectors(ref, query_vector, limit=retrieve_limit)

    if payload.rerank:
        rerank_started = time.perf_counter()
        hits = rerank(payload.query, hits, limit=payload.limit)
        rerank_ms = (time.perf_counter() - rerank_started) * 1000
    duration_ms = (time.perf_counter() - started) * 1000

    return SearchResponse(
        owner=ref.owner,
        name=ref.name,
        query=payload.query,
        mode=payload.mode,
        duration_ms=round(duration_ms, 1),
        rerank_ms=round(rerank_ms, 1) if rerank_ms is not None else None,
        hits=[to_hit_out(hit) for hit in hits],
    )


@app.post("/repositories/{owner}/{name}/ask", response_model=AskResponse)
def ask_repository(owner: str, name: str, payload: AskRequest) -> AskResponse:
    """Repository hakkindaki soruyu, kod kaynaklarini gostererek cevaplar.

    Akis: soru -> embedding -> Qdrant'tan en alakali parcalar -> LLM.
    Model yalnizca bu parcalara dayanarak cevap verir; kanit yoksa
    uydurmak yerine bulamadigini soyler.
    """
    ref = build_reference(owner, name)

    retrieval_started = time.perf_counter()
    # Iki asamali retrieval. Adim 13: hybrid arama (anlamsal kavrami,
    # BM25 birebir ismi yakalar) genis bir aday havuzu cikarir. Adim 14:
    # cross-encoder bu adaylari yeniden siralar ve LLM-e yalnizca en
    # alakalilari gider.
    candidates = search_hybrid(
        ref, payload.question, limit=RERANK_CANDIDATES
    )
    retrieval_ms = (time.perf_counter() - retrieval_started) * 1000

    rerank_started = time.perf_counter()
    hits = rerank(payload.question, candidates, limit=payload.limit)
    rerank_ms = (time.perf_counter() - rerank_started) * 1000

    generation_started = time.perf_counter()
    answer = generate_answer(ref, payload.question, hits)
    generation_ms = (time.perf_counter() - generation_started) * 1000

    # Modelin yazdigi kaynak referanslarini, kendisine VERILEN parcalarla
    # karsilastir. Uydurma referanslari boylece yakalariz.
    citations = verify_citations(answer.text, hits)

    return AskResponse(
        owner=ref.owner,
        name=ref.name,
        question=payload.question,
        answer=answer.text,
        model=answer.model,
        retrieval_ms=round(retrieval_ms, 1),
        rerank_ms=round(rerank_ms, 1),
        generation_ms=round(generation_ms, 1),
        sources=[to_hit_out(hit) for hit in hits],
        citations=[
            CitationOut(
                file_path=citation.file_path,
                start_line=citation.start_line,
                end_line=citation.end_line,
                status=citation.status,
                chunk_id=citation.chunk_id,
            )
            for citation in citations
        ],
        unverified_citations=count_unverified(citations),
    )


@app.post(
    "/repositories/{owner}/{name}/investigate",
    response_model=InvestigateResponse,
)
def investigate_repository(
    owner: str, name: str, payload: InvestigateRequest
) -> InvestigateResponse:
    """Soruyu cok adimli arastirmayla cevaplar (Adim 25).

    /ask tek arama yapar. Burada model araclari kendisi cagirir: arar, dosya
    okur, gordugu isimleri baska dosyalara kadar takip eder. Cevabin kaynaklari
    tek bir aramanin sonucu degil, adim adim biriken kanit havuzudur ve
    citation dogrulamasi o havuza gore yapilir.
    """
    started = time.perf_counter()
    ref = build_reference(owner, name)
    result = investigate(ref, payload.question)
    citations = verify_citations(result.text, result.evidence)
    duration_ms = (time.perf_counter() - started) * 1000

    return InvestigateResponse(
        owner=ref.owner,
        name=ref.name,
        question=payload.question,
        answer=result.text,
        model=result.model,
        duration_ms=round(duration_ms, 1),
        steps=[
            AgentStepOut(
                tool=step.tool,
                argument=step.argument,
                result_count=step.result_count,
            )
            for step in result.steps
        ],
        sources=[to_hit_out(hit) for hit in result.evidence],
        citations=[
            CitationOut(
                file_path=citation.file_path,
                start_line=citation.start_line,
                end_line=citation.end_line,
                status=citation.status,
                chunk_id=citation.chunk_id,
            )
            for citation in citations
        ],
        unverified_citations=count_unverified(citations),
    )
