"""Two-engine chapter translation: NLLB body + (Qwen | NLLB) SEO.

Routing:
- BODY (HTML): always NLLB via segment-reinsert (fast, tag-safe).
- SEO (title/metaDescription/keywords/faq):
    Tier-1 -> Qwen (contextual localization, higher quality on high-resource langs)
    Tier-2 -> NLLB (the long tail Qwen can't do reliably)

Both pipelines share the body path, the field-contract assembly (fields.reinsert),
and validation. In production the engines run in separate phases on the one GPU
(load Qwen, do all SEO; unload; load NLLB, do all bodies + Tier-2 SEO). For testing
NLLB runs on CPU so it can coexist with Qwen on the GPU.
"""

from __future__ import annotations

from typing import Any

import client
import config
import fields
import html_segments
from nllb_engine import NLLBEngine


def translate_body(en_obj: dict[str, Any], code: str, nllb: NLLBEngine) -> str:
    """Translate the HTML body via NLLB; tags/href preserved by reassembly.

    Uses sentence-aware translation so multi-sentence segments don't lose sentences.
    """
    seg = html_segments.segment(en_obj.get("content", ""))
    translated_cores = nllb.translate_texts(seg.cores, code)
    return html_segments.reassemble(seg, translated_cores)


def translate_seo_nllb(en_obj: dict[str, Any], code: str, nllb: NLLBEngine) -> dict[str, Any]:
    """Translate the SEO fields via NLLB (Tier-2). One batched call for efficiency."""
    title = en_obj.get("title", "")
    meta = en_obj.get("metaDescription", "")
    keywords = list(en_obj.get("keywords", []) or [])
    faq = en_obj.get("faq", []) or []

    faq_texts: list[str] = []
    for item in faq:
        faq_texts.append(item.get("question", ""))
        faq_texts.append(item.get("answer", ""))

    flat = [title, meta, *keywords, *faq_texts]
    out = nllb.translate_texts(flat, code)  # sentence-aware (faq answers can be multi-sentence)

    i = 0
    t_title, t_meta = out[i], out[i + 1]
    i += 2
    t_keywords = out[i : i + len(keywords)]
    i += len(keywords)
    t_faq_texts = out[i : i + len(faq_texts)]
    t_faq = [
        {"question": t_faq_texts[j], "answer": t_faq_texts[j + 1]}
        for j in range(0, len(t_faq_texts) - 1, 2)
    ]
    return {"title": t_title, "metaDescription": t_meta, "keywords": t_keywords, "faq": t_faq}


def translate_chapter(en_obj: dict[str, Any], code: str, nllb: NLLBEngine, *, verbose: bool = True) -> dict[str, Any]:
    """Translate one chapter into one language, routed by tier; return assembled JSON."""
    body = translate_body(en_obj, code, nllb)

    if config.seo_engine(code) == "qwen":
        seo, _ = client.translate_seo(en_obj, config.language_name(code), verbose=verbose)
    else:
        seo = translate_seo_nllb(en_obj, code, nllb)

    payload = {"content": body, **seo}
    return fields.reinsert(en_obj, payload)
