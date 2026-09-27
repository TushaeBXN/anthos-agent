"""Web research: search, fetch pages, turn HTML into readable text (stdlib only)."""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) smart9b/0.1"


def _get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(2_000_000)
        charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def search_duckduckgo(query: str, n: int = 5) -> list[dict]:
    page = _get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query))
    results = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.DOTALL):
        href = html.unescape(m.group(1))
        # DuckDuckGo wraps links as //duckduckgo.com/l/?uddg=<real url>
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        url = qs.get("uddg", [href])[0]
        if url.startswith("//"):
            url = "https:" + url
        title = re.sub(r"<.*?>", "", html.unescape(m.group(2))).strip()
        if url.startswith("http") and "duckduckgo.com" not in url:
            results.append({"url": url, "title": title})
        if len(results) >= n:
            break
    return results


def search_searxng(base_url: str, query: str, n: int = 5) -> list[dict]:
    url = base_url.rstrip("/") + "/search?format=json&q=" + urllib.parse.quote(query)
    data = json.loads(_get(url))
    return [{"url": r["url"], "title": r.get("title", "")} for r in data.get("results", [])[:n]]


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header", "aside", "form", "svg", "noscript"}
    BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr", "pre", "section", "article"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip_depth += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3") and not self.skip_depth:
            self.parts.append("## ")
        if tag == "li" and not self.skip_depth:
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(page: str) -> str:
    p = _TextExtractor()
    p.feed(page)
    text = "".join(p.parts)
    text = re.sub(r"[ \t]+", " ", text)
    lines = [ln.strip() for ln in text.splitlines()]
    # Drop menu-like crumbs: very short lines that aren't headings or bullets.
    lines = [ln for ln in lines if len(ln) > 30 or ln.startswith(("#", "-")) or ln == ""]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def fetch_text(url: str, max_chars: int = 6000) -> str:
    try:
        return html_to_text(_get(url))[:max_chars]
    except Exception as exc:
        return f"[could not read {url}: {exc}]"


class Researcher:
    def __init__(self, backend: str = "duckduckgo", searxng_url: str = ""):
        self.backend = backend
        self.searxng_url = searxng_url

    def search(self, query: str, n: int = 5) -> list[dict]:
        try:
            if self.backend == "searxng":
                return search_searxng(self.searxng_url, query, n)
            return search_duckduckgo(query, n)
        except Exception:
            return []

    def gather(self, queries: list[str], max_sources: int = 3) -> list[dict]:
        """Search each query, fetch the first unique readable pages."""
        seen, sources = set(), []
        for q in queries:
            for r in self.search(q):
                if r["url"] in seen:
                    continue
                seen.add(r["url"])
                text = fetch_text(r["url"])
                if text.startswith("[could not read") or len(text) < 300:
                    continue
                sources.append({**r, "text": text})
                if len(sources) >= max_sources:
                    return sources
        return sources
