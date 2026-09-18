"""Adim 21 - entegrasyon testi: index -> search -> ask akisinin tamami.

Gercek olan: git deposu, dosya tarama, AST chunking, embedding, Qdrant,
hybrid retrieval, reranker ve citation dogrulamasi.
Sahte olan yalnizca LLM cagrisi - gercek Gemini istegi kota harcar ve
API anahtari ister, o yuzden `app.main.generate_answer` mock'lanir.

Gecici bir klasore calisir: WORKSPACE_DIR ve STORAGE_DIR oraya yonlendirilir,
projenin gercek `workspace/` ve `qdrant_data/` klasorlerine dokunulmaz.

Yavastir (iki model yuklenir, ~1 dakika). Yalnizca bunu calistirmak icin:

    cd backend
    python -m unittest tests.test_integration
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import repository, vector_store  # noqa: E402
from app.services.answerer import Answer  # noqa: E402
from app.services.ast_chunker import chunk_repository  # noqa: E402
from app.services.embedder import embed_texts  # noqa: E402
from app.services.hybrid_search import search as search_hybrid  # noqa: E402
from app.services.repository import build_reference, repository_path  # noqa: E402

OWNER = "testowner"
NAME = "testrepo"

FILES = {
    "auth.py": (
        "import bcrypt\n"
        "\n"
        "\n"
        "def verify_password(raw, hashed):\n"
        '    """Check a plain password against its stored hash."""\n'
        "    return bcrypt.checkpw(raw.encode(), hashed)\n"
        "\n"
        "\n"
        "def login(email, password, users):\n"
        '    """Log a user in, or raise if the credentials are wrong."""\n'
        "    user = users.find(email)\n"
        "    if not verify_password(password, user.password_hash):\n"
        "        raise ValueError('invalid credentials')\n"
        "    return user\n"
    ),
    "config.py": (
        "import os\n"
        "\n"
        "\n"
        "def load_settings():\n"
        '    """Read configuration values from the environment."""\n'
        "    return {\n"
        "        'debug': os.environ.get('DEBUG') == '1',\n"
        "        'database_url': os.environ.get('DATABASE_URL'),\n"
        "    }\n"
    ),
    "README.md": "# Test repo\n\nA tiny repository used by the integration test.\n",
}


def fake_answer(ref, question, hits) -> Answer:
    """LLM yerine gecer: ilk kaynagi dogru, bir dosyayi da uydurarak gosterir.

    Referansi gelen parcadan uretiyoruz; boylece "dogrulanmis" durum gercek
    chunk sinirlarina dayaniyor, teste sabit satir numarasi gomulmuyor.
    """
    first = hits[0]
    return Answer(
        text=(
            f"Sifre kontrolu {first.file_path}:{first.start_line}-{first.end_line} "
            "icinde yapiliyor. Ayrica yokdosya.py:1-2 dosyasina bakin."
        ),
        model="sahte-model",
    )


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        base = Path(tmp.name)

        # Qdrant yerel modda klasoru kilitler; gecici klasor silinmeden once
        # istemci kapatilmali. Cleanup'lar LIFO calisir, bu yuzden tmp'den
        # SONRA kaydedilen bu temizlik ONCE calisir.
        cls.addClassCleanup(cls._reset_client)

        workspace = base / "workspace"
        repo_dir = workspace / OWNER / NAME
        repo_dir.mkdir(parents=True)
        for name, text in FILES.items():
            (repo_dir / name).write_text(text, encoding="utf-8")

        # scan_repository `git ls-files` kullaniyor: gercek bir depo sart.
        cls._git(repo_dir, "init", "-q")
        cls._git(repo_dir, "add", "-A")
        cls._git(
            repo_dir,
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-q",
            "-m",
            "ilk",
        )

        cls.enterClassContext(
            mock.patch.object(repository, "WORKSPACE_DIR", workspace)
        )
        cls.enterClassContext(
            mock.patch.object(vector_store, "STORAGE_DIR", base / "qdrant")
        )
        cls._reset_client()

        cls.ref = build_reference(OWNER, NAME)
        result = chunk_repository(repository_path(cls.ref))
        cls.chunk_count = len(result.chunks)
        vectors = embed_texts([chunk.content for chunk in result.chunks])
        vector_store.store_chunks(cls.ref, result.chunks, vectors)

    @staticmethod
    def _git(cwd: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(cwd), *args], check=True)

    @staticmethod
    def _reset_client() -> None:
        """Acik Qdrant istemcisini kapatir; bir sonraki cagri yenisini acar."""
        if vector_store._client is not None:
            vector_store._client.close()
            vector_store._client = None

    def test_indeksleme_parca_uretti(self) -> None:
        self.assertGreater(self.chunk_count, 0)
        self.assertEqual(vector_store.stored_count(self.ref), self.chunk_count)

    def test_hybrid_arama_dogru_dosyayi_buluyor(self) -> None:
        hits = search_hybrid(
            self.ref, "how does the app check a user password", limit=5
        )

        self.assertTrue(hits)
        self.assertIn("auth.py", [hit.file_path for hit in hits])

    def test_agent_araclari_kanit_topluyor(self) -> None:
        """Agent'in araclari - model cagrisi olmadan.

        Modeli cagirmak icin canli bir Gemini gerekir; araclar ise bizim
        kodumuz ve burada gercek repo uzerinde calisiyor.
        """
        from app.services.agent import Recorder, build_tools

        recorder = Recorder()
        tools = {tool.__name__: tool for tool in build_tools(self.ref, recorder)}

        self.assertIn("auth.py", tools["search_code"]("how is a password checked"))
        self.assertIn("verify_password", tools["search_symbol"]("verify_password"))
        self.assertIn("bcrypt", tools["read_file"]("auth.py", 1, 6))
        self.assertIn("auth.py", tools["find_references"]("verify_password"))

        # Her cagri bir adim olarak kaydedilmeli, kanit havuzu birikmeli.
        self.assertEqual(
            [step.tool for step in recorder.steps],
            ["search_code", "search_symbol", "read_file", "find_references"],
        )
        self.assertTrue(recorder.evidence)

        # read_file ile okunan aralik da kanit sayilmali; yoksa model oradan
        # gordugu bir satiri kaynak gosterince "uydurma" damgasi yerdi.
        okunan = [hit for hit in recorder.evidence if hit.chunk_id == "auth.py:1-6"]
        self.assertEqual(len(okunan), 1)

    def test_agent_arac_tip_ipuclari_metne_donmemis(self) -> None:
        """Arac parametrelerinin tip ipuclari GERCEK tip olmali, metin degil.

        `agent.py`'ye `from __future__ import annotations` eklenirse butun
        ipuclari metne doner; SDK arac semasini cikaramaz ve araclari
        otomatik CALISTIRMAZ - ham function_call donderir. Bu sessiz bir
        bozulma: kod calisir, agent hicbir sey yapmadan bos cevap uretir.
        """
        import inspect

        from app.services.agent import Recorder, build_tools

        for tool in build_tools(self.ref, Recorder()):
            for parametre in inspect.signature(tool).parameters.values():
                self.assertNotIsInstance(
                    parametre.annotation,
                    str,
                    f"{tool.__name__}({parametre.name}) ipucu metne donmus",
                )

    def test_servis_hatasi_http_cevabina_cevriliyor(self) -> None:
        """Endpointler artik try/except tasimiyor; ceviriyi tek handler yapiyor.

        Handler bozulursa bu istek 500 doner - yani sessizce degil, burada
        patlar.
        """
        from fastapi.testclient import TestClient

        from app import main

        client = TestClient(main.app)
        response = client.get("/repositories/yok/boyle-bir-repo/files")

        self.assertEqual(response.status_code, 404)
        self.assertIn("detail", response.json())

    def test_agent_repo_disina_cikamaz(self) -> None:
        """Yolu model uretiyor; repo kokunun disina cikmasi engellenmeli."""
        from app.services.agent import safe_path
        from app.services.repository import RepositoryError

        # Ters boluyu KULLANMIYORUZ: Linux'ta o bir yol ayraci degil, sadece
        # garip bir dosya adidir ve repo icinde kalir. Asagidaki iki bicim
        # her iki isletim sisteminde de disari cikmayi dener.
        for kotu in ("../../../etc/passwd", "/etc/passwd"):
            with self.assertRaises(RepositoryError, msg=kotu):
                safe_path(self.ref, kotu)

    def test_ask_citation_dogrulamasi_gercek_parcalara_bakiyor(self) -> None:
        from fastapi.testclient import TestClient

        from app import main

        with mock.patch.object(main, "generate_answer", fake_answer):
            client = TestClient(main.app)
            response = client.post(
                f"/repositories/{OWNER}/{NAME}/ask",
                json={"question": "how is a password verified"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["model"], "sahte-model")
        self.assertTrue(body["sources"])

        statuses = {c["file_path"]: c["status"] for c in body["citations"]}
        self.assertEqual(statuses["yokdosya.py"], "unknown_file")
        self.assertEqual(body["unverified_citations"], 1)

        # Uydurma olmayan tek referans dogrulanmis olmali.
        gercek = [c for c in body["citations"] if c["file_path"] != "yokdosya.py"]
        self.assertEqual([c["status"] for c in gercek], ["verified"])


if __name__ == "__main__":
    unittest.main()
