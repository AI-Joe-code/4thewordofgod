"""Benchmark the NLLB body path on GPU with the production model (nllb-200-3.3B).

Loads the model once, times the sentence-aware body translation for each language,
checks HTML integrity, and writes a UTF-8 report with timing + quality samples
(incl. a 600M-vs-3.3B comparison on the segments where Welsh had word-sense errors).

Only the body is exercised (pure NLLB) — Tier-1 SEO via Qwen is skipped because
Qwen is unloaded to free VRAM for this benchmark.

Run:  python pipeline/bench_nllb_gpu.py [--model facebook/nllb-200-3.3B] [--device cuda]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import html_segments
import validate

REPO = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "output"
CHAPTER = REPO / "content-source/en/Isaiah/json/isaiah_14.json"
LANGS = [("spa_Latn", "Spanish"), ("fra_Latn", "French"), ("cym_Latn", "Welsh"), ("zul_Latn", "Zulu")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="facebook/nllb-200-3.3B")
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    import nllb_engine
    en = json.loads(CHAPTER.read_text(encoding="utf-8"))
    seg = html_segments.segment(en["content"])
    en_cores = seg.cores

    lines = [f"Model: {args.model}  Device: {args.device}  Segments: {len(en_cores)}"]
    print("Loading model...")
    t0 = time.perf_counter()
    engine = nllb_engine.NLLBEngine(model_id=args.model, device=args.device)
    load_s = time.perf_counter() - t0
    lines.append(f"Load time: {load_s:.1f}s")
    lines.append("\nPER-LANGUAGE BODY TRANSLATION (GPU):")
    lines.append(f"  {'lang':<9} {'sec':>7} {'seg/s':>7}  integrity")

    new_cores = {}
    for code, name in LANGS:
        t = time.perf_counter()
        cores = engine.translate_texts(en_cores, code)
        dt = time.perf_counter() - t
        new_cores[code] = cores
        body = html_segments.reassemble(seg, cores)
        et, eh = validate._profile(en["content"])
        ot, oh = validate._profile(body)
        ok = (et == ot and eh == oh)
        lines.append(f"  {code:<9} {dt:>7.1f} {len(en_cores)/dt:>7.1f}  {'OK' if ok else 'TAG MISMATCH'}")
        (OUT / code).mkdir(parents=True, exist_ok=True)
        (OUT / code / "isaiah_14.3b_body.json").write_text(
            json.dumps({**en, "content": body}, ensure_ascii=False, indent=2), encoding="utf-8")

    def find(s):
        return next(i for i, c in enumerate(en_cores) if s.lower() in c.lower())

    for label, idx in [("Lucifer commentary", find("Lucifer, who had enslaved")),
                       ("Hell speech (Welsh said 'river' on 600M)", find("Their speech continues in Hell"))]:
        lines.append("\n" + "=" * 80)
        lines.append(f"{label}  (segment {idx})")
        lines.append("=" * 80)
        lines.append(f"EN     : {en_cores[idx]}")
        for code, name in LANGS:
            lines.append(f"{name:7}: {new_cores[code][idx]}")

    # 600M vs 3.3B on Welsh (load prior 600M output if present).
    prior = OUT / "cym_Latn" / "isaiah_14.json"
    if prior.exists():
        old_cores = html_segments.segment(json.loads(prior.read_text(encoding="utf-8"))["content"]).cores
        lines.append("\n" + "=" * 80)
        lines.append("WELSH: 600M (prior) vs 3.3B (now)")
        lines.append("=" * 80)
        for idx in [find("Lucifer, who had enslaved"), find("Their speech continues in Hell")]:
            lines.append(f"\nseg {idx} EN  : {en_cores[idx][:160]}")
            if idx < len(old_cores):
                lines.append(f"   600M Welsh: {old_cores[idx][:160]}")
            lines.append(f"   3.3B Welsh: {new_cores['cym_Latn'][idx][:160]}")

    report = OUT / "_gpu_bench.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {report}")


if __name__ == "__main__":
    main()
