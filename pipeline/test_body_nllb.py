"""Validate the NLLB body path: segment -> NLLB translate -> reassemble -> integrity.

Translates ONLY the HTML body via NLLB (the SEO elements stay on Qwen, tested
separately) and checks that the tag/href skeleton is preserved exactly. Writes a
body-only sample for eyeball QA.

Run:  python pipeline/test_body_nllb.py [--lang spa_Latn] [--model facebook/nllb-200-3.3B] [--device cuda]
"""

from __future__ import annotations

import argparse
import copy
import json
import time
from pathlib import Path

import html_segments
import validate

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
DEFAULT_CHAPTER = REPO_ROOT / "content-source/en/Isaiah/json/isaiah_14.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Test the NLLB body translation path.")
    parser.add_argument("--lang", default="spa_Latn", help="FLORES code (NLLB tgt_lang)")
    parser.add_argument("--chapter", type=Path, default=DEFAULT_CHAPTER)
    parser.add_argument("--model", help="NLLB model id (default: distilled-600M via env)")
    parser.add_argument("--device", help="cpu | cuda (default: auto)")
    args = parser.parse_args()

    # Import after arg parse so model/device env can be honored by the engine module.
    import nllb_engine
    kwargs = {}
    if args.model:
        kwargs["model_id"] = args.model
    if args.device:
        kwargs["device"] = args.device

    en = json.loads(args.chapter.read_text(encoding="utf-8"))
    seg = html_segments.segment(en["content"])
    print(f"Chapter: {args.chapter.name}  segments: {len(seg.cores)}  target: {args.lang}")

    print("Loading NLLB...")
    t_load = time.perf_counter()
    engine = nllb_engine.NLLBEngine(**kwargs)
    print(f"  loaded {engine.model_id} on {engine.device} in {time.perf_counter() - t_load:.1f}s")

    print("Translating body segments...")
    t0 = time.perf_counter()
    translated_cores = engine.translate_batch(seg.cores, args.lang)
    elapsed = time.perf_counter() - t0
    new_content = html_segments.reassemble(seg, translated_cores)
    print(f"  {len(seg.cores)} segments in {elapsed:.1f}s ({len(seg.cores)/elapsed:.1f} seg/s)")

    out = copy.deepcopy(en)
    out["content"] = new_content
    out_path = OUTPUT_ROOT / args.lang / f"{args.chapter.stem}.body.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # HTML integrity is the whole point — check tags + hrefs against the source body.
    en_tags, en_hrefs = validate._profile(en["content"])
    out_tags, out_hrefs = validate._profile(new_content)
    print("\nHTML integrity:")
    print(f"  tags identical:  {en_tags == out_tags}  ({sum(en_tags.values())} tags)")
    print(f"  hrefs identical: {en_hrefs == out_hrefs}")

    print("\nSample translations (English core -> NLLB):")
    for i in (0, 3, 6, 30):
        if i < len(seg.cores):
            src = seg.cores[i][:70]
            tgt = translated_cores[i][:70]
            print(f"  [{i}] {src!r}\n      -> {tgt!r}")

    print(f"\nOutput: {out_path}")


if __name__ == "__main__":
    main()
