"""Validation for a translated chapter against its English source.

No third-party deps — HTML tag/href integrity uses the stdlib html.parser. Returns
a list of checks; ``ok`` on each, plus ``critical`` to distinguish hard failures
from informational warnings.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

import config
import fields


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    critical: bool = True


class _TagCollector(HTMLParser):
    """Collects a multiset of tag names and a multiset of href attribute values."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: Counter[str] = Counter()
        self.hrefs: Counter[str] = Counter()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags[tag] += 1
        for name, value in attrs:
            if name == "href" and value is not None:
                self.hrefs[value] += 1

    handle_startendtag = handle_starttag


def _profile(html: str) -> tuple[Counter[str], Counter[str]]:
    collector = _TagCollector()
    collector.feed(html or "")
    return collector.tags, collector.hrefs


def _gather_text(obj: dict[str, Any]) -> str:
    """All translatable text concatenated, for leak detection."""
    parts = [obj.get("title", ""), obj.get("content", ""), obj.get("metaDescription", "")]
    parts.extend(obj.get("keywords", []) or [])
    for item in obj.get("faq", []) or []:
        parts.append(item.get("question", ""))
        parts.append(item.get("answer", ""))
    return "\n".join(p for p in parts if isinstance(p, str))


def validate(en_obj: dict[str, Any], out_obj: dict[str, Any]) -> list[Check]:
    checks: list[Check] = []

    # 1) Same top-level keys (reinsert shouldn't add/drop any).
    en_keys, out_keys = set(en_obj), set(out_obj)
    checks.append(
        Check(
            "schema keys match",
            en_keys == out_keys,
            "identical key set" if en_keys == out_keys
            else f"missing={en_keys - out_keys} extra={out_keys - en_keys}",
        )
    )

    # 2) Structural / identifier fields byte-identical.
    mismatched = [k for k in fields.PRESERVED_TOP_LEVEL if en_obj.get(k) != out_obj.get(k)]
    checks.append(
        Check(
            "structural fields byte-identical",
            not mismatched,
            "all preserved" if not mismatched else f"changed: {mismatched}",
        )
    )

    # 3) HTML tag integrity.
    en_tags, en_hrefs = _profile(en_obj.get("content", ""))
    out_tags, out_hrefs = _profile(out_obj.get("content", ""))
    tags_ok = en_tags == out_tags
    detail = (
        f"{sum(en_tags.values())} tags preserved"
        if tags_ok
        else f"tag delta: { {t: out_tags[t] - en_tags[t] for t in (set(en_tags) | set(out_tags)) if out_tags[t] != en_tags[t]} }"
    )
    checks.append(Check("HTML tag set/count match", tags_ok, detail))

    # 4) href values unchanged.
    hrefs_ok = en_hrefs == out_hrefs
    checks.append(
        Check(
            "href values unchanged",
            hrefs_ok,
            f"{sum(en_hrefs.values())} hrefs preserved" if hrefs_ok
            else f"href delta: { {h: out_hrefs[h] - en_hrefs[h] for h in (set(en_hrefs) | set(out_hrefs)) if out_hrefs[h] != en_hrefs[h]} }",
        )
    )

    # 5) No sentinel markers leaked into translatable text.
    text = _gather_text(out_obj)
    leaked = [s for s in config.SENTINELS if s in text]
    checks.append(
        Check(
            "no sentinel leakage",
            not leaked,
            "clean" if not leaked else f"leaked: {leaked}",
        )
    )

    # 6) content length within a sane band of the source.
    en_len = len(en_obj.get("content", "") or "")
    out_len = len(out_obj.get("content", "") or "")
    ratio = (out_len / en_len) if en_len else 0.0
    band_ok = 0.5 <= ratio <= 2.0
    checks.append(
        Check(
            "content length in band (0.5x-2.0x)",
            band_ok,
            f"{out_len} chars vs {en_len} source (ratio {ratio:.2f})",
        )
    )

    # 7) (informational) content actually changed from English.
    changed = (out_obj.get("content", "") != en_obj.get("content", ""))
    checks.append(
        Check(
            "content differs from English",
            changed,
            "translated" if changed else "identical to source (untranslated?)",
            critical=False,
        )
    )

    return checks


def all_critical_passed(checks: list[Check]) -> bool:
    return all(c.ok for c in checks if c.critical)


def format_report(checks: list[Check]) -> str:
    lines = []
    for c in checks:
        mark = "PASS" if c.ok else ("WARN" if not c.critical else "FAIL")
        lines.append(f"  [{mark}] {c.name}: {c.detail}")
    return "\n".join(lines)
