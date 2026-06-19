"""End-to-end pipeline run: N languages x 1 chapter, both tiers.

Loads NLLB once, then translates the chapter into each requested language — Tier-1
via NLLB body + Qwen SEO, Tier-2 via all-NLLB — assembles the full JSON, validates,
and writes pipeline/output/<code>/<file>. Prints a per-language pass/fail + timing
table so you can feel the workflow across both pipelines.

Default 4 languages exercise both pipelines: 2 Tier-1 (Spanish, French) + 2 Tier-2
(Welsh, Zulu).

Run:  python pipeline/run_pipeline.py
      python pipeline/run_pipeline.py --langs spa_Latn,fra_Latn,cym_Latn,zul_Latn
      python pipeline/run_pipeline.py --nllb-model facebook/nllb-200-3.3B --nllb-device cuda
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import config
import validate

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = Path(__file__).resolve().parent / "output"
DEFAULT_CHAPTER = REPO_ROOT / "content-source/en/Isaiah/json/isaiah_14.json"
DEFAULT_LANGS = ["spa_Latn", "fra_Latn", "cym_Latn", "zul_Latn"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the two-engine pipeline on one chapter.")
    parser.add_argument("--langs", default=",".join(DEFAULT_LANGS),
                        help="Comma-separated FLORES codes")
    parser.add_argument("--chapter", type=Path, default=DEFAULT_CHAPTER)
    parser.add_argument("--qwen-model", help="Override Qwen MODEL_ID")
    parser.add_argument("--nllb-model", help="NLLB model id (default: distilled-600M)")
    parser.add_argument("--nllb-device", help="cpu | cuda (default: auto)")
    args = parser.parse_args()
    if args.qwen_model:
        config.MODEL_ID = args.qwen_model

    langs = [c.strip() for c in args.langs.split(",") if c.strip()]
    chapter_path = args.chapter if args.chapter.is_absolute() else (REPO_ROOT / args.chapter)
    en_obj = json.loads(chapter_path.read_text(encoding="utf-8"))

    print(f"Chapter: {chapter_path.name}")
    print(f"Languages: " + ", ".join(
        f"{c} ({'T1/Qwen+NLLB' if config.is_tier1(c) else 'T2/NLLB'})" for c in langs))

    # Import + load NLLB once (after arg parse so device/model env can apply).
    import coordinator
    from nllb_engine import NLLBEngine
    kwargs = {}
    if args.nllb_model:
        kwargs["model_id"] = args.nllb_model
    if args.nllb_device:
        kwargs["device"] = args.nllb_device
    print("\nLoading NLLB...")
    t_load = time.perf_counter()
    nllb = NLLBEngine(**kwargs)
    print(f"  {nllb.model_id} on {nllb.device} ({time.perf_counter() - t_load:.1f}s)")

    rows = []
    for code in langs:
        name = config.display_name(code)
        print(f"\n=== {name} ({code}) ===")
        t0 = time.perf_counter()
        out_obj = coordinator.translate_chapter(en_obj, code, nllb)
        elapsed = time.perf_counter() - t0

        out_path = OUTPUT_ROOT / code / chapter_path.name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")

        checks = validate.validate(en_obj, out_obj)
        passed = validate.all_critical_passed(checks)
        print(validate.format_report(checks))
        print(f"  title: {out_obj.get('title', '')!r}")
        rows.append((code, name, "T1" if config.is_tier1(code) else "T2", passed, elapsed))

    print("\n" + "=" * 70)
    print("PIPELINE SUMMARY")
    print("=" * 70)
    print(f"  {'code':<10} {'tier':<5} {'result':<6} {'sec':>7}  name")
    for code, name, tier, passed, elapsed in rows:
        print(f"  {code:<10} {tier:<5} {'PASS' if passed else 'FAIL':<6} {elapsed:>7.1f}  {name}")
    all_ok = all(r[3] for r in rows)
    print(f"\nOverall: {'ALL PASS' if all_ok else 'SOME FAILED'}  "
          f"(outputs in {OUTPUT_ROOT})")
    raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
