"""Adim 21 - birim testleri: filtreleme, chunking, parsing, citation.

Model yuklemez, ag kullanmaz, diske yazmaz. Yaklasik 6 saniye surer -
neredeyse tamami keyword_search uzerinden gelen qdrant istemcisi import
maliyeti; testlerin kendisi milisaniyeler icinde biter.

    cd backend
    python -m unittest discover tests
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import citations  # noqa: E402
from app.services.ast_chunker import chunk_source  # noqa: E402
from app.services.chunker import CHUNK_SIZE_LINES, chunk_text  # noqa: E402
from app.services.dependency_graph import (  # noqa: E402
    build_python_index,
    extract_python_imports,
)
from app.services.file_scanner import is_in_ignored_directory  # noqa: E402
from app.services.hybrid_search import fuse  # noqa: E402
from app.services.incremental_index import diff_files  # noqa: E402
from app.services.keyword_search import tokenize  # noqa: E402
from app.services.repository import RepositoryError, parse_github_url  # noqa: E402
from app.services.vector_store import SearchHit  # noqa: E402


def make_hit(file_path: str, start: int, end: int) -> SearchHit:
    """Testlerde kullanilan sade bir arama sonucu."""
    return SearchHit(
        chunk_id=f"{file_path}:{start}-{end}",
        file_path=file_path,
        start_line=start,
        end_line=end,
        content="...",
        score=1.0,
    )


class FilteringTests(unittest.TestCase):
    def test_uretilmis_klasorler_elenir(self) -> None:
        for path in (
            "node_modules/react/index.js",
            "app/dist/bundle.js",
            "a/b/__pycache__/c.py",
        ):
            self.assertTrue(is_in_ignored_directory(path), path)

    def test_kaynak_dosyalar_kalir(self) -> None:
        for path in ("src/app.py", "README.md", "a/b/c.tsx"):
            self.assertFalse(is_in_ignored_directory(path), path)

    def test_yalnizca_klasor_adina_bakilir(self) -> None:
        # "dist" burada dosya adi, klasor degil; elenmemeli.
        self.assertFalse(is_in_ignored_directory("src/dist.py"))


class ChunkTextTests(unittest.TestCase):
    TEXT = "\n".join(f"satir {i}" for i in range(1, 301))

    def test_metadata_butun_dosyayi_kapsar(self) -> None:
        chunks = chunk_text("a/b.py", self.TEXT)

        self.assertTrue(chunks)
        self.assertEqual(chunks[0].start_line, 1)
        self.assertEqual(chunks[-1].end_line, 300)

        for chunk in chunks:
            self.assertEqual(chunk.file_path, "a/b.py")
            self.assertEqual(
                chunk.chunk_id, f"a/b.py:{chunk.start_line}-{chunk.end_line}"
            )
            self.assertLessEqual(
                chunk.end_line - chunk.start_line + 1, CHUNK_SIZE_LINES
            )

    def test_parcalar_araya_satir_dusurmez(self) -> None:
        chunks = chunk_text("a/b.py", self.TEXT)

        for before, after in zip(chunks, chunks[1:]):
            self.assertLessEqual(after.start_line, before.end_line + 1)

    def test_bos_dosya_parca_uretmez(self) -> None:
        self.assertEqual(chunk_text("a/b.py", ""), [])
        self.assertEqual(chunk_text("a/b.py", "\n\n   \n"), [])


class AstChunkerTests(unittest.TestCase):
    SOURCE = (
        "def topla(a, b):\n"
        "    return a + b\n"
        "\n"
        "\n"
        "class Hesap:\n"
        "    def carp(self, a, b):\n"
        "        return a * b\n"
    )

    def test_semboller_isim_ve_turuyle_cikar(self) -> None:
        chunks = chunk_source("calc.py", self.SOURCE)
        by_name = {c.symbol_name: c for c in chunks if c.symbol_name}

        self.assertEqual(by_name["topla"].symbol_type, "function")
        self.assertEqual(by_name["Hesap"].symbol_type, "class")

    def test_parca_sinirlari_sembolun_kendi_satirlari(self) -> None:
        topla = next(c for c in chunk_source("calc.py", self.SOURCE) if c.symbol_name == "topla")

        self.assertEqual(topla.start_line, 1)
        self.assertEqual(topla.end_line, 2)
        self.assertIn("return a + b", topla.content)

    def test_desteklenmeyen_uzanti_satir_tabanina_duser(self) -> None:
        # Grameri olmayan diller (ve .md) icin AST yok; parca yine uretilir
        # ama sembol bilgisi tasimaz.
        chunks = chunk_source("a.rb", "puts 1\n")

        self.assertEqual(len(chunks), 1)
        self.assertIsNone(chunks[0].symbol_name)
        self.assertIsNone(chunks[0].symbol_type)


class CitationTests(unittest.TestCase):
    def test_uzantisiz_metin_referans_sayilmaz(self) -> None:
        found = citations.extract_citations("bkz app/main.py:10-20, ayrica adim 9:1-3")

        self.assertEqual(found, [("app/main.py", 10, 20)])

    def test_ayni_referans_bir_kez_doner(self) -> None:
        found = citations.extract_citations("a.py:1-5 ve yine a.py:1-5")

        self.assertEqual(found, [("a.py", 1, 5)])

    def test_uc_dogrulama_durumu(self) -> None:
        hits = [make_hit("app/main.py", 10, 40)]
        text = (
            "icerde app/main.py:12-20, "
            "disarda app/main.py:80-90, "
            "hic verilmemis other.py:1-5"
        )

        result = citations.verify_citations(text, hits)

        self.assertEqual(
            [c.status for c in result],
            ["verified", "out_of_range", "unknown_file"],
        )
        self.assertEqual(result[0].chunk_id, "app/main.py:10-40")
        self.assertEqual(citations.count_unverified(result), 2)


class RrfFusionTests(unittest.TestCase):
    """Adim 13'un cekirdegi: iki sonuc listesini sira uzerinden birlestirme."""

    def setUp(self) -> None:
        # Anlamsal: A, B, C   |   Kelime: C, D
        # C tek listede ust sirada degil ama IKI listede birden var.
        self.vector = [make_hit("A.py", 1, 10), make_hit("B.py", 1, 10), make_hit("C.py", 1, 10)]
        self.keyword = [make_hit("C.py", 1, 10), make_hit("D.py", 1, 10)]

    def test_iki_listede_birden_olan_basa_gecer(self) -> None:
        sonuc = fuse(self.vector, self.keyword, limit=5)

        self.assertEqual(sonuc[0].file_path, "C.py")
        self.assertEqual(sonuc[0].vector_rank, 3)
        self.assertEqual(sonuc[0].keyword_rank, 1)

    def test_hicbir_aday_kaybolmaz(self) -> None:
        sonuc = fuse(self.vector, self.keyword, limit=10)

        self.assertEqual({hit.file_path for hit in sonuc}, {"A.py", "B.py", "C.py", "D.py"})

    def test_tek_listede_olanin_digeri_None_kalir(self) -> None:
        sonuc = {hit.file_path: hit for hit in fuse(self.vector, self.keyword, limit=10)}

        self.assertIsNone(sonuc["A.py"].keyword_rank)
        self.assertIsNone(sonuc["D.py"].vector_rank)

    def test_ayni_girdi_ayni_sirayi_uretir(self) -> None:
        # Esit puanlarda siralama chunk_id'ye dusuyor; rastgelelik olmamali.
        birinci = [hit.chunk_id for hit in fuse(self.vector, self.keyword, limit=10)]
        ikinci = [hit.chunk_id for hit in fuse(self.vector, self.keyword, limit=10)]

        self.assertEqual(birinci, ikinci)

    def test_limit_uygulanir(self) -> None:
        self.assertEqual(len(fuse(self.vector, self.keyword, limit=2)), 2)

    def test_bos_listeler(self) -> None:
        self.assertEqual(fuse([], [], limit=5), [])
        self.assertEqual(len(fuse(self.vector, [], limit=5)), 3)


class TokenizeTests(unittest.TestCase):
    """BM25'in kalbi: kod isimleri bitisik yazilir, parcalara ayrilmali."""

    def test_camel_case_bolunur(self) -> None:
        tokens = tokenize("JwtService")

        # Hem tam hali hem parcalari indekslenmeli: ikisiyle de aranabilsin.
        self.assertIn("jwtservice", tokens)
        self.assertIn("jwt", tokens)
        self.assertIn("service", tokens)

    def test_alt_cizgi_bolunur(self) -> None:
        tokens = tokenize("create_token")

        self.assertIn("create_token", tokens)
        self.assertIn("create", tokens)
        self.assertIn("token", tokens)

    def test_ardisik_buyuk_harfler(self) -> None:
        # parseHTTPUrl -> parse | HTTP | Url
        tokens = tokenize("parseHTTPUrl")

        self.assertIn("parse", tokens)
        self.assertIn("http", tokens)
        self.assertIn("url", tokens)

    def test_noktalama_token_uretmez(self) -> None:
        self.assertEqual(tokenize("--- +++ ..."), [])


class DiffFilesTests(unittest.TestCase):
    """Adim 19: artimli indekslemenin karar verdigi yer."""

    def test_eklenen_degisen_silinen(self) -> None:
        eski = {"a.py": "1", "b.py": "2", "c.py": "3"}
        yeni = {"a.py": "1", "b.py": "DEGISTI", "d.py": "4"}

        added, modified, deleted = diff_files(eski, yeni)

        self.assertEqual(added, ["d.py"])
        self.assertEqual(modified, ["b.py"])
        self.assertEqual(deleted, ["c.py"])

    def test_degisiklik_yoksa_hepsi_bos(self) -> None:
        ayni = {"a.py": "1", "b.py": "2"}

        self.assertEqual(diff_files(ayni, dict(ayni)), ([], [], []))

    def test_ilk_indeksleme_hepsini_eklenen_sayar(self) -> None:
        added, modified, deleted = diff_files({}, {"a.py": "1", "b.py": "2"})

        self.assertEqual(added, ["a.py", "b.py"])
        self.assertEqual((modified, deleted), ([], []))


class PythonImportIndexTests(unittest.TestCase):
    """Adim 18: mutlak import'lari dosyaya baglayan suffix eslesmesi."""

    def test_her_suffix_anahtar_olur(self) -> None:
        index = build_python_index(["src/flask/app.py"])

        self.assertEqual(index["src/flask/app"], "src/flask/app.py")
        self.assertEqual(index["flask/app"], "src/flask/app.py")
        self.assertEqual(index["app"], "src/flask/app.py")

    def test_cakismada_koke_en_yakin_kazanir(self) -> None:
        """Bu gercek bir hataydi: pallets/flask'ta asil paket ile testlerdeki
        fixture dosyasi ayni suffix'i uretiyordu ve kazanan belirsizdi."""
        index = build_python_index(
            ["tests/test_apps/cliapp/inner1/flask.py", "src/flask/__init__.py"]
        )

        self.assertEqual(index["flask"], "src/flask/__init__.py")

    def test_sira_sonucu_degistirmez(self) -> None:
        dosyalar = ["tests/test_apps/cliapp/inner1/flask.py", "src/flask/__init__.py"]

        self.assertEqual(
            build_python_index(dosyalar), build_python_index(list(reversed(dosyalar)))
        )

    def test_import_satirlari_cikarilir(self) -> None:
        kaynak = "import os\nfrom . import helpers\nfrom flask.app import Flask\n"

        moduller = [modul for _, modul in extract_python_imports(kaynak)]

        self.assertIn("os", moduller)
        self.assertIn("flask.app", moduller)


class RepositoryUrlTests(unittest.TestCase):
    def test_kabul_edilen_yazimlar(self) -> None:
        for raw in (
            "https://github.com/pallets/flask",
            "https://github.com/pallets/flask.git",
            "github.com/pallets/flask",
            "www.github.com/pallets/flask/",
            "  https://github.com/pallets/flask  ",
        ):
            ref = parse_github_url(raw)
            self.assertEqual((ref.owner, ref.name), ("pallets", "flask"), raw)

    def test_reddedilen_yazimlar(self) -> None:
        for raw in (
            "https://gitlab.com/pallets/flask",
            "github.com/pallets",
            "github.com/pallets/flask/extra",
            "bu bir adres degil",
            "github.com/../etc",
        ):
            with self.assertRaises(RepositoryError, msg=raw):
                parse_github_url(raw)


if __name__ == "__main__":
    unittest.main()
