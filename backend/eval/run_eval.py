"""Retrieval kalitesini olcer: Recall@1/3/5 ve MRR.

Adim 13'te hybrid search, Adim 14'te reranker eklendi ve ikisi de "daha iyi
olmali" varsayimiyla yazildi. Bu betik o varsayimi sayiya cevirir: ayni soru
setini dort farkli retrieval surumunde calistirip sonuclari karsilastirir.

    semantic       yalnizca embedding (vektor) aramasi
    keyword        yalnizca BM25
    hybrid         ikisinin RRF ile birlestirilmisi
    hybrid+rerank  hybrid'in 20 adayi, cross-encoder ile yeniden siralanmis

Olcum DOSYA seviyesindedir: veri setinde her soru icin "cevabin hangi
dosyada oldugu" etiketlenmistir, satir araligi degil. Bu yuzden donen
parcalar once dosya listesine indirgenir (ayni dosyadan birden fazla parca
gelirse ilk sirasi sayilir).

    Recall@k  sorularin yuzde kacinda dogru dosya ilk k dosya arasinda cikti
    MRR       dogru dosyanin sirasinin tersinin ortalamasi (1. sira = 1.0,
              2. sira = 0.5, ... ilk 10'da hic yoksa 0)

Kullanim:

    python eval/run_eval.py --index     # repoyu once indeksle, sonra olc
    python eval/run_eval.py             # zaten indeksliyse dogrudan olc
    python eval/run_eval.py --save sonuc.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

# Betik backend/eval/ altinda; "app" paketini gorebilmek icin backend/ eklenir.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.ast_chunker import chunk_repository  # noqa: E402
from app.services.embedder import embed_query, embed_texts  # noqa: E402
from app.services.hybrid_search import search as search_hybrid  # noqa: E402
from app.services.keyword_search import search as search_keywords  # noqa: E402
from app.services.repository import (  # noqa: E402
    RepositoryError,
    RepositoryRef,
    build_reference,
    repository_path,
)
from app.services.reranker import CANDIDATE_LIMIT as RERANK_POOL  # noqa: E402
from app.services.reranker import rerank  # noqa: E402
from app.services.vector_store import SearchHit  # noqa: E402
from app.services.vector_store import search as search_vectors  # noqa: E402
from app.services.vector_store import stored_count, store_chunks  # noqa: E402

DATASET_PATH = Path(__file__).resolve().parent / "dataset.json"

# Her varyant bu kadar parca dondurur. Dosyaya indirgendiginde genelde daha
# az dosya kalir; Recall@5 icin yeterli derinlik birakmak istiyoruz.
TOP_CHUNKS = 10

# Hangi k degerleri raporlanacak.
RECALL_AT = (1, 3, 5)

VARIANTS = ("semantic", "keyword", "hybrid", "hybrid+rerank")


def retrieve(variant: str, ref: RepositoryRef, question: str) -> list[SearchHit]:
    """Bir soruyu secilen retrieval surumuyle calistirir."""
    if variant == "semantic":
        return search_vectors(ref, embed_query(question), limit=TOP_CHUNKS)

    if variant == "keyword":
        return search_keywords(ref, question, limit=TOP_CHUNKS)

    if variant == "hybrid":
        return search_hybrid(ref, question, limit=TOP_CHUNKS)

    if variant == "hybrid+rerank":
        candidates = search_hybrid(ref, question, limit=RERANK_POOL)
        return rerank(question, candidates, limit=TOP_CHUNKS)

    raise ValueError(f"bilinmeyen varyant: {variant}")


def ranked_files(hits: list[SearchHit]) -> list[str]:
    """Parca listesini, sirasi bozulmadan benzersiz dosya listesine cevirir."""
    seen: list[str] = []
    for hit in hits:
        if hit.file_path not in seen:
            seen.append(hit.file_path)
    return seen


def first_correct_rank(files: list[str], expected: list[str]) -> int | None:
    """Beklenen dosyalardan ilkinin kacinci sirada ciktigi (1'den baslar)."""
    wanted = set(expected)
    for position, path in enumerate(files, start=1):
        if path in wanted:
            return position
    return None


def evaluate(variant: str, ref: RepositoryRef, questions: list[dict]) -> dict:
    """Bir varyanti butun soru setinde calistirip metrikleri hesaplar."""
    hit_counts = {k: 0 for k in RECALL_AT}
    reciprocal_total = 0.0
    per_category: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "hits": 0}
    )
    misses: list[dict] = []

    started = time.perf_counter()

    for item in questions:
        files = ranked_files(retrieve(variant, ref, item["question"]))
        rank = first_correct_rank(files, item["expected_files"])

        for k in RECALL_AT:
            if rank is not None and rank <= k:
                hit_counts[k] += 1

        reciprocal_total += (1 / rank) if rank is not None else 0.0

        bucket = per_category[item["category"]]
        bucket["total"] += 1
        if rank == 1:
            bucket["hits"] += 1

        # Recall bu veri setinde tavana vuruyor, yani "kacirilan" diye bir
        # sey neredeyse kalmiyor. Asil ogretici olan, dogru dosyayi ILK
        # siraya koyamadigi sorular; teshis icin onlari topluyoruz.
        if rank != 1:
            misses.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "expected": item["expected_files"],
                    "rank": rank,
                    "got": files[:3],
                }
            )

    elapsed_ms = (time.perf_counter() - started) * 1000
    total = len(questions)

    return {
        "variant": variant,
        "recall": {k: hit_counts[k] / total for k in RECALL_AT},
        "mrr": reciprocal_total / total,
        "ms_per_question": elapsed_ms / total,
        "per_category": {
            name: data["hits"] / data["total"]
            for name, data in sorted(per_category.items())
        },
        "misses": misses,
    }


def warm_up(ref: RepositoryRef, questions: list[dict]) -> None:
    """Modelleri ve BM25 indeksini olcumden once yukler.

    Aksi halde ilk calisan varyant, embedding modelinin yuklenmesi ve BM25
    indeksinin kurulmasi maliyetini de ustlenir; olculen sure o varyant
    aleyhine sisiyordu (ayni varyant iki kosuda 33 ms ve 117 ms cikti).
    Hepsini bir kez calistirip esit sartlari sagliyoruz.
    """
    sample = questions[0]["question"]
    search_vectors(ref, embed_query(sample), limit=1)
    search_keywords(ref, sample, limit=1)
    rerank(sample, search_hybrid(ref, sample, limit=2), limit=1)


def index_repository(ref: RepositoryRef) -> None:
    """Repoyu indeksler; /repositories/.../index endpointiyle ayni akis."""
    print(f"indeksleniyor: {ref.owner}/{ref.name}")
    result = chunk_repository(repository_path(ref))
    print(f"  {len(result.chunks)} parca cikti, embedding uretiliyor...")

    started = time.perf_counter()
    vectors = embed_texts([chunk.content for chunk in result.chunks])
    print(f"  embedding: {(time.perf_counter() - started):.1f} sn")

    written = store_chunks(ref, result.chunks, vectors)
    print(f"  {written} parca veritabanina yazildi\n")


def print_report(results: list[dict], total_questions: int) -> None:
    """Varyantlari yan yana bir tabloda gosterir."""
    print(f"\n{'=' * 78}")
    print(f"RETRIEVAL DEGERLENDIRMESI - {total_questions} soru, dosya seviyesi")
    print("=" * 78)

    header = f"{'varyant':<16}" + "".join(f"{f'Recall@{k}':>11}" for k in RECALL_AT)
    print(f"{header}{'MRR':>9}{'ms/soru':>10}")
    print("-" * 78)

    for result in results:
        row = f"{result['variant']:<16}"
        row += "".join(f"{result['recall'][k]:>10.1%} " for k in RECALL_AT)
        row += f"{result['mrr']:>8.3f} {result['ms_per_question']:>9.0f}"
        print(row)

    best = max(results, key=lambda r: r["mrr"])
    print(f"\nEn iyi MRR: {best['variant']} ({best['mrr']:.3f})")

    print(f"\n{'-' * 78}")
    print("Kategori bazinda Recall@1")
    print("-" * 78)

    categories = sorted(results[0]["per_category"])
    print(f"{'kategori':<20}" + "".join(f"{r['variant']:>16}" for r in results))
    for category in categories:
        row = f"{category:<20}"
        row += "".join(f"{r['per_category'].get(category, 0):>15.0%} " for r in results)
        print(row)

    print(f"\n{'-' * 78}")
    print(f"{best['variant']}: dogru dosyayi ilk siraya koyamadiklari ({len(best['misses'])})")
    print("-" * 78)
    for miss in best["misses"]:
        yer = f"{miss['rank']}. sirada" if miss["rank"] else "ilk 10-da yok"
        print(f"  [{miss['id']}] {miss['question']}  -> {yer}")
        print(f"      beklenen: {', '.join(miss['expected'])}")
        print(f"      gelen   : {', '.join(miss['got']) or '(sonuc yok)'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--index",
        action="store_true",
        help="Olcumden once repoyu yeniden indeksle",
    )
    parser.add_argument(
        "--save",
        metavar="DOSYA",
        help="Sonuclari JSON olarak bu dosyaya yaz",
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=VARIANTS,
        default=list(VARIANTS),
        help="Yalnizca bu varyantlari calistir",
    )
    args = parser.parse_args()

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    repo = dataset["repository"]
    questions = dataset["questions"]
    ref = build_reference(repo["owner"], repo["name"])

    if args.index:
        index_repository(ref)

    if stored_count(ref) == 0:
        print(
            f"{repo['owner']}/{repo['name']} indekslenmemis.\n"
            f"Once klonlayin ({repo['url']}), sonra --index ile calistirin.",
            file=sys.stderr,
        )
        return 1

    print("modeller isitiliyor ...", flush=True)
    warm_up(ref, questions)

    results = []
    for variant in args.variants:
        print(f"calisiyor: {variant} ...", flush=True)
        results.append(evaluate(variant, ref, questions))

    print_report(results, len(questions))

    if args.save:
        payload = {
            "repository": repo,
            "question_count": len(questions),
            "top_chunks": TOP_CHUNKS,
            "results": results,
        }
        Path(args.save).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nsonuclar yazildi: {args.save}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RepositoryError as error:
        print(f"HATA: {error.message}", file=sys.stderr)
        raise SystemExit(1) from error
