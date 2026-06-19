"""TEST B - pipeline mechanics: per-element translate -> reinsert -> validate.

Translates one chapter into one language element-by-element (content, title,
metaDescription, keywords, faq) against the shared English context, reassembles the
full chapter JSON (static fields carried over), validates structural + HTML
integrity, and writes the result to pipeline/output/<lang>/<file> for human QA.

Run:  python pipeline/test_mechanics.py [--lang spa_Latn] [--model qwen/qwen3.5-9b]
      python pipeline/test_mechanics.py --chapter content-source/en/Isaiah/json/isaiah_14.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import client
import config
import fields
import validate

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
DEFAULT_CHAPTER = REPO_ROOT / "content-source/en/Isaiah/json/isaiah_14.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate one chapter and validate it.")
    parser.add_argument("--lang", default="spa_Latn", help="FLORES code (default: spa_Latn)")
    parser.add_argument("--chapter", type=Path, default=DEFAULT_CHAPTER,
                        help="Path to the English chapter JSON")
    parser.add_argument("--model", help="Override MODEL_ID (e.g. qwen/qwen3.5-9b)")
    args = parser.parse_args()
    if args.model:
        config.MODEL_ID = args.model

    lang_name = config.language_name(args.lang)
    chapter_path = args.chapter if args.chapter.is_absolute() else (REPO_ROOT / args.chapter)
    en_obj = json.loads(chapter_path.read_text(encoding="utf-8"))

    print(f"Translating {chapter_path.name} -> {lang_name} ({args.lang})")
    print(f"Model: {config.MODEL_ID} @ {config.BASE_URL}\n")

    translated, timings = client.translate_chapter(en_obj, lang_name)
    out_obj = fields.reinsert(en_obj, translated)

    out_path = OUTPUT_ROOT / args.lang / chapter_path.name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    total_s = sum(t.total_time for t in timings.values())
    comp = sum((t.completion_tokens or 0) for t in timings.values())
    print(f"\nDone in {total_s:.1f}s across {len(timings)} elements "
          f"({comp} completion tokens total)")
    print(f"Translated title: {out_obj.get('title', '')!r}\n")

    checks = validate.validate(en_obj, out_obj)
    print("Validation:")
    print(validate.format_report(checks))

    passed = validate.all_critical_passed(checks)
    print(f"\nOverall: {'PASS' if passed else 'FAIL'}")
    print(f"Output: {out_path}")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
