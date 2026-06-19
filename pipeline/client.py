"""LM Studio (OpenAI-compatible) client — per-element translation.

Each request shares a byte-identical prefix (system + the English-chapter context)
and varies only the trailing per-element task + language word. That's what makes
KV-cache prefix reuse possible, and it keeps each generation small and focused.

- ``translate_element_stream`` streams one element and measures TTFT (Test A).
- ``translate_element`` returns one element's parsed value (Test B).
- ``translate_chapter`` runs every element and assembles the translated payload.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from openai import BadRequestError, OpenAI

import config
import fields

_client = OpenAI(base_url=config.BASE_URL, api_key=config.API_KEY, timeout=config.REQUEST_TIMEOUT)

# Disable Qwen reasoning via the chat-template kwarg; fall back to omitting it if the
# server rejects it. Both fallbacks latch for the rest of the run so the cache test
# isn't confounded by a mid-run prompt/option change.
_THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}
_use_extra_body = True
_force_text_format = False

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


@dataclass
class StreamResult:
    text: str
    ttft: float | None          # seconds to first generated content token
    total_time: float           # seconds for the whole request
    prompt_tokens: int | None
    completion_tokens: int | None


def build_messages(en_obj: dict[str, Any], element: config.Element, language_name: str) -> list[dict[str, str]]:
    """system + (context + element task + language-last). Context is the shared prefix."""
    context = fields.render_context(en_obj)
    user = (
        f"{context}\n\n"
        f"TASK: {element.task}\n\n"
        f"{config.TARGET_LANGUAGE_LABEL}\n{language_name}"
    )
    return [
        {"role": "system", "content": config.SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _response_format(kind: str) -> dict:
    if _force_text_format:
        return config.TEXT_FORMAT
    return config.RESPONSE_FORMATS[kind]


def _request_kwargs(messages: list[dict[str, str]], kind: str, *, stream: bool) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": config.MODEL_ID,
        "messages": messages,
        "temperature": config.TEMPERATURE,
        "max_tokens": config.MAX_TOKENS,
        "response_format": _response_format(kind),
        "stream": stream,
    }
    if stream:
        kwargs["stream_options"] = {"include_usage": True}
    if _use_extra_body:
        kwargs["extra_body"] = dict(_THINKING_OFF)
    return kwargs


def _create(messages: list[dict[str, str]], kind: str, *, stream: bool):
    """Issue the request, downgrading unsupported options once and retrying."""
    global _use_extra_body, _force_text_format
    try:
        return _client.chat.completions.create(**_request_kwargs(messages, kind, stream=stream))
    except BadRequestError as exc:
        msg = str(exc)
        if _use_extra_body and "chat_template_kwargs" in msg:
            print("  [warn] server rejected enable_thinking kwarg; retrying without it "
                  "(disable thinking in the LM Studio app instead).")
            _use_extra_body = False
            return _create(messages, kind, stream=stream)
        if not _force_text_format and "response_format" in msg:
            print("  [warn] server rejected json_schema response_format; "
                  "falling back to text (relying on parse_json).")
            _force_text_format = True
            return _create(messages, kind, stream=stream)
        raise


def translate_element_stream(en_obj: dict[str, Any], element: config.Element, language_name: str) -> StreamResult:
    """Streaming call that measures TTFT and captures usage. Used by Test A."""
    messages = build_messages(en_obj, element, language_name)
    t0 = time.perf_counter()
    ttft: float | None = None
    chunks: list[str] = []
    prompt_tokens = completion_tokens = None

    for chunk in _create(messages, element.kind, stream=True):
        if getattr(chunk, "usage", None):
            prompt_tokens = chunk.usage.prompt_tokens
            completion_tokens = chunk.usage.completion_tokens
        if not chunk.choices:
            continue
        piece = getattr(chunk.choices[0].delta, "content", None)
        if piece:
            if ttft is None:
                ttft = time.perf_counter() - t0
            chunks.append(piece)

    return StreamResult(
        text=_clean("".join(chunks)),
        ttft=ttft,
        total_time=time.perf_counter() - t0,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def translate_element(en_obj: dict[str, Any], element: config.Element, language_name: str) -> tuple[Any, StreamResult]:
    """Non-streaming call returning the element's parsed value + timing. Used by Test B."""
    messages = build_messages(en_obj, element, language_name)
    t0 = time.perf_counter()
    resp = _create(messages, element.kind, stream=False)
    total_time = time.perf_counter() - t0

    text = _clean(resp.choices[0].message.content or "")
    usage = getattr(resp, "usage", None)
    result = StreamResult(
        text=text,
        ttft=None,
        total_time=total_time,
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
    )
    return _parse_value(text, element.kind), result


def translate_elements(
    en_obj: dict[str, Any],
    language_name: str,
    elements: "tuple[config.Element, ...]",
    *,
    verbose: bool = True,
) -> tuple[dict[str, Any], dict[str, StreamResult]]:
    """Translate the given elements via Qwen and collect values + timings."""
    payload: dict[str, Any] = {}
    timings: dict[str, StreamResult] = {}
    for element in elements:
        value, result = translate_element(en_obj, element, language_name)
        payload[element.key] = value
        timings[element.key] = result
        if verbose:
            print(f"    qwen {element.key:<16} {result.total_time:6.1f}s  "
                  f"completion={result.completion_tokens} tok")
    return payload, timings


def translate_chapter(en_obj: dict[str, Any], language_name: str, *, verbose: bool = True) -> tuple[dict[str, Any], dict[str, StreamResult]]:
    """Translate every element (incl. body) via Qwen. Kept for the all-Qwen path."""
    return translate_elements(en_obj, language_name, config.ELEMENTS, verbose=verbose)


def translate_seo(en_obj: dict[str, Any], language_name: str, *, verbose: bool = True) -> tuple[dict[str, Any], dict[str, StreamResult]]:
    """Translate only the SEO elements via Qwen (body goes to NLLB). Tier-1 path."""
    return translate_elements(en_obj, language_name, config.SEO_ELEMENTS, verbose=verbose)


def _parse_value(text: str, kind: str) -> Any:
    if kind == "text":
        return text
    data = parse_json(text)
    # Unwrap {"value": [...]} from the json_schema; tolerate a bare array (text fallback).
    if isinstance(data, dict) and "value" in data:
        return data["value"]
    return data


def _clean(text: str) -> str:
    text = _THINK_RE.sub("", text)
    return _FENCE_RE.sub("", text.strip()).strip()


def parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Recover an object or array embedded in surrounding noise.
        candidates = [(text.find("{"), text.rfind("}")), (text.find("["), text.rfind("]"))]
        for start, end in candidates:
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
        raise
