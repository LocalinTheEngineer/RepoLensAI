"""RepoLens AI - Backend giris noktasi.

Su an sadece bir saglik kontrolu (health check) endpoint'i var.
Yol haritasi Adim 1: frontend ile backend'in konusabildigini kanitlamak.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Uygulama nesnesi. title/description/version degerleri
# otomatik olusan API dokumantasyonunda (/docs) gorunur.
app = FastAPI(
    title="RepoLens AI API",
    description="GitHub repository'lerini analiz eden AI developer tool'un backend servisi.",
    version="0.1.0",
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
