"""Document retrieval tool: fetch a URL and return clean main-content text."""
from __future__ import annotations

import httpx
from langchain_core.tools import StructuredTool

from ..config import Settings
from ..guardrails import is_safe_url

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _extract(html: str, url: str) -> str:
    try:
        import trafilatura

        text = trafilatura.extract(
            html, include_comments=False, include_tables=True, url=url
        )
        if text:
            return text
    except Exception:
        pass
    # Fallback: crude tag strip
    try:
        from html.parser import HTMLParser

        class _Strip(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.parts: list[str] = []
                self._skip = False

            def handle_starttag(self, tag, attrs):
                if tag in {"script", "style", "noscript"}:
                    self._skip = True

            def handle_endtag(self, tag):
                if tag in {"script", "style", "noscript"}:
                    self._skip = False

            def handle_data(self, data):
                if not self._skip and data.strip():
                    self.parts.append(data.strip())

        s = _Strip()
        s.feed(html)
        return " ".join(s.parts)
    except Exception:
        return ""


def make_fetch_tool(settings: Settings) -> StructuredTool:
    def fetch_page(url: str) -> str:
        """Fetch a web page and return its cleaned main text content.

        Use after web_search to read a promising page (e.g. a pricing or features page).
        """
        if not url.startswith(("http://", "https://")):
            return f"Invalid URL: {url!r}"
        # SSRF guardrail: refuse internal/non-public targets before connecting.
        ok, reason = is_safe_url(url)
        if not ok:
            return f"Blocked URL {url}: {reason}"
        try:
            with httpx.Client(
                follow_redirects=True, timeout=settings.request_timeout, headers=_HEADERS
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                # A redirect may have landed on an internal host — re-check before
                # returning any content fetched from it.
                final_ok, final_reason = is_safe_url(str(resp.url))
                if not final_ok:
                    return f"Blocked redirect to {resp.url}: {final_reason}"
                html = resp.text
        except Exception as exc:
            return f"Fetch error for {url}: {exc}"

        text = _extract(html, url).strip()
        if not text:
            return f"No extractable text from {url}."
        if len(text) > settings.max_page_chars:
            text = text[: settings.max_page_chars] + "\n...[truncated]"
        return f"Content from {url}:\n{text}"

    return StructuredTool.from_function(
        func=fetch_page,
        name="fetch_page",
        description=(
            "Fetch a URL and return its cleaned main-content text. Use to read a page "
            "found via web_search (pricing, features, news, etc.)."
        ),
    )
