from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from config import TOOL_OUTPUT_CHARS
from tools.files import truncate


def web_search(query: str, max_results: int = 6) -> list[dict]:
    query = (query or "").strip()
    if not query:
        raise ValueError("The search query is empty.")
    from ddgs import DDGS
    results = DDGS().text(query, max_results=max_results) or []
    return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in results]


def fetch_page(url: str) -> str:
    """Download a public web page and return its main text."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Only http(s) pages can be fetched.")
    host = (parsed.hostname or "").casefold()
    if host == "localhost" or host.endswith((".local", ".lan", ".home")):
        raise ValueError("Local network addresses can't be fetched.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved):
        raise ValueError("Local network addresses can't be fetched.")
    import trafilatura
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise RuntimeError(f"Couldn't download {url}.")
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=True) or ""
    if not text.strip():
        raise RuntimeError("The page had no readable main text.")
    return truncate(text.strip(), TOOL_OUTPUT_CHARS)
