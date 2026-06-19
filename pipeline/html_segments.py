"""Tag-preserving text extraction for the HTML body.

The engine (NLLB or Qwen) corrupts markup when asked to re-emit HTML. The fix: the
engine never sees a tag. We tokenize the body into verbatim tag tokens and text
tokens, hand only the text to the engine, and splice translations back into the
*identical* tag skeleton. Tag/attribute/href integrity is then guaranteed by
construction — an identity translation reproduces the source byte-for-byte.

Granularity is per text node. For THIS corpus that's ideal for the bulk of the
content (commentary <p> and <blockquote class="primary-scripture"> have no inline
tags, so each is one clean unit). The known weak spot is <li> cross-references,
where KJV <em>-italicised words and <strong> reference labels fragment a sentence
into small pieces — flagged for refinement (block-level grouping) once we see real
NLLB output. Leading/trailing whitespace around each text node is preserved so
formatting and inter-tag spacing never shift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Matches any HTML tag verbatim (incl. attributes). The corpus has no '>' inside
# attribute values, so this simple form is safe here.
_TAG_RE = re.compile(r"<[^>]+>")
# Split a text node into (leading whitespace, core, trailing whitespace).
_WS_RE = re.compile(r"^(\s*)(.*?)(\s*)$", re.DOTALL)


@dataclass
class Segmented:
    tokens: list[tuple[str, str]]       # ("tag"|"text", verbatim)
    seg_indices: list[int]              # indices into tokens that are translatable
    cores: list[str]                    # the stripped text to translate (parallel to seg_indices)
    _affix: list[tuple[str, str]]       # (leading_ws, trailing_ws) per segment

    @property
    def texts(self) -> list[str]:
        return self.cores


def segment(html: str) -> Segmented:
    """Tokenize the body and collect the translatable text cores."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    for m in _TAG_RE.finditer(html):
        if m.start() > pos:
            tokens.append(("text", html[pos:m.start()]))
        tokens.append(("tag", m.group()))
        pos = m.end()
    if pos < len(html):
        tokens.append(("text", html[pos:]))

    seg_indices: list[int] = []
    cores: list[str] = []
    affix: list[tuple[str, str]] = []
    for i, (kind, value) in enumerate(tokens):
        if kind != "text":
            continue
        lead, core, trail = _WS_RE.match(value).groups()
        if core:  # skip whitespace-only nodes (kept verbatim on reassembly)
            seg_indices.append(i)
            cores.append(core)
            affix.append((lead, trail))

    return Segmented(tokens, seg_indices, cores, affix)


def reassemble(seg: Segmented, translated_cores: list[str]) -> str:
    """Splice translated cores back into the verbatim skeleton."""
    if len(translated_cores) != len(seg.seg_indices):
        raise ValueError(
            f"expected {len(seg.seg_indices)} translations, got {len(translated_cores)}"
        )
    out = [value for _, value in seg.tokens]
    for slot, (idx, (lead, trail)) in enumerate(zip(seg.seg_indices, seg._affix)):
        out[idx] = f"{lead}{translated_cores[slot]}{trail}"
    return "".join(out)
