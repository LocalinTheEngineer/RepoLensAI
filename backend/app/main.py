"""RepoLens AI - Backend giris noktasi.

Yol haritasi:
  Adim 1: /health         -> frontend ile backend konusabiliyor
  Adim 2: /repositories   -> verilen GitHub URL'sindeki repo clone ediliyor
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import CloneRequest, CloneResponse
from app.services.repository import (
    RepositoryError,
    clone_repository,
    parse_github_url,
)

# Uygulama nesnesi. title/description/version degerleri
# otomatik olusan API dokumantasyonunda (/docs) gorunur.
app = FastAPI(
    title="RepoLens AI API",
    description="GitHub repository'lerini analiz eden AI developer tool'un backend servisi.",
    version="0.2.0",
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
    try:
        ref = parse_github_url(payload.url)
        path, commit, already_cloned = clone_repository(ref)
    except RepositoryError as error:
        raise HTTPException(
            status_code=error.status_code, detail=error.message
        ) from error

    return CloneResponse(
        owner=ref.owner,
        name=ref.name,
        path=str(path),
        commit=commit,
        already_cloned=already_cloned,
    )
