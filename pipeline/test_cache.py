"""TEST A - KV-cache prefix-reuse measurement (the make-or-break test).

Per-element flow: the shared prefix is the English-chapter context; only the
element task + language word vary. We measure prefill reuse on the cheap TITLE
element (TTFT ~= context prefill cost), then stream ONE content generation to get
the generation rate for the economics projection.

  warmup (discard)
  A: title  / Spanish / isaiah_14   -> cold prefix (prefills context)
  B: title  / French  / isaiah_14   -> identical prefix (warm if reuse works)
  C: title  / German  / isaiah_13   -> different prefix (cold control)
  G: content/ Spanish / isaiah_14   -> measure generation rate + body size

Run:  python pipeline/test_cache.py [--model qwen/qwen3.5-9b]
Watch the LM Studio SERVER LOG during request B for
  "forcing full prompt re-processing due to lack of cache data ..."
which is the definitive signal that reuse FAILED.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import client
import config

REPO_ROOT = Path(__file__).resolve().parents[1]
CHAPTER_A = REPO_ROOT / "content-source/en/Isaiah/json/isaiah_14.json"
CHAPTER_C = REPO_ROOT / "content-source/en/Isaiah/json/isaiah_13.json"  # different prefix

TITLE = config.ELEMENT_BY_KEY["title"]
CONTENT = config.ELEMENT_BY_KEY["content"]
WARMUP_OBJ = {
    "title": "Hello", "content": "<p>Hello.</p>", "metaDescription": "Hi",
    "keywords": ["hi"], "faq": [{"question": "Q?", "answer": "A."}],
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fmt(x: float | None, unit: str = "s") -> str:
    return "n/a" if x is None else f"{x:.3f}{unit}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure KV-cache prefix reuse.")
    parser.add_argument("--model", help="Override MODEL_ID (e.g. qwen/qwen3.5-9b)")
    args = parser.parse_args()
    if args.model:
        config.MODEL_ID = args.model

    print(f"Model: {config.MODEL_ID}  @ {config.BASE_URL}\n")
    en14, en13 = load(CHAPTER_A), load(CHAPTER_C)

    print("Warmup (discarded)...")
    client.translate_element_stream(WARMUP_OBJ, TITLE, "Spanish")

    print("Request A  (title,   Spanish, isaiah_14) ......")
    a = client.translate_element_stream(en14, TITLE, "Spanish")
    show(a)
    print("Request B  (title,   French,  isaiah_14 - IDENTICAL prefix) ......")
    b = client.translate_element_stream(en14, TITLE, "French")
    show(b)
    print("Request C  (title,   German,  isaiah_13 - DIFFERENT prefix / control) ......")
    c = client.translate_element_stream(en13, TITLE, "German")
    show(c)
    print("Request G  (content, Spanish, isaiah_14 - measure generation rate) ......")
    g = client.translate_element_stream(en14, CONTENT, "Spanish")
    show(g)

    print_verdict(a, b, c)
    print_economics(a, g)

    print("\nIMPORTANT: confirm against the LM Studio server log whether the "
          "'forcing full prompt re-processing ...' line appeared during request B.\n"
          "  - absent  -> consistent with reuse WORKING\n"
          "  - present -> reuse is DEAD regardless of the TTFT numbers above")


def show(r: client.StreamResult) -> None:
    print(f"  TTFT={fmt(r.ttft)}  total={fmt(r.total_time)}  "
          f"prompt_tokens={r.prompt_tokens}  completion_tokens={r.completion_tokens}")


def print_verdict(a: client.StreamResult, b: client.StreamResult, c: client.StreamResult) -> None:
    print("\n" + "=" * 64)
    print("CACHE-REUSE VERDICT")
    print("=" * 64)
    print(f"  TTFT_A (cold) ............ {fmt(a.ttft)}  ({a.prompt_tokens} prompt tok)")
    print(f"  TTFT_B (warm if reuse) ... {fmt(b.ttft)}  ({b.prompt_tokens} prompt tok)")
    print(f"  TTFT_C (cold control) .... {fmt(c.ttft)}  ({c.prompt_tokens} prompt tok)")

    if not (a.ttft and b.ttft and c.ttft and a.prompt_tokens and b.prompt_tokens and c.prompt_tokens):
        print("\n  INCONCLUSIVE: a TTFT or token count was not captured.")
        return

    # Normalize by prompt tokens: a genuine prefill has a bounded tok/s rate, while a
    # cache hit "prefills" thousands of tokens in ~0s (an impossibly high rate). This is
    # robust to the control chapter being a different size than A.
    a_rate = a.prompt_tokens / a.ttft
    b_rate = b.prompt_tokens / b.ttft
    c_rate = c.prompt_tokens / c.ttft
    print(f"\n  effective prefill rate (prompt_tok / TTFT):")
    print(f"    A {a_rate:>8,.0f} tok/s   B {b_rate:>8,.0f} tok/s   C {c_rate:>8,.0f} tok/s")
    print(f"    B is {b_rate / a_rate:.1f}x A's rate (high => reuse);  "
          f"C is {c_rate / a_rate:.1f}x A's rate (~1x => cold control)")

    if b_rate >= 3 * a_rate and c_rate <= 2 * a_rate:
        verdict = "WORKS  (B reuses the cached prefix; C re-prefills cold like A)"
    elif b_rate < 1.5 * a_rate:
        verdict = "DEAD   (B ~= A -> no reuse; per-element re-prefills the context every call)"
    else:
        verdict = "INCONCLUSIVE (mixed signal -> rely on the server-log line below)"
    print(f"\n  >>> {verdict}")


def print_economics(a: client.StreamResult, g: client.StreamResult) -> None:
    print("\n" + "=" * 64)
    print("PROJECTED ECONOMICS  (per-element flow)")
    print("=" * 64)
    if not (a.ttft and a.prompt_tokens and g.ttft and g.completion_tokens and g.total_time > g.ttft):
        print("  Skipped: missing timing/usage from request A or G.")
        return

    prefill_rate = a.prompt_tokens / a.ttft                     # tok/s (context prefill)
    gen_rate = g.completion_tokens / (g.total_time - g.ttft)    # tok/s (body generation)
    langs = config.NUM_TIER1_LANGUAGES
    chapters = config.NUM_ENGLISH_CHAPTERS
    n_elem = len(config.ELEMENTS)

    prefill_once = a.ttft                       # time to prefill the chapter context once
    gen_per_lang = g.completion_tokens / gen_rate  # body dominates; SEO elements are tiny

    per_chapter_reuse = prefill_once + langs * gen_per_lang
    # Without reuse, every element call (n_elem of them) re-prefills the context.
    per_chapter_noreuse = langs * n_elem * prefill_once + langs * gen_per_lang

    run_reuse_h = per_chapter_reuse * chapters / 3600
    run_noreuse_h = per_chapter_noreuse * chapters / 3600

    print(f"  Measured (isaiah_14, a large chapter):")
    print(f"    context prefill = {a.prompt_tokens} tok in {a.ttft:.1f}s  (~{prefill_rate:,.0f} tok/s)")
    print(f"    body generation = {g.completion_tokens} tok  (~{gen_rate:,.0f} tok/s)")
    print(f"  Scope: {chapters} chapters x {langs} languages x {n_elem} elements\n")
    print(f"  Per chapter (60 langs):  with reuse {per_chapter_reuse/60:.1f} min   |   "
          f"without {per_chapter_noreuse/60:.1f} min")
    print(f"  FULL RUN:                with reuse {run_reuse_h:,.1f} h     |   "
          f"without {run_noreuse_h:,.1f} h")
    if run_reuse_h:
        print(f"  Delta: reuse saves {run_noreuse_h - run_reuse_h:,.1f} h "
              f"({run_noreuse_h / run_reuse_h:.1f}x faster)")
    print("  Note: isaiah_14 is ~3x the average chapter (40K vs 14.5K chars), so the "
          "full-run hours above are a conservative over-estimate.")


if __name__ == "__main__":
    main()
