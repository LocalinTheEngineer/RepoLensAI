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
