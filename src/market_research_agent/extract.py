"""Robust structured output for open models behind an OpenAI-compatible API.

Tries native structured output first; falls back to JSON-from-text parsing so
the pipeline survives models with shaky function-calling support.
"""
from __future__ import annotations

import json
import re
from typing import Type, TypeVar

from langchain_core.messages import BaseMessage, SystemMessage
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def _json_from_text(text: str) -> dict:
    """Best-effort: pull the first JSON object out of a model response."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            candidate = text[start : end + 1]
    if candidate is None:
        raise ValueError("No JSON object found in model output.")
    return json.loads(candidate)


def structured_invoke(llm, schema: Type[T], messages: list[BaseMessage], metrics=None) -> T:
    """Invoke `llm` and coerce the result into `schema`.

    If `metrics` (a RunMetrics) is supplied, token usage from the underlying
    LLM call is recorded onto it.
    """
    # 1) Native structured output (function calling / json mode). `include_raw`
    #    keeps the raw AIMessage around so we can read its token usage.
    try:
        out = llm.with_structured_output(schema, include_raw=True).invoke(messages)
        if metrics is not None:
            metrics.record_usage(out.get("raw"))
        parsed = out.get("parsed")
        if parsed is not None:
            return parsed
        # parsing failed inside the wrapper — fall through to text parsing.
    except Exception:
        pass

    # 2) Fallback: ask for raw JSON and parse it ourselves.
    fields = json.dumps(schema.model_json_schema().get("properties", {}), indent=2)
    instruction = SystemMessage(
        content=(
            "Respond with ONLY a single valid JSON object matching this schema "
            f"(no prose, no markdown fences):\n{fields}"
        )
    )
    raw = llm.invoke(messages + [instruction])
    if metrics is not None:
        metrics.record_usage(raw)
    text = raw.content if isinstance(raw, BaseMessage) else str(raw)
    data = _json_from_text(text)
    return schema.model_validate(data)
