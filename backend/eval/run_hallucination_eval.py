"""Adim 16: Sistem kanit yokken uydurmuyor mu, bunu olcer.

`run_eval.py` retrieval'in DOGRU dosyayi bulup bulamadigini olcuyor. Bu
betik farkli bir seyi olcuyor: repo'da hic OLMAYAN bir seyi sorunca (orn.
"Flask'in Redis entegrasyonu nasil calisiyor" - Flask'ta Redis yok) LLM
"kanit yok" diyip cekiliyor mu, yoksa uydurup kanit varmis gibi mi
cevapliyor?

Gercek pipeline calistirilir: hybrid+rerank retrieval + gercek Gemini
cagrisi. Ucretsiz/dusuk maliyetli oldugu icin varsayilan calisir; API
anahtari yoksa .env'i kontrol et.

Kullanim:

    python eval/run_hallucination_eval.py
    python eval/run_hallucination_eval.py --save sonuc.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.answerer import generate_answer  # noqa: E402
from app.services.hybrid_search import search as search_hybrid  # noqa: E402
from app.services.repository import (  # noqa: E402
    RepositoryError,
    build_reference,
)
from app.services.reranker import CANDIDATE_LIMIT as RERANK_POOL  # noqa: E402
from app.services.reranker import rerank  # noqa: E402
from app.services.vector_store import stored_count  # noqa: E402

DATASET_PATH = Path(__file__).resolve().parent / "hallucination_dataset.json"

# LLM'e giden parca sayisi; asil pipeline'daki (main.py) ayarla ayni tut.
ANSWER_CHUNKS = 6

# Sistem prompt'u modelden bu ifadelerden birini kullanmasini istiyor
# ("could not find enough evidence"). Guvenli davranisi bunlarla yakaliyoruz.
REFUSAL_MARKERS = (
    "could not find",
    "couldn't find",
    "cannot find",
    "can't find",
    "not enough evidence",
    "no evidence",
    "insufficient evidence",
    "did not find",
    "didn't find",
    "unable to find",
    "no relevant",
    "don't have enough",
    "do not have enough",
)


def is_refusal(answer_text: str) -> bool:
    text = answer_text.lower()
    return any(marker in text for marker in REFUSAL_MARKERS)


def run(questions: list[dict], ref) -> list[dict]:
    rows = []
    for item in questions:
        candidates = search_hybrid(ref, item["question"], limit=RERANK_POOL)
        hits = rerank(item["question"], candidates, limit=ANSWER_CHUNKS)
        answer = generate_answer(ref, item["question"], hits)

        rows.append(
            {
                "id": item["id"],
                "category": item["category"],
                "question": item["question"],
                "refused": is_refusal(answer.text),
                "answer": answer.text,
            }
        )
    return rows


def print_report(rows: list[dict]) -> None:
    total = len(rows)
    refused = sum(1 for r in rows if r["refused"])
    false_claims = [r for r in rows if not r["refused"]]

    print(f"\n{'=' * 78}")
    print(f"HALLUCINATION DEGERLENDIRMESI - {total} soru (repo'da olmayan konular)")
    print("=" * 78)
    print(f"guvenli ret orani (dogru davranis): {refused}/{total} ({refused / total:.1%})")
    print(f"yanlis kesin iddia orani           : {len(false_claims)}/{total} ({len(false_claims) / total:.1%})")

    print(f"\n{'-' * 78}")
    print("Kategori bazinda guvenli ret orani")
    print("-" * 78)
    categories = sorted(set(r["category"] for r in rows))
    for category in categories:
        bucket = [r for r in rows if r["category"] == category]
        hits = sum(1 for r in bucket if r["refused"])
        print(f"  {category:<20} {hits}/{len(bucket)} ({hits / len(bucket):.0%})")

    if false_claims:
        print(f"\n{'-' * 78}")
        print("Uydurma supheli cevaplar (incele):")
        print("-" * 78)
        for row in false_claims:
            print(f"  [{row['id']}] {row['question']}")
            print(f"      cevap: {row['answer'][:200]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", metavar="DOSYA", help="Sonuclari JSON olarak bu dosyaya yaz")
    args = parser.parse_args()

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    repo = dataset["repository"]
    ref = build_reference(repo["owner"], repo["name"])

    if stored_count(ref) == 0:
        print(
            f"{repo['owner']}/{repo['name']} indekslenmemis.\n"
            "Once run_eval.py --index ile indeksleyin.",
            file=sys.stderr,
        )
        return 1

    print("sorular calistiriliyor (gercek LLM cagrisi, biraz surer)...", flush=True)
    rows = run(dataset["questions"], ref)
    print_report(rows)

    if args.save:
        Path(args.save).write_text(
            json.dumps({"repository": repo, "rows": rows}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nsonuclar yazildi: {args.save}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RepositoryError as error:
        print(f"HATA: {error.message}", file=sys.stderr)
        raise SystemExit(1) from error
