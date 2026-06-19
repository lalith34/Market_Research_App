"""Runtime configuration, loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    """All knobs for the agent. Construct with `Settings.from_env()`."""

    # LLM (Nebius AI Studio — OpenAI-compatible endpoint)
    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.studio.nebius.com/v1/"
    model: str = "deepseek-ai/DeepSeek-V3.2"
    temperature: float = 0.2

    # Search
    search: str = "auto"          # auto | ddg | tavily
    tavily_api_key: str = ""

    # Behavior
    mode: str = "auto"            # auto | brand | category (how to read the target)
    competitors: list = field(default_factory=list)  # pin an explicit list, skip discovery
    max_competitors: int = 3
    max_research_steps: int = 6
    request_timeout: int = 25
    max_page_chars: int = 6000    # truncate fetched pages fed to the LLM

    # Reflection pattern (Draft -> Critique -> Revise on the synthesis).
    reflection: bool = True
    max_reflection_rounds: int = 1

    # Target-focused SWOT analysis section in the briefing.
    swot: bool = True

    # Human-in-the-loop: pause after discovery so a human can edit the
    # competitor list before the (expensive) research stage runs.
    human_review: bool = False

    # Load the bundled Hacker News MCP tool by default (needs MCP deps installed;
    # degrades gracefully to core tools if they're not).
    hn_tool: bool = True

    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            nebius_api_key=os.getenv("NEBIUS_API_KEY", ""),
            nebius_base_url=os.getenv("NEBIUS_BASE_URL", cls.nebius_base_url),
            model=os.getenv("MRA_MODEL", cls.model),
            temperature=_float("MRA_TEMPERATURE", cls.temperature),
            search=os.getenv("MRA_SEARCH", cls.search).lower(),
            tavily_api_key=os.getenv("TAVILY_API_KEY", ""),
            mode=os.getenv("MRA_MODE", cls.mode).lower(),
            competitors=[c.strip() for c in os.getenv("MRA_COMPETITORS", "").split(",") if c.strip()],
            max_competitors=_int("MRA_MAX_COMPETITORS", cls.max_competitors),
            max_research_steps=_int("MRA_MAX_RESEARCH_STEPS", cls.max_research_steps),
            request_timeout=_int("MRA_REQUEST_TIMEOUT", cls.request_timeout),
            reflection=_bool("MRA_REFLECTION", cls.reflection),
            max_reflection_rounds=_int("MRA_MAX_REFLECTION_ROUNDS", cls.max_reflection_rounds),
            swot=_bool("MRA_SWOT", cls.swot),
            human_review=_bool("MRA_HUMAN_REVIEW", cls.human_review),
            hn_tool=_bool("MRA_HN", cls.hn_tool),
        )

    @property
    def search_backend(self) -> str:
        """Resolve 'auto' into a concrete backend."""
        if self.search == "auto":
            return "tavily" if self.tavily_api_key else "ddg"
        return self.search

    @property
    def discovery_mode(self) -> str:
        """How to interpret the target: 'brand', 'category', or 'auto'."""
        return self.mode if self.mode in {"brand", "category"} else "auto"

    def require_llm(self) -> None:
        if not self.nebius_api_key:
            raise RuntimeError(
                "NEBIUS_API_KEY is not set. Copy .env.example to .env and add your key, "
                "or export NEBIUS_API_KEY=... before running."
            )
