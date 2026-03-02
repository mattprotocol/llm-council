"""Web search integration for the LLM Council.

Provides search context for questions that benefit from up-to-date information.
Supports multiple search providers with automatic fallback:
  - DuckDuckGo (free, no API key needed)
  - Serper (fast Google results, needs SERPER_API_KEY)
  - Tavily (AI-optimized search, needs TAVILY_API_KEY)
  - Brave (privacy-focused, needs BRAVE_API_KEY)

Also includes Jina Reader for extracting full article content from URLs.
"""

import httpx
import os
import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# Search provider API keys
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
JINA_API_KEY = os.getenv("JINA_API_KEY", "")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    content: str = ""  # Full article content (from Jina Reader)
    relevance: float = 0.0


@dataclass
class SearchContext:
    """Aggregated search results ready for injection into prompts."""
    query: str
    results: List[SearchResult] = field(default_factory=list)
    provider: str = ""

    def to_prompt_context(self, max_results: int = 3, max_chars: int = 2000) -> str:
        """Format search results as context for LLM prompts."""
        if not self.results:
            return ""

        lines = [f"[Web Search Results for: {self.query}]"]
        for i, r in enumerate(self.results[:max_results]):
            text = r.content if r.content else r.snippet
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            lines.append(f"\n--- Source {i+1}: {r.title} ---")
            lines.append(f"URL: {r.url}")
            lines.append(text)

        lines.append("\n[End of Search Results]")
        return "\n".join(lines)


def detect_search_intent(question: str) -> bool:
    """Detect whether a question would benefit from web search context.

    Returns True for questions about current events, recent data,
    specific facts, or topics that change frequently.
    """
    question_lower = question.lower()

    # Strong indicators of search need
    search_patterns = [
        r"\b(latest|recent|current|today|this week|this month|this year|202\d)\b",
        r"\b(news|update|announcement|release|launch)\b",
        r"\b(price|stock|weather|score|result)\b",
        r"\b(who is|what is|when did|where is|how many)\b",
        r"\b(compare|vs|versus|difference between)\b",
        r"\b(best|top|recommend)\b.{0,30}\b(202\d|now|currently)\b",
    ]

    for pattern in search_patterns:
        if re.search(pattern, question_lower):
            return True

    # Questions with proper nouns (names, companies, etc.) often need search
    # Simple heuristic: words starting with uppercase that aren't sentence starters
    words = question.split()
    if len(words) > 2:
        proper_nouns = [w for w in words[1:] if w[0].isupper() and not w.isupper()]
        if len(proper_nouns) >= 2:
            return True

    return False


async def search_duckduckgo(query: str, max_results: int = 5) -> List[SearchResult]:
    """Search using DuckDuckGo Instant Answer API (free, no key needed)."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            # Use the DuckDuckGo HTML endpoint for better results
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "LLM-Council/1.0"},
                follow_redirects=True,
            )
            response.raise_for_status()
            # Parse basic results from HTML response
            results = _parse_ddg_html(response.text, max_results)
            return results
    except Exception as e:
        print(f"DuckDuckGo search error: {e}")
        return []


def _parse_ddg_html(html: str, max_results: int) -> List[SearchResult]:
    """Parse search results from DuckDuckGo HTML response."""
    results = []
    # Simple regex-based parsing of result snippets
    # Match result links and snippets
    link_pattern = re.compile(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
    snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)

    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i in range(min(len(links), len(snippets), max_results)):
        url = links[i][0]
        # DuckDuckGo wraps URLs in a redirect
        if "uddg=" in url:
            url_match = re.search(r'uddg=([^&]+)', url)
            if url_match:
                from urllib.parse import unquote
                url = unquote(url_match.group(1))

        title = re.sub(r'<[^>]+>', '', links[i][1]).strip()
        snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()

        if title and url:
            results.append(SearchResult(title=title, url=url, snippet=snippet))

    return results


async def search_serper(query: str, max_results: int = 5) -> List[SearchResult]:
    """Search using Serper.dev (Google results)."""
    if not SERPER_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(
                "https://google.serper.dev/search",
                json={"q": query, "num": max_results},
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            results = []
            for item in data.get("organic", [])[:max_results]:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                ))
            return results
    except Exception as e:
        print(f"Serper search error: {e}")
        return []


async def search_tavily(query: str, max_results: int = 5) -> List[SearchResult]:
    """Search using Tavily (AI-optimized search)."""
    if not TAVILY_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": query,
                    "max_results": max_results,
                    "include_raw_content": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            results = []
            for item in data.get("results", [])[:max_results]:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                ))
            return results
    except Exception as e:
        print(f"Tavily search error: {e}")
        return []


async def search_brave(query: str, max_results: int = 5) -> List[SearchResult]:
    """Search using Brave Search API."""
    if not BRAVE_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY},
            )
            response.raise_for_status()
            data = response.json()
            results = []
            for item in data.get("web", {}).get("results", [])[:max_results]:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("description", ""),
                ))
            return results
    except Exception as e:
        print(f"Brave search error: {e}")
        return []


async def fetch_article_content(url: str) -> str:
    """Fetch full article content using Jina Reader API."""
    try:
        headers = {"Accept": "text/plain"}
        if JINA_API_KEY:
            headers["Authorization"] = f"Bearer {JINA_API_KEY}"

        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.get(
                f"https://r.jina.ai/{url}",
                headers=headers,
                follow_redirects=True,
            )
            response.raise_for_status()
            content = response.text
            # Truncate very long articles
            if len(content) > 5000:
                content = content[:5000] + "\n[Content truncated]"
            return content
    except Exception as e:
        print(f"Jina Reader error for {url}: {e}")
        return ""


# Provider priority order
_SEARCH_PROVIDERS = [
    ("serper", search_serper),
    ("tavily", search_tavily),
    ("brave", search_brave),
    ("duckduckgo", search_duckduckgo),
]


def get_available_providers() -> List[str]:
    """Return list of search providers with valid API keys."""
    available = []
    if SERPER_API_KEY:
        available.append("serper")
    if TAVILY_API_KEY:
        available.append("tavily")
    if BRAVE_API_KEY:
        available.append("brave")
    available.append("duckduckgo")  # Always available (no key needed)
    return available


async def search(
    query: str,
    max_results: int = 5,
    provider: Optional[str] = None,
    fetch_content: bool = False,
) -> SearchContext:
    """Execute a web search with automatic provider fallback.

    If provider is None, tries providers in priority order until one succeeds.
    If fetch_content is True, uses Jina Reader to get full article text for top results.
    """
    results = []
    used_provider = ""

    if provider:
        # Use specific provider
        for name, func in _SEARCH_PROVIDERS:
            if name == provider:
                results = await func(query, max_results)
                used_provider = name
                break
    else:
        # Try providers in priority order
        for name, func in _SEARCH_PROVIDERS:
            results = await func(query, max_results)
            if results:
                used_provider = name
                break

    # Optionally fetch full content for top results
    if fetch_content and results:
        import asyncio
        top_results = results[:2]  # Fetch content for top 2
        contents = await asyncio.gather(
            *[fetch_article_content(r.url) for r in top_results],
            return_exceptions=True,
        )
        for r, content in zip(top_results, contents):
            if isinstance(content, str):
                r.content = content

    return SearchContext(query=query, results=results, provider=used_provider)


def get_search_config() -> Dict[str, Any]:
    """Return current search configuration."""
    return {
        "available_providers": get_available_providers(),
        "jina_available": bool(JINA_API_KEY),
        "intent_detection": True,
    }
