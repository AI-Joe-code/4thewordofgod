# Translation pipeline — single-chapter test harness

Gated test harness for translating the English commentaries into the 60 Tier‑1
languages using the local **Qwen** model in **LM Studio**. See
`translation_test_brief.md` (repo root) for the full rationale.

This builds the smallest harness that answers two questions:

1. **Test A (priority):** does LM Studio's KV‑cache **prefix reuse** fire for a
   shared‑prefix / varying‑language request pattern? This decides whether
   translating ~154 chapters × 60 languages on the LLM is economically feasible.
2. **Test B:** does the extract → translate → reinsert → validate loop produce
   structurally intact, valid JSON?

It is **not** the full run (that's deferred — see the plan's "Deferred" section).

## Module layout

| File | Role |
|---|---|
| `config.py` | Env, prompt, FLORES→name map, **FLORES→BCP-47 map**, element specs |
| `fields.py` | Field contract: `reinsert` / `render_context` (translate vs preserve) |
| `client.py` | Qwen (LM Studio) per-element + `translate_seo` |
| `html_segments.py` | Tag-safe body tokenize/reassemble (engine never sees HTML) |
| `nllb_engine.py` | NLLB-200 batched + **sentence-aware** `translate_texts` (fp16 on GPU) |
| `coordinator.py` | Two-engine routing: NLLB body + Qwen/NLLB SEO by tier |
| `validate.py` | JSON / structural / HTML tag+href integrity checks |
| **`run_all.py`** | **Full-run orchestrator** (resumable, thermal-safe, phased) |
| `test_cache.py` / `test_mechanics.py` / `bench_nllb_gpu.py` / `probe_concurrency.py` | one-off tests/benchmarks |

## Architecture (two engines, phase-batched)

Body → **NLLB-200-3.3B** (tag-safe segment-reinsert, sentence-level). SEO (title/meta/
keywords/faq) → **Qwen** for Tier-1 (60 high-resource langs), **NLLB** for Tier-2 (143).
Single 12 GB GPU can't host both, so the full run is phase-batched. NLLB loads in **fp16**
(fp32 overflows VRAM).

## Setup

```sh
python -m venv pipeline/.venv
# Windows PowerShell:
pipeline\.venv\Scripts\Activate.ps1
python -m pip install -r pipeline/requirements.txt
```

Copy `pipeline/.env.example` to `pipeline/.env` and fill in the LM Studio
connection (already done locally; `.env` is gitignored).

## LM Studio app settings (confirm in the app, not via API)

- Model `qwen/qwen3.5-35b-a3b` loaded.
- Context length **≥ 32K**.
- **Thinking mode OFF** (the harness also sends `enable_thinking=false` and strips
  any `<think>` block, but confirm in the app).
- Model loading guardrails **Relaxed** (the model overflows 12 GB VRAM by design).

## Full run (production) — all 203 languages, resumable + thermal-safe

```sh
# 1) NLLB phase — all bodies + Tier-2 SEO. Unload Qwen in LM Studio first.
python pipeline/run_all.py --phase nllb        # ~115h; resumable; pauses if GPU hot
#    smoke test first:  --langs spa_Latn,cym_Latn --limit-chapters 2

# 2) Qwen phase — Tier-1 SEO. Load Qwen in LM Studio first.
python pipeline/run_all.py --phase qwen         # ~26h

# 3) Assemble (no GPU) — merge caches -> content-source/{bcp47}/{Book}/json/
python pipeline/run_all.py --phase assemble

# then publish per language, e.g.:
node scripts/upload_content.js --lang=es --type=json --dir=content-source/es/<Book>/json --remote
```

Resume: stop/restart any phase freely — cached units in `pipeline/work/` are skipped.
Thermal: `--max-temp 80 --resume-temp 65` (defaults); add `--break-every N --break-secs S`
for periodic pauses. Progress + ETA print live and persist to `pipeline/work/progress_*.json`.

## Test harness (single-chapter validation)

```sh
# Test A — cache reuse + economics projection
python pipeline/test_cache.py
#   While request B runs, watch the LM Studio SERVER LOG for
#   "forcing full prompt re-processing ..." — its presence means reuse is DEAD.

# Test B — mechanics; writes pipeline/output/spa_Latn/isaiah_14.json
python pipeline/test_mechanics.py
#   Other languages / chapters:
python pipeline/test_mechanics.py --lang fra_Latn
```

Test B exits non‑zero if any critical validation check fails.
