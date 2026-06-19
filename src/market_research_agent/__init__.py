"""Market Research Agent — autonomous competitor analysis.

Public API:
    from market_research_agent import run_analysis, Settings
"""
from .config import Settings
from .pipeline import run_analysis

__all__ = ["Settings", "run_analysis"]
__version__ = "0.1.0"
