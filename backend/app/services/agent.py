"""Adim 25 - Repo Agent: tek aramayla cevaplanmayan sorular icin.

`/ask` tek atisliktir: bir arama yapar, bulduklarini modele verir, cevap
ister. "Login neden bazen 401 donuyor?" gibi bir soruda bu yetmez - cevap
birden fazla dosyaya dagilmistir ve nereye bakilacagi ancak ilk bulgudan
sonra belli olur.

Agent bu yuzden dongu halinde calisir: modele arama ve okuma araclari
verilir, model hangi araci ne zaman cagiracagina kendisi karar verir, her
cagri yeni kanit getirir, kanit yeterli olunca cevabi yazar.

Planlama akisini elle kurmuyoruz; Gemini'nin function calling ozelligi bunu
zaten yapiyor. Bizim isimiz araclari tanimlamak, cagrilari kaydetmek ve
toplanan kaniti citation dogrulamasina vermek.

Araclar SALT OKUNURDUR: arama, dosya okuma, referans bulma. Kabuk komutu ya
da kod calistirma yoktur ve `read_file` repo klasorunun disina cikamaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from google.genai import types

from app.services.answerer import (
    FALLBACK_MODELS,
    MODEL_NAME,
    TEMPERATURE,
    describe_api_failure,
    get_client,
    is_retriable_error,
)
from app.services.hybrid_search import search as search_hybrid
from app.services.keyword_search import search as search_keywords
from app.services.repository import (
    RepositoryError,
    RepositoryRef,
    repository_path,
)
from app.services.reranker import CANDIDATE_LIMIT as RERANK_POOL
from app.services.reranker import rerank
from app.services.vector_store import SearchHit

# Model en fazla bu kadar arac cagirabilir. Sinir yoksa bir sorunun
# maliyeti ongorulemez hale gelir; 8 cagri pratikte bol bol yetiyor.
MAX_TOOL_CALLS = 8

# Tek bir arama kac parca dondursun.
HITS_PER_SEARCH = 5

# read_file tek seferde en fazla bu kadar satir verir; model butun dosyayi
# isteyip context'i doldurmasin.
MAX_FILE_LINES = 200

# Agent'in cevabi /ask'inkinden uzun olabilir: birden fazla dosyayi anlatiyor.
MAX_OUTPUT_TOKENS = 2000

SYSTEM_PROMPT = """You are a code investigator working on one specific GitHub repository.

You have read-only tools. Use them to gather evidence before answering. A
typical investigation: search for the area, read the file around what you
found, follow the names you saw into other files.

Rules:

1. Break the question into steps and use the tools. Do not answer from general
   knowledge about the library or framework, even if you are confident.
2. Keep going until you have actual evidence. If your first search is not
   enough, search again with different words, or read the file around a hit.
3. Before you write the final answer, check whether the evidence you collected
   actually answers the question. If it does not, say plainly which part you
   could not find evidence for. Never fill a gap with a guess.
4. Never invent file paths, identifiers or line numbers. Only mention things
   that literally appeared in tool results.
5. The final answer MUST cite its evidence as `path:start-end`, using ranges
   that appeared in tool results. Narrowing a range is fine; going outside one
   is not.
6. Be concrete and brief: describe the real mechanism, and say which file does
   which part. Answer in English."""


@dataclass
class Step:
    """Agent'in attigi tek bir adim."""

    tool: str
    argument: str
    result_count: int


@dataclass
class Investigation:
    """Agent'in cevabi, attigi adimlar ve topladigi kanit."""

    text: str
    model: str
    steps: list[Step] = field(default_factory=list)
    evidence: list[SearchHit] = field(default_factory=list)


class Recorder:
    """Arac cagrilarini ve toplanan kaniti biriktirir.

    Kanit citation dogrulamasina gidecek: model yalnizca gercekten gordugu
    satirlari kaynak gosterebilsin diye.
    """

    def __init__(self) -> None:
        self.steps: list[Step] = []
        self.evidence: list[SearchHit] = []
        self._seen: set[str] = set()

    def add(self, tool: str, argument: str, hits: list[SearchHit]) -> None:
        self.steps.append(Step(tool=tool, argument=argument, result_count=len(hits)))
        for hit in hits:
            if hit.chunk_id not in self._seen:
                self._seen.add(hit.chunk_id)
                self.evidence.append(hit)


def format_hits(hits: list[SearchHit]) -> str:
    """Parcalari modelin okuyacagi metne cevirir.

    Basliklar `path:start-end` bicimindedir; model kaynak gosterirken bunlari
    aynen kopyalayacak.
    """
    if not hits:
        return "No results."

    bolumler = []
    for hit in hits:
        etiket = f" ({hit.symbol_type} {hit.symbol_name})" if hit.symbol_name else ""
        bolumler.append(
            f"--- {hit.file_path}:{hit.start_line}-{hit.end_line}{etiket} ---\n"
            f"{hit.content}"
        )
    return "\n\n".join(bolumler)


def safe_path(ref: RepositoryRef, relative: str) -> Path:
    """Model'in verdigi yolu repo klasorune hapseder.

    Yolu model uretiyor, yani guvenilmez girdi. `..` ya da mutlak yol
    verildiginde repo disina cikilmasini burada engelliyoruz.
    """
    root = repository_path(ref).resolve()
    target = (root / relative).resolve()

    if not target.is_relative_to(root):
        raise RepositoryError(f"Repo disinda dosya okunamaz: {relative}")

    return target


def build_tools(ref: RepositoryRef, recorder: Recorder) -> list:
    """Agent'a verilecek salt okunur araclari uretir.

    Docstring'ler modele gonderilen arac aciklamalaridir; bu yuzden
    Ingilizce ve modelin ne zaman hangisini secmesi gerektigini anlatir
    bicimde yazildilar.
    """

    def search_code(query: str) -> str:
        """Find code related to a question or concept, by meaning.

        Use this first, and whenever you need code you cannot name exactly.
        Example queries: "where is the session cookie signed", "how are
        errors turned into responses".
        """
        hits = rerank(
            query,
            search_hybrid(ref, query, limit=RERANK_POOL),
            limit=HITS_PER_SEARCH,
        )
        recorder.add("search_code", query, hits)
        return format_hits(hits)

    def search_symbol(name: str) -> str:
        """Find the definition of an exact identifier.

        Use this when you already know the name of a function, class or
        constant, for example "SecureCookieSessionInterface" or "locate_app".
        """
        hits = search_keywords(ref, name, limit=HITS_PER_SEARCH)
        recorder.add("search_symbol", name, hits)
        return format_hits(hits)

    def read_file(path: str, start_line: int, end_line: int) -> str:
        """Read an exact line range of a file, to see context around a hit.

        Use this when a search result is cut off, or when you need the lines
        just before or after something you found. Paths must be exactly as
        they appeared in earlier results.
        """
        target = safe_path(ref, path)
        if not target.is_file():
            return f"No such file: {path}"

        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, start_line)
        end = min(len(lines), max(start, end_line), start + MAX_FILE_LINES - 1)
        content = "\n".join(lines[start - 1 : end])

        # Okunan araligi da kanit havuzuna koyuyoruz; yoksa model buradan
        # gordugu bir satiri kaynak gosterince "uydurma" sayilirdi.
        hit = SearchHit(
            chunk_id=f"{path}:{start}-{end}",
            file_path=path,
            start_line=start,
            end_line=end,
            content=content,
            score=0.0,
        )
        recorder.add("read_file", f"{path}:{start}-{end}", [hit])
        return f"--- {path}:{start}-{end} ---\n{content}"

    def find_references(name: str) -> str:
        """List the places where an identifier is used across the repository.

        Use this to follow a name outwards: who calls this function, where is
        this config key read. Returns locations, not full code.
        """
        hits = search_keywords(ref, name, limit=HITS_PER_SEARCH * 2)
        recorder.add("find_references", name, hits)

        if not hits:
            return "No results."

        return "\n".join(
            f"{hit.file_path}:{hit.start_line}-{hit.end_line}"
            + (f" ({hit.symbol_type} {hit.symbol_name})" if hit.symbol_name else "")
            for hit in hits
        )

    def read_tests(query: str) -> str:
        """Find tests covering a behaviour.

        Tests often state the expected behaviour more plainly than the code
        does. Use this to confirm what something is supposed to do.
        """
        hits = [
            hit
            for hit in search_hybrid(ref, query, limit=RERANK_POOL)
            if "test" in hit.file_path.lower()
        ][:HITS_PER_SEARCH]
        recorder.add("read_tests", query, hits)
        return format_hits(hits)

    return [search_code, search_symbol, read_file, find_references, read_tests]


def investigate(ref: RepositoryRef, question: str) -> Investigation:
    """Soruyu cok adimli arastirmayla cevaplar."""
    client = get_client()
    recorder = Recorder()

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=build_tools(ref, recorder),
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        # SDK arac cagrilarini kendisi yurutur; bizim isimiz sinir koymak.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            maximum_remote_calls=MAX_TOOL_CALLS
        ),
    )

    last_error: Exception | None = None

    for model_name in [MODEL_NAME, *FALLBACK_MODELS]:
        try:
            # Arac cagirma dongusu icin SDK sohbet arayuzunu oneriyor;
            # generate_content ile kullanildiginda uyari basiyor.
            chat = client.chats.create(model=model_name, config=config)
            response = chat.send_message(question)
        except Exception as error:
            last_error = error
            if is_retriable_error(error):
                continue
            message, status_code = describe_api_failure(error)
            raise RepositoryError(message, status_code=status_code) from error

        text = (response.text or "").strip()
        if text:
            return Investigation(
                text=text,
                model=model_name,
                steps=recorder.steps,
                evidence=recorder.evidence,
            )

        last_error = RuntimeError("bos cevap")

    if last_error is not None and is_retriable_error(last_error):
        raise RepositoryError(
            "Denenen modellerin hepsi su an mesgul ya da istek sinirina "
            "takildi. Birkac dakika bekleyip tekrar dene.",
            status_code=503,
        ) from last_error

    raise RepositoryError(
        "Model bos cevap dondurdu. Tekrar dene.", status_code=502
    )
