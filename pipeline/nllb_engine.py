"""NLLB-200 translation engine for the HTML body (runs outside LM Studio).

NLLB is purpose-built NMT: it translates a *batch* of plain-text segments in one
GPU forward pass, which is the real throughput lever the LM Studio path lacks.
It only ever sees text (from html_segments), so HTML integrity is preserved by the
caller's reassembly.

Model/device are configurable:
- TEST (this machine, GPU saturated by Qwen): distilled-600M on CPU — fast enough to
  validate mechanics + integrity without touching VRAM.
- PRODUCTION: nllb-200-3.3B on the GPU, run in a phase AFTER Qwen is unloaded
  (single 12 GB GPU can't host both at once).

Target languages use FLORES-200 codes verbatim (the same codes in translation_targets.md).
"""

from __future__ import annotations

import os
import re

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

DEFAULT_MODEL = os.environ.get("NLLB_MODEL", "facebook/nllb-200-distilled-600M")
DEFAULT_DEVICE = os.environ.get("NLLB_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
SRC_LANG = "eng_Latn"

# Split English text into sentences. NLLB-200 is a SENTENCE-level model: given a
# multi-sentence segment it sometimes translates only part (drops sentences), so we
# feed it one sentence at a time. Split on .!? followed by space + an opening
# quote/paren and a capital/digit; merge back single-letter initials (e.g. "P.").
_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+(?=["“(\[]?[A-Z0-9])')
_TRAILING_INITIAL = re.compile(r'(?:^|\s)[A-Z]\.$')


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = _SENT_SPLIT.split(text)
    merged: list[str] = []
    for part in parts:
        if merged and _TRAILING_INITIAL.search(merged[-1]):
            merged[-1] = f"{merged[-1]} {part}"  # e.g. "Lewis P." + "Hussell ..."
        else:
            merged.append(part)
    return merged


class NLLBEngine:
    def __init__(self, model_id: str = DEFAULT_MODEL, device: str = DEFAULT_DEVICE) -> None:
        self.model_id = model_id
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, src_lang=SRC_LANG)

        # On GPU, load in fp16. NLLB-3.3B in fp32 is ~13 GB and overflows a 12 GB card
        # into shared system memory (catastrophically slow). fp16 (~6.6 GB) fits with
        # headroom. We pass torch_dtype AND force .half() so it can't silently stay fp32
        # if the dtype kwarg name differs across transformers versions.
        use_fp16 = device != "cpu"
        model = None
        if use_fp16:
            # transformers 5.x renamed torch_dtype -> dtype; try the new name first.
            for kw in ("dtype", "torch_dtype"):
                try:
                    model = AutoModelForSeq2SeqLM.from_pretrained(model_id, **{kw: torch.float16})
                    break
                except TypeError:
                    model = None
        if model is None:
            model = AutoModelForSeq2SeqLM.from_pretrained(model_id)
        if use_fp16:
            model = model.half()  # enforce fp16 regardless of which kwarg landed
        self.model = model.to(device)
        self.model.eval()

    def _tgt_bos(self, tgt_lang: str) -> int:
        # The forced first decoder token selects the output language.
        tid = self.tokenizer.convert_tokens_to_ids(tgt_lang)
        if tid is None or tid == self.tokenizer.unk_token_id:
            raise ValueError(f"NLLB tokenizer doesn't know target language code {tgt_lang!r}")
        return tid

    @torch.inference_mode()
    def translate_batch(
        self,
        texts: list[str],
        tgt_lang: str,
        *,
        batch_size: int = 16,
        max_length: int = 512,
    ) -> list[str]:
        """Translate text segments eng_Latn -> tgt_lang, preserving order."""
        if not texts:
            return []
        bos = self._tgt_bos(tgt_lang)
        out: list[str] = []
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            enc = self.tokenizer(
                chunk, return_tensors="pt", padding=True, truncation=True, max_length=max_length
            ).to(self.device)
            gen = self.model.generate(
                **enc, forced_bos_token_id=bos, max_length=max_length, num_beams=1
            )
            out.extend(self.tokenizer.batch_decode(gen, skip_special_tokens=True))
        return out

    def translate_texts(self, texts: list[str], tgt_lang: str, **batch_kwargs) -> list[str]:
        """Sentence-aware translation: split each text into sentences, translate each,
        rejoin — one output per input, in order. Prevents NLLB dropping sentences in
        multi-sentence segments. Empty/whitespace inputs pass through as "".
        """
        spans: list[tuple[int, int]] = []
        flat: list[str] = []
        for t in texts:
            sentences = split_sentences(t)
            spans.append((len(flat), len(sentences)))
            flat.extend(sentences)

        translated = self.translate_batch(flat, tgt_lang, **batch_kwargs) if flat else []

        out: list[str] = []
        for start, count in spans:
            out.append(" ".join(translated[start : start + count]) if count else "")
        return out
