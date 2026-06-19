"""Shared configuration for the translation pipeline.

Architecture: each chapter is translated **one element at a time** against a single
shared prefix = the full English chapter rendered as context. Per element we send a
small task whose last line is the target language. This (a) reduces context rot —
each output is small and focused, and (b) is the shared-prefix / varying-suffix
pattern that LM Studio KV-cache prefix reuse rewards. Static/structural fields are
never sent to the model; Python carries them over verbatim (see fields.py).

The prompt scaffolding lives here so every request is built from one source and the
shared prefix stays byte-identical across elements and languages.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(
            f"Missing required env var {name!r}. "
            f"Copy pipeline/.env.example to pipeline/.env and fill it in "
            f"(looked in {_ENV_PATH})."
        )
    return value


BASE_URL = _require("LMSTUDIO_BASE_URL")
API_KEY = _require("LMSTUDIO_API_KEY")
# Default model; CLI --model overrides this at runtime (client reads config.MODEL_ID
# at call time, so scripts can reassign it before issuing requests).
MODEL_ID = _require("MODEL_ID")

# --- Sampling / runtime params -------------------------------------------------
TEMPERATURE = 0.2
# Big enough for a full-length body in a verbose target script. With a ~15K-token
# context, 24K output still fits a 64K window with margin.
MAX_TOKENS = 24000
REQUEST_TIMEOUT = 1800

# --- Prompt scaffolding --------------------------------------------------------
# system + the rendered English context (fields.render_context) form the fixed
# prefix P. The per-element TASK and the trailing language word are the only things
# that vary; the language word is always the LAST content in the message.
SYSTEM_PROMPT = (
    "You are an expert translator and SEO localizer for Bible commentary. You are "
    "given one English chapter as context, then asked to produce exactly ONE field "
    "at a time, rendered into the target language named on the final line. Stay "
    "faithful to the chapter's meaning and make the result natural in the target "
    "language. Preserve every HTML tag, attribute, and href/URL exactly; never "
    "translate or alter URLs, code, or identifiers. Output ONLY the requested "
    "field's value — no labels, no surrounding quotes, no commentary, no markdown "
    "fences."
)

CONTEXT_BEGIN = "<<<ENGLISH CHAPTER (context only — do not output this block)>>>"
CONTEXT_END = "<<<END ENGLISH CHAPTER>>>"
TARGET_LANGUAGE_LABEL = "Target language:"

# Markers that must never appear in model output (leak detection in validate.py).
SENTINELS = (CONTEXT_BEGIN, CONTEXT_END, TARGET_LANGUAGE_LABEL)


@dataclass(frozen=True)
class Element:
    key: str          # field name in the chapter payload
    kind: str         # "text" | "string_array" | "faq_array"
    task: str         # instruction appended after the context (language added last)


# Order matters only for cache warmth: translate the big body first so its (cold)
# context prefill is reused by the cheap SEO elements that follow.
ELEMENTS: tuple[Element, ...] = (
    Element(
        "content", "text",
        "Translate the BODY_HTML shown above, in full, into the target language. "
        "Preserve every HTML tag, attribute, and href exactly as written; translate "
        "only the human-readable text between tags (including the scripture quoted "
        "in blockquotes). Output only the translated HTML.",
    ),
    Element(
        "title", "text",
        "Render the TITLE shown above into the target language: a faithful, natural, "
        "SEO-strong chapter title grounded in this chapter. Output only the title.",
    ),
    Element(
        "metaDescription", "text",
        "Render the META_DESCRIPTION shown above into the target language as a "
        "compelling, accurate SEO meta description of roughly the same length. "
        "Output only the description.",
    ),
    Element(
        "keywords", "string_array",
        "Localize the KEYWORDS shown above into the target language: natural search "
        "phrases for this chapter, not literal word-for-word translations. Return a "
        "JSON array of keyword strings.",
    ),
    Element(
        "faq", "faq_array",
        "Render each FAQ question and answer shown above into the target language, "
        "faithful to this chapter. Output only the translated question and answer "
        "text — do NOT include the list numbering or any 'Q:'/'A:' labels. Return a "
        'JSON array of objects, each with "question" and "answer".',
    ),
)

ELEMENT_BY_KEY: dict[str, Element] = {e.key: e for e in ELEMENTS}

# SEO elements = everything except the body. Tier-1 sends these to Qwen (contextual
# localization); Tier-2 sends them to NLLB along with the body.
SEO_ELEMENTS: tuple[Element, ...] = tuple(e for e in ELEMENTS if e.key != "content")


def _array_schema(name: str, item_schema: dict) -> dict:
    # LM Studio structured output requires an object root, so array results are
    # wrapped in {"value": [...]}. client.py unwraps it (and tolerates a bare array
    # under the text fallback).
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"value": {"type": "array", "items": item_schema}},
                "required": ["value"],
                "additionalProperties": False,
            },
        },
    }


TEXT_FORMAT = {"type": "text"}
RESPONSE_FORMATS: dict[str, dict] = {
    "text": TEXT_FORMAT,
    "string_array": _array_schema("keywords", {"type": "string"}),
    "faq_array": _array_schema(
        "faq",
        {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "answer": {"type": "string"},
            },
            "required": ["question", "answer"],
            "additionalProperties": False,
        },
    ),
}

# --- Language map (Tier 1 — Qwen LLM, from translation_targets.md) --------------
LANG_NAMES: dict[str, str] = {
    "zho_Hans": "Chinese (Simplified)",
    "zho_Hant": "Chinese (Traditional)",
    "yue_Hant": "Yue Chinese (Cantonese)",
    "kor_Hang": "Korean",
    "jpn_Jpan": "Japanese",
    "vie_Latn": "Vietnamese",
    "tha_Thai": "Thai",
    "zsm_Latn": "Standard Malay",
    "ind_Latn": "Indonesian",
    "jav_Latn": "Javanese",
    "ceb_Latn": "Cebuano",
    "tgl_Latn": "Tagalog",
    "deu_Latn": "German",
    "ita_Latn": "Italian",
    "fra_Latn": "French",
    "spa_Latn": "Spanish",
    "por_Latn": "Portuguese",
    "nld_Latn": "Dutch",
    "cat_Latn": "Catalan",
    "glg_Latn": "Galician",
    "ast_Latn": "Asturian",
    "swe_Latn": "Swedish",
    "dan_Latn": "Danish",
    "nob_Latn": "Norwegian Bokmal",
    "fin_Latn": "Finnish",
    "isl_Latn": "Icelandic",
    "afr_Latn": "Afrikaans",
    "rus_Cyrl": "Russian",
    "ukr_Cyrl": "Ukrainian",
    "bel_Cyrl": "Belarusian",
    "pol_Latn": "Polish",
    "ces_Latn": "Czech",
    "slk_Latn": "Slovak",
    "slv_Latn": "Slovenian",
    "hrv_Latn": "Croatian",
    "bos_Latn": "Bosnian",
    "mkd_Cyrl": "Macedonian",
    "bul_Cyrl": "Bulgarian",
    "ron_Latn": "Romanian",
    "hun_Latn": "Hungarian",
    "ell_Grek": "Greek",
    "lvs_Latn": "Standard Latvian",
    "est_Latn": "Estonian",
    "tur_Latn": "Turkish",
    "azj_Latn": "North Azerbaijani",
    "kaz_Cyrl": "Kazakh",
    "kir_Cyrl": "Kyrgyz",
    "arb_Arab": "Modern Standard Arabic",
    "heb_Hebr": "Hebrew",
    "pes_Arab": "Western Persian (Farsi)",
    "hin_Deva": "Hindi",
    "urd_Arab": "Urdu",
    "ben_Beng": "Bengali",
    "tam_Taml": "Tamil",
    "mar_Deva": "Marathi",
    "guj_Gujr": "Gujarati",
    "kan_Knda": "Kannada",
    "mal_Mlym": "Malayalam",
    "pan_Guru": "Eastern Panjabi",
    "swh_Latn": "Swahili",
}

# --- Tier 2 — NLLB-200 (143 languages, from translation_targets.md) ------------
# NLLB takes each FLORES code verbatim as tgt_lang. Names are for logging only.
TIER2_NAMES: dict[str, str] = {
    "ace_Arab": "Acehnese (Arabic script)",
    "ace_Latn": "Acehnese (Latin script)",
    "acm_Arab": "Mesopotamian Arabic",
    "acq_Arab": "Ta'izzi-Adeni Arabic",
    "aeb_Arab": "Tunisian Arabic",
    "ajp_Arab": "South Levantine Arabic",
    "aka_Latn": "Akan",
    "amh_Ethi": "Amharic",
    "apc_Arab": "North Levantine Arabic",
    "arb_Latn": "Modern Standard Arabic (Romanized)",
    "ars_Arab": "Najdi Arabic",
    "ary_Arab": "Moroccan Arabic",
    "arz_Arab": "Egyptian Arabic",
    "asm_Beng": "Assamese",
    "awa_Deva": "Awadhi",
    "ayr_Latn": "Central Aymara",
    "azb_Arab": "South Azerbaijani",
    "bak_Cyrl": "Bashkir",
    "bam_Latn": "Bambara",
    "ban_Latn": "Balinese",
    "bem_Latn": "Bemba",
    "bho_Deva": "Bhojpuri",
    "bjn_Arab": "Banjar (Arabic script)",
    "bjn_Latn": "Banjar (Latin script)",
    "bod_Tibt": "Standard Tibetan",
    "bug_Latn": "Buginese",
    "cjk_Latn": "Chokwe",
    "ckb_Arab": "Central Kurdish",
    "crh_Latn": "Crimean Tatar",
    "cym_Latn": "Welsh",
    "dik_Latn": "Southwestern Dinka",
    "dyu_Latn": "Dyula",
    "dzo_Tibt": "Dzongkha",
    "epo_Latn": "Esperanto",
    "eus_Latn": "Basque",
    "ewe_Latn": "Ewe",
    "fao_Latn": "Faroese",
    "fij_Latn": "Fijian",
    "fon_Latn": "Fon",
    "fur_Latn": "Friulian",
    "fuv_Latn": "Nigerian Fulfulde",
    "gla_Latn": "Scottish Gaelic",
    "gle_Latn": "Irish",
    "grn_Latn": "Guarani",
    "hat_Latn": "Haitian Creole",
    "hau_Latn": "Hausa",
    "hne_Deva": "Chhattisgarhi",
    "hye_Armn": "Armenian",
    "ibo_Latn": "Igbo",
    "ilo_Latn": "Ilocano",
    "kab_Latn": "Kabyle",
    "kac_Latn": "Jingpho",
    "kam_Latn": "Kamba",
    "kas_Arab": "Kashmiri (Arabic script)",
    "kas_Deva": "Kashmiri (Devanagari script)",
    "kat_Geor": "Georgian",
    "knc_Arab": "Central Kanuri (Arabic script)",
    "knc_Latn": "Central Kanuri (Latin script)",
    "kbp_Latn": "Kabiye",
    "kea_Latn": "Kabuverdianu",
    "khm_Khmr": "Khmer",
    "kik_Latn": "Kikuyu",
    "kin_Latn": "Kinyarwanda",
    "kmb_Latn": "Kimbundu",
    "kmr_Latn": "Northern Kurdish",
    "kon_Latn": "Kikongo",
    "lao_Laoo": "Lao",
    "lij_Latn": "Ligurian",
    "lim_Latn": "Limburgish",
    "lin_Latn": "Lingala",
    "lit_Latn": "Lithuanian",
    "lmo_Latn": "Lombard",
    "ltg_Latn": "Latgalian",
    "ltz_Latn": "Luxembourgish",
    "lua_Latn": "Luba-Kasai",
    "lug_Latn": "Ganda",
    "luo_Latn": "Luo",
    "lus_Latn": "Mizo",
    "mag_Deva": "Magahi",
    "mai_Deva": "Maithili",
    "min_Arab": "Minangkabau (Arabic script)",
    "min_Latn": "Minangkabau (Latin script)",
    "plt_Latn": "Plateau Malagasy",
    "mlt_Latn": "Maltese",
    "mni_Beng": "Meitei (Bengali script)",
    "khk_Cyrl": "Halh Mongolian",
    "mos_Latn": "Mossi",
    "mri_Latn": "Maori",
    "mya_Mymr": "Burmese",
    "nno_Latn": "Norwegian Nynorsk",
    "npi_Deva": "Nepali",
    "nso_Latn": "Northern Sotho",
    "nus_Latn": "Nuer",
    "nya_Latn": "Nyanja",
    "oci_Latn": "Occitan",
    "gaz_Latn": "West Central Oromo",
    "ory_Orya": "Odia",
    "pag_Latn": "Pangasinan",
    "pap_Latn": "Papiamento",
    "prs_Arab": "Dari",
    "pbt_Arab": "Southern Pashto",
    "quy_Latn": "Ayacucho Quechua",
    "run_Latn": "Rundi",
    "sag_Latn": "Sango",
    "san_Deva": "Sanskrit",
    "sat_Olck": "Santali",
    "scn_Latn": "Sicilian",
    "shn_Mymr": "Shan",
    "sin_Sinh": "Sinhala",
    "smo_Latn": "Samoan",
    "sna_Latn": "Shona",
    "snd_Arab": "Sindhi",
    "som_Latn": "Somali",
    "sot_Latn": "Southern Sotho",
    "als_Latn": "Tosk Albanian",
    "srd_Latn": "Sardinian",
    "srp_Cyrl": "Serbian",
    "ssw_Latn": "Swati",
    "sun_Latn": "Sundanese",
    "szl_Latn": "Silesian",
    "tat_Cyrl": "Tatar",
    "tel_Telu": "Telugu",
    "tgk_Cyrl": "Tajik",
    "tir_Ethi": "Tigrinya",
    "taq_Latn": "Tamasheq (Latin script)",
    "taq_Tfng": "Tamasheq (Tifinagh script)",
    "tpi_Latn": "Tok Pisin",
    "tsn_Latn": "Tswana",
    "tso_Latn": "Tsonga",
    "tuk_Latn": "Turkmen",
    "tum_Latn": "Tumbuka",
    "twi_Latn": "Twi",
    "tzm_Tfng": "Central Atlas Tamazight",
    "uig_Arab": "Uyghur",
    "umb_Latn": "Umbundu",
    "uzn_Latn": "Northern Uzbek",
    "vec_Latn": "Venetian",
    "war_Latn": "Waray",
    "wol_Latn": "Wolof",
    "xho_Latn": "Xhosa",
    "ydd_Hebr": "Eastern Yiddish",
    "yor_Latn": "Yoruba",
    "zul_Latn": "Zulu",
}

ALL_NAMES: dict[str, str] = {**LANG_NAMES, **TIER2_NAMES}

NUM_TIER1_LANGUAGES = len(LANG_NAMES)
NUM_TIER2_LANGUAGES = len(TIER2_NAMES)
NUM_ENGLISH_CHAPTERS = 154


def is_tier1(flores_code: str) -> bool:
    """Tier-1 = a Qwen-capable language (body still always NLLB)."""
    return flores_code in LANG_NAMES


# Tier-1 languages whose Qwen SEO showed real errors (Israel→Iran, serpent→lion,
# English/Latin leaks, etc. on the 9B) — route their SEO through NLLB instead.
# Expand as you spot-check more languages.
SEO_VIA_NLLB: set[str] = {
    "pes_Arab",  # Persian  — "Israel"→"Iran"
    "heb_Hebr",  # Hebrew   — answer trailed into English; bad Lucifer translit
    "arb_Arab",  # Arabic   — "serpent"→"lion"; name errors; Latin leak
    "tam_Taml",  # Tamil    — "fiery"→"fish"; "Babylon"→"Bali"
    "ell_Grek",  # Greek    — invented words
}


def seo_engine(flores_code: str) -> str:
    """Which engine produces this language's SEO: 'qwen' for verified Tier-1, else 'nllb'."""
    if is_tier1(flores_code) and flores_code not in SEO_VIA_NLLB:
        return "qwen"
    return "nllb"


def display_name(flores_code: str) -> str:
    """Human name for any supported code (Tier-1 or Tier-2); errors if unknown."""
    if flores_code in ALL_NAMES:
        return ALL_NAMES[flores_code]
    raise SystemExit(
        f"Unknown FLORES code {flores_code!r}. Not in the Tier-1 ({NUM_TIER1_LANGUAGES}) "
        f"or Tier-2 ({NUM_TIER2_LANGUAGES}) registries."
    )


def language_name(flores_code: str) -> str:
    """Tier-1 English name for the Qwen prompt; errors on non-Tier-1 codes."""
    try:
        return LANG_NAMES[flores_code]
    except KeyError:
        raise SystemExit(
            f"{flores_code!r} is not a Tier-1 (Qwen) language. Tier-1 codes: "
            f"{', '.join(sorted(LANG_NAMES))}"
        )


# --- FLORES -> BCP-47 output codes ---------------------------------------------
# Short BCP-47 codes used for R2 keys / site URLs (matches the existing `en`).
# ISO 639-1 where it exists, else 639-3; script subtag only where the same language
# appears in >1 script (so URLs stay distinct). REVIEW: a handful of long-tail codes
# may want adjusting; the startup collision check guards against duplicates.
FLORES_TO_BCP47: dict[str, str] = {
    # Tier 1
    "zho_Hans": "zh-Hans", "zho_Hant": "zh-Hant", "yue_Hant": "yue", "kor_Hang": "ko",
    "jpn_Jpan": "ja", "vie_Latn": "vi", "tha_Thai": "th", "zsm_Latn": "ms", "ind_Latn": "id",
    "jav_Latn": "jv", "ceb_Latn": "ceb", "tgl_Latn": "tl", "deu_Latn": "de", "ita_Latn": "it",
    "fra_Latn": "fr", "spa_Latn": "es", "por_Latn": "pt", "nld_Latn": "nl", "cat_Latn": "ca",
    "glg_Latn": "gl", "ast_Latn": "ast", "swe_Latn": "sv", "dan_Latn": "da", "nob_Latn": "nb",
    "fin_Latn": "fi", "isl_Latn": "is", "afr_Latn": "af", "rus_Cyrl": "ru", "ukr_Cyrl": "uk",
    "bel_Cyrl": "be", "pol_Latn": "pl", "ces_Latn": "cs", "slk_Latn": "sk", "slv_Latn": "sl",
    "hrv_Latn": "hr", "bos_Latn": "bs", "mkd_Cyrl": "mk", "bul_Cyrl": "bg", "ron_Latn": "ro",
    "hun_Latn": "hu", "ell_Grek": "el", "lvs_Latn": "lv", "est_Latn": "et", "tur_Latn": "tr",
    "azj_Latn": "az", "kaz_Cyrl": "kk", "kir_Cyrl": "ky", "arb_Arab": "ar", "heb_Hebr": "he",
    "pes_Arab": "fa", "hin_Deva": "hi", "urd_Arab": "ur", "ben_Beng": "bn", "tam_Taml": "ta",
    "mar_Deva": "mr", "guj_Gujr": "gu", "kan_Knda": "kn", "mal_Mlym": "ml", "pan_Guru": "pa",
    "swh_Latn": "sw",
    # Tier 2
    "ace_Arab": "ace-Arab", "ace_Latn": "ace-Latn", "acm_Arab": "acm", "acq_Arab": "acq",
    "aeb_Arab": "aeb", "ajp_Arab": "ajp", "aka_Latn": "ak", "amh_Ethi": "am", "apc_Arab": "apc",
    "arb_Latn": "ar-Latn", "ars_Arab": "ars", "ary_Arab": "ary", "arz_Arab": "arz",
    "asm_Beng": "as", "awa_Deva": "awa", "ayr_Latn": "ay", "azb_Arab": "azb", "bak_Cyrl": "ba",
    "bam_Latn": "bm", "ban_Latn": "ban", "bem_Latn": "bem", "bho_Deva": "bho",
    "bjn_Arab": "bjn-Arab", "bjn_Latn": "bjn-Latn", "bod_Tibt": "bo", "bug_Latn": "bug",
    "cjk_Latn": "cjk", "ckb_Arab": "ckb", "crh_Latn": "crh", "cym_Latn": "cy", "dik_Latn": "dik",
    "dyu_Latn": "dyu", "dzo_Tibt": "dz", "epo_Latn": "eo", "eus_Latn": "eu", "ewe_Latn": "ee",
    "fao_Latn": "fo", "fij_Latn": "fj", "fon_Latn": "fon", "fur_Latn": "fur", "fuv_Latn": "fuv",
    "gla_Latn": "gd", "gle_Latn": "ga", "grn_Latn": "gn", "hat_Latn": "ht", "hau_Latn": "ha",
    "hne_Deva": "hne", "hye_Armn": "hy", "ibo_Latn": "ig", "ilo_Latn": "ilo", "kab_Latn": "kab",
    "kac_Latn": "kac", "kam_Latn": "kam", "kas_Arab": "ks-Arab", "kas_Deva": "ks-Deva",
    "kat_Geor": "ka", "knc_Arab": "knc-Arab", "knc_Latn": "knc-Latn", "kbp_Latn": "kbp",
    "kea_Latn": "kea", "khm_Khmr": "km", "kik_Latn": "ki", "kin_Latn": "rw", "kmb_Latn": "kmb",
    "kmr_Latn": "kmr", "kon_Latn": "kg", "lao_Laoo": "lo", "lij_Latn": "lij", "lim_Latn": "li",
    "lin_Latn": "ln", "lit_Latn": "lt", "lmo_Latn": "lmo", "ltg_Latn": "ltg", "ltz_Latn": "lb",
    "lua_Latn": "lua", "lug_Latn": "lg", "luo_Latn": "luo", "lus_Latn": "lus", "mag_Deva": "mag",
    "mai_Deva": "mai", "min_Arab": "min-Arab", "min_Latn": "min-Latn", "plt_Latn": "mg",
    "mlt_Latn": "mt", "mni_Beng": "mni", "khk_Cyrl": "mn", "mos_Latn": "mos", "mri_Latn": "mi",
    "mya_Mymr": "my", "nno_Latn": "nn", "npi_Deva": "ne", "nso_Latn": "nso", "nus_Latn": "nus",
    "nya_Latn": "ny", "oci_Latn": "oc", "gaz_Latn": "om", "ory_Orya": "or", "pag_Latn": "pag",
    "pap_Latn": "pap", "prs_Arab": "prs", "pbt_Arab": "ps", "quy_Latn": "quy", "run_Latn": "rn",
    "sag_Latn": "sg", "san_Deva": "sa", "sat_Olck": "sat", "scn_Latn": "scn", "shn_Mymr": "shn",
    "sin_Sinh": "si", "smo_Latn": "sm", "sna_Latn": "sn", "snd_Arab": "sd", "som_Latn": "so",
    "sot_Latn": "st", "als_Latn": "sq", "srd_Latn": "sc", "srp_Cyrl": "sr", "ssw_Latn": "ss",
    "sun_Latn": "su", "szl_Latn": "szl", "tat_Cyrl": "tt", "tel_Telu": "te", "tgk_Cyrl": "tg",
    "tir_Ethi": "ti", "taq_Latn": "taq-Latn", "taq_Tfng": "taq-Tfng", "tpi_Latn": "tpi",
    "tsn_Latn": "tn", "tso_Latn": "ts", "tuk_Latn": "tk", "tum_Latn": "tum", "twi_Latn": "tw",
    "tzm_Tfng": "tzm", "uig_Arab": "ug", "umb_Latn": "umb", "uzn_Latn": "uz", "vec_Latn": "vec",
    "war_Latn": "war", "wol_Latn": "wo", "xho_Latn": "xh", "ydd_Hebr": "yi", "yor_Latn": "yo",
    "zul_Latn": "zu",
}


def bcp47(flores_code: str) -> str:
    try:
        return FLORES_TO_BCP47[flores_code]
    except KeyError:
        raise SystemExit(f"No BCP-47 mapping for FLORES code {flores_code!r}.")


def bcp47_collisions() -> dict[str, list[str]]:
    """Return any BCP-47 code mapped from >1 FLORES code (should be empty)."""
    rev: dict[str, list[str]] = {}
    for flores, code in FLORES_TO_BCP47.items():
        rev.setdefault(code, []).append(flores)
    return {code: srcs for code, srcs in rev.items() if len(srcs) > 1}


def all_flores_codes() -> list[str]:
    """All 203 target FLORES codes (Tier-1 then Tier-2)."""
    return list(LANG_NAMES) + list(TIER2_NAMES)
