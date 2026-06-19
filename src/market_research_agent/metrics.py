"""Run-level cost / latency / reliability tracking.

Implements the "cost, latency, reliability" theme: every LLM call and
tool call is counted so a run can be judged on more than its output. Token
counts are best-effort — they're captured wherever the provider returns
`usage_metadata` (OpenAI-compatible endpoints like Nebius do).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class RunMetrics:
    """Mutable sink accumulated across a single `run_analysis` call."""

    started_at: float = field(default_factory=time.perf_counter)
    elapsed_s: float = 0.0

    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    tool_calls: int = 0
    tool_breakdown: Dict[str, int] = field(default_factory=dict)

    # Reliability / failure-mode counters.
    duplicate_tool_calls: int = 0   # same tool+args repeated → loop / wasted tokens
    unknown_tool_calls: int = 0     # model hallucinated a tool name
    tool_errors: int = 0            # tool raised / returned an error

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def record_usage(self, message: Any) -> None:
        """Pull token usage off an AIMessage if the provider supplied it."""
        usage = getattr(message, "usage_metadata", None)
        if not usage:
            return
        self.llm_calls += 1
        self.input_tokens += int(usage.get("input_tokens", 0) or 0)
        self.output_tokens += int(usage.get("output_tokens", 0) or 0)

    def record_tool(self, name: str) -> None:
        self.tool_calls += 1
        self.tool_breakdown[name] = self.tool_breakdown.get(name, 0) + 1

    def finalize(self) -> "RunMetrics":
        self.elapsed_s = time.perf_counter() - self.started_at
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "elapsed_s": round(self.elapsed_s, 1),
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "tool_calls": self.tool_calls,
            "tool_breakdown": dict(self.tool_breakdown),
            "duplicate_tool_calls": self.duplicate_tool_calls,
            "unknown_tool_calls": self.unknown_tool_calls,
            "tool_errors": self.tool_errors,
        }

    def summary(self) -> str:
        """One-glance human-readable footer for the CLI."""
        toks = (
            f"{self.total_tokens:,} tokens "
            f"({self.input_tokens:,} in / {self.output_tokens:,} out)"
        )
        line = (
            f"⏱  {self.elapsed_s:.1f}s · {self.llm_calls} LLM calls · {toks} · "
            f"{self.tool_calls} tool calls"
        )
        flags = []
        if self.duplicate_tool_calls:
            flags.append(f"{self.duplicate_tool_calls} duplicate")
        if self.unknown_tool_calls:
            flags.append(f"{self.unknown_tool_calls} unknown-tool")
        if self.tool_errors:
            flags.append(f"{self.tool_errors} tool-error")
        if flags:
            line += "\n   ⚠ reliability: " + ", ".join(flags)
        return line
