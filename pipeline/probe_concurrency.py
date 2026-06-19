"""Concurrency probe — does aggregate generation throughput scale with parallel requests?

Single 12 GB GPU already loaded with Qwen, so this answers empirically whether LM
Studio serializes requests (one slot) or runs parallel slots that raise aggregate
tok/s. Fires N identical moderate-length requests (the faq element, ~400 tok) at
increasing concurrency and reports wall time + aggregate tokens/second.

Run:  python pipeline/probe_concurrency.py [--model qwen/qwen3.5-9b] [--max 4]
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import client
import config

REPO_ROOT = Path(__file__).resolve().parents[1]
CHAPTER = REPO_ROOT / "content-source/en/Isaiah/json/isaiah_14.json"
FAQ = config.ELEMENT_BY_KEY["faq"]  # moderate generation (~400 tok), shared prefix


def one_call(en_obj: dict, language: str) -> int:
    _, result = client.translate_element(en_obj, FAQ, language)
    return result.completion_tokens or 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe parallel-request throughput.")
    parser.add_argument("--model", help="Override MODEL_ID")
    parser.add_argument("--max", type=int, default=4, help="Max concurrency to test")
    args = parser.parse_args()
    if args.model:
        config.MODEL_ID = args.model

    en = json.loads(CHAPTER.read_text(encoding="utf-8"))
    print(f"Model: {config.MODEL_ID}  @ {config.BASE_URL}")
    print("Warmup...")
    client.translate_element(en, FAQ, "Spanish")

    langs = ["Spanish", "French", "German", "Italian", "Portuguese", "Dutch", "Polish", "Czech"]
    print("\n  N  wall_s  total_tok  aggregate_tok/s  per_req_tok/s")
    baseline = None
    for n in range(1, args.max + 1):
        batch = langs[:n]
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=n) as pool:
            toks = list(pool.map(lambda lg: one_call(en, lg), batch))
        wall = time.perf_counter() - t0
        total = sum(toks)
        agg = total / wall
        per_req = agg / n
        if n == 1:
            baseline = agg
        print(f"  {n:>2} {wall:>6.1f} {total:>9} {agg:>15,.1f} {per_req:>13,.1f}")

    print("\nInterpretation:")
    print("  aggregate tok/s rising with N  -> parallel slots help (concurrency is a real lever)")
    print("  aggregate tok/s flat with N    -> requests serialized on one slot (no speedup)")
    print("  errors / OOM at higher N       -> GPU can't host parallel KV caches at this context")


if __name__ == "__main__":
    main()
