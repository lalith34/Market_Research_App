"""LLM factory. Nebius is OpenAI-compatible, so we drive it via ChatOpenAI.

Swapping providers is just a base_url / key change — any OpenAI-compatible
endpoint (Nebius, Together, OpenRouter, vLLM, ...) works unchanged.
"""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from .config import Settings


def make_llm(settings: Settings, *, temperature: float | None = None) -> ChatOpenAI:
    settings.require_llm()
    return ChatOpenAI(
        model=settings.model,
        api_key=settings.nebius_api_key,
        base_url=settings.nebius_base_url,
        temperature=settings.temperature if temperature is None else temperature,
        timeout=settings.request_timeout,
        max_retries=2,
    )
