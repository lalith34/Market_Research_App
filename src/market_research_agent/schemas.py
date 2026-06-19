"""Structured output schemas for the competitive analysis."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class CompetitorList(BaseModel):
    """Result of the competitor-discovery step."""

    competitors: List[str] = Field(
        default_factory=list,
        description="Distinct competitor company/product names, most relevant first.",
    )


class SWOT(BaseModel):
    """Target-focused SWOT derived from the competitive landscape.

    Strengths/weaknesses are the TARGET's internal attributes; opportunities/
    threats are external, drawn from what the competitor research surfaced.
    """

    strengths: List[str] = Field(
        default_factory=list, description="Target's internal advantages vs. the field."
    )
    weaknesses: List[str] = Field(
        default_factory=list, description="Target's internal gaps competitors exploit."
    )
    opportunities: List[str] = Field(
        default_factory=list, description="External openings the landscape creates for the target."
    )
    threats: List[str] = Field(
        default_factory=list, description="External threats from competitors / market shifts."
    )


class PricingTier(BaseModel):
    name: str = Field(description="Plan name, e.g. 'Free', 'Pro', 'Enterprise'.")
    price: str = Field(description="Price as written, e.g. '$10/user/mo' or 'Custom'.")
    notes: str = Field(default="", description="Key limits or what's included.")


class CompetitorProfile(BaseModel):
    """Structured insights extracted for a single competitor."""

    name: str
    website: str = Field(default="", description="Primary website URL if found.")
    one_liner: str = Field(default="", description="One-sentence description.")
    is_public: Optional[bool] = Field(
        default=None,
        description="True if the company is publicly traded on a stock exchange, "
        "False if privately held, null/None if the notes don't make it clear.",
    )
    stock_ticker: str = Field(
        default="",
        description="Exchange and ticker if public, e.g. 'NASDAQ: ABNB'. Empty otherwise.",
    )
    headquarters_country: str = Field(
        default="",
        description="Country where the company is headquartered, e.g. 'United States', "
        "'France'. Empty if the notes don't say.",
    )
    is_us_based: Optional[bool] = Field(
        default=None,
        description="True if headquartered in the United States, False if outside the "
        "US, null/None if the notes don't make it clear.",
    )
    positioning: str = Field(
        default="", description="Market positioning / who it targets and how it differentiates."
    )
    target_segments: List[str] = Field(default_factory=list)
    pricing: List[PricingTier] = Field(default_factory=list)
    key_features: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    recent_news: List[str] = Field(
        default_factory=list, description="Recent developments, funding, launches (with rough dates)."
    )
    sources: List[str] = Field(default_factory=list, description="URLs used as evidence.")
