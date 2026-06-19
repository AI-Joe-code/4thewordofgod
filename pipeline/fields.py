"""The field contract: what gets translated vs. preserved, and how output is rebuilt.

This module is the reusable core of the pipeline. Both tests (and the eventual
full run) depend on it.

``extract_translatables`` pulls ONLY the human-readable values into a compact dict
that is the entire payload we send the model. ``reinsert`` clones the English
object, overwrites just those fields with the model's translations, syncs the
duplicated SEO/schema mirrors from the canonical fields (free — no extra LLM
call), and leaves every structural/identifier field byte-identical.

See translation_test_brief.md (Field contract) for the authoritative spec.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import config

# Strip a leaked FAQ label that some Qwen languages echo from the prompt's FAQ
# rendering: optional "1." / "1)" enumeration then an optional Q:/A: label
# (ASCII or fullwidth colon). Conservative — only fires on an actual colon label.
_FAQ_LABEL_RE = re.compile(r"^\s*(?:\d+\s*[.)]\s*)?(?:[QAＱＡ]\s*[:：]\s*)?")


def _strip_faq_label(text: str) -> str:
    return _FAQ_LABEL_RE.sub("", text, count=1) if isinstance(text, str) else text

# Top-level keys we translate. (content includes the HTML body, scripture and all,
# per the project decision to translate everything now.)
TRANSLATABLE_TOP_LEVEL = ("title", "content", "metaDescription")


def render_context(en_obj: dict[str, Any]) -> str:
    """Render the English chapter as the labeled context block (the shared prefix).

    This is byte-identical for a given chapter across every element and language,
    so it's the slab that KV-cache prefix reuse should keep warm. Static fields are
    deliberately excluded — they never need to reach the model.
    """
    keywords = ", ".join(en_obj.get("keywords", []) or [])
    faq_lines: list[str] = []
    for i, item in enumerate(en_obj.get("faq", []) or [], start=1):
        faq_lines.append(f"{i}. Q: {item.get('question', '')}")
        faq_lines.append(f"   A: {item.get('answer', '')}")
    faq_block = "\n".join(faq_lines) if faq_lines else "(none)"

    return (
        f"{config.CONTEXT_BEGIN}\n"
        f"TITLE: {en_obj.get('title', '')}\n"
        f"META_DESCRIPTION: {en_obj.get('metaDescription', '')}\n"
        f"KEYWORDS: {keywords}\n"
        f"FAQ:\n{faq_block}\n"
        f"BODY_HTML:\n{en_obj.get('content', '')}\n"
        f"{config.CONTEXT_END}"
    )

# Structural / identifier fields that must come out byte-identical to English.
PRESERVED_TOP_LEVEL = (
    "book_name",
    "chapter_number",
    "previous_chapter",
    "next_chapter",
)


def extract_translatables(en_obj: dict[str, Any]) -> dict[str, Any]:
    """Return a compact dict of just the human-readable values to translate.

    The shape is intentionally simple and stable so the model can return the same
    keys back. This dict (serialized) IS the document payload — it must be
    identical across every target language for a given chapter, which it naturally
    is because it derives only from the English source.
    """
    payload: dict[str, Any] = {
        "title": en_obj.get("title", ""),
        "content": en_obj.get("content", ""),
        "metaDescription": en_obj.get("metaDescription", ""),
        "keywords": list(en_obj.get("keywords", []) or []),
        "faq": [
            {"question": item.get("question", ""), "answer": item.get("answer", "")}
            for item in (en_obj.get("faq", []) or [])
        ],
    }
    return payload


def _coerce_keywords(value: Any, fallback: list[str]) -> list[str]:
    """Normalize the model's keywords back into a list of strings."""
    if isinstance(value, list):
        return [str(k) for k in value]
    if isinstance(value, str):
        # Model occasionally returns a comma-joined string; split it back.
        return [part.strip() for part in value.split(",") if part.strip()]
    return list(fallback)


def reinsert(en_obj: dict[str, Any], translated: dict[str, Any]) -> dict[str, Any]:
    """Clone English, overwrite translated fields, sync mirrors, preserve the rest."""
    out = copy.deepcopy(en_obj)

    # 1) Canonical translated fields (fall back to English if the model omitted one).
    out["title"] = translated.get("title", out.get("title", ""))
    out["content"] = translated.get("content", out.get("content", ""))
    out["metaDescription"] = translated.get(
        "metaDescription", out.get("metaDescription", "")
    )
    out["keywords"] = _coerce_keywords(
        translated.get("keywords"), out.get("keywords", []) or []
    )

    src_faq = en_obj.get("faq", []) or []
    new_faq = translated.get("faq") or []
    out_faq = []
    for i, en_item in enumerate(src_faq):
        t_item = new_faq[i] if i < len(new_faq) and isinstance(new_faq[i], dict) else {}
        out_faq.append(
            {
                "question": _strip_faq_label(t_item.get("question", en_item.get("question", ""))),
                "answer": _strip_faq_label(t_item.get("answer", en_item.get("answer", ""))),
            }
        )
    out["faq"] = out_faq

    # 2) Sync the duplicated mirrors from the canonical translated fields.
    _sync_structured_data(out)
    if "og:title" in out:
        out["og:title"] = out["title"]
    if "og:description" in out:
        out["og:description"] = out["metaDescription"]

    return out


def _sync_structured_data(out: dict[str, Any]) -> None:
    """Propagate translated title/description/keywords/faq into structuredData.

    Article.headline/description/keywords and FAQPage.mainEntity are exact copies
    of fields we already translated, so we mirror them here instead of paying for
    a second translation. BreadcrumbList, @context/@type, author, and Article.about
    are left untouched (preserved byte-identical).
    """
    blocks = out.get("structuredData")
    if blocks is None:
        return
    if not isinstance(blocks, list):
        blocks = [blocks]
        out["structuredData"] = blocks

    keywords_str = ", ".join(out.get("keywords", []))

    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("@type")

        if btype == "Article":
            if "headline" in block:
                block["headline"] = out["title"]
            if "description" in block:
                block["description"] = out["metaDescription"]
            if "keywords" in block:
                block["keywords"] = keywords_str

        elif btype == "FAQPage":
            main = block.get("mainEntity")
            if isinstance(main, list):
                for i, entity in enumerate(main):
                    if not isinstance(entity, dict) or i >= len(out["faq"]):
                        continue
                    entity["name"] = out["faq"][i]["question"]
                    answer = entity.get("acceptedAnswer")
                    if isinstance(answer, dict):
                        answer["text"] = out["faq"][i]["answer"]
