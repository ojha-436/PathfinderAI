"""Job-description ingestion for the Apply Studio (plan-apply.md, Phase B).

Compliant by construction: pasted text ALWAYS passes through; a URL is fetched
ONLY for public / ATS hosts (Greenhouse, Lever, Ashby, company career pages).
ToS-/JS-walled sites (LinkedIn, Indeed, Workday, Naukri, Glassdoor) are blocked
with a friendly "paste the description instead" — we never scrape them.

`extract(url|text)` returns {jd_text, source, blocked, message}. Skill parsing +
matching reuse the existing `jd_parser` / `matching` engines (grounded).
"""
from __future__ import annotations

import re
import sys
import urllib.request
from typing import Dict, Optional
from urllib.parse import urlparse

# Hosts we must not scrape (ToS / bot-walls / JS-only). Paste-text is the path.
_BLOCKED = ("linkedin.", "indeed.", "workday", "myworkdayjobs.", "naukri.",
            "glassdoor.", "ziprecruiter.", "monster.")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_WS_RE = re.compile(r"[ \t]+")
_BLANKS_RE = re.compile(r"\n\s*\n\s*\n+")
_MAX_FETCH_BYTES = 800_000


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _html_to_text(html: str) -> str:
    html = _SCRIPT_STYLE_RE.sub(" ", html)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</(p|div|li|h[1-6]|tr)>", "\n", html, flags=re.I)
    text = _HTML_TAG_RE.sub(" ", html)
    text = (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"'))
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANKS_RE.sub("\n\n", text).strip()


def _fetch(url: str) -> str:  # pragma: no cover - network
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; PathFinderBot/1.0; +https://pathfinder.app)",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(req, timeout=12) as resp:
        raw = resp.read(_MAX_FETCH_BYTES)
    return raw.decode("utf-8", errors="ignore")


def extract(url: Optional[str] = None, jd_text: Optional[str] = None) -> Dict[str, object]:
    """Resolve a JD from pasted text or a public/ATS URL. Never raises."""
    if jd_text and jd_text.strip():
        return {"jd_text": jd_text.strip(), "source": "pasted", "blocked": False, "message": ""}

    if url and url.strip():
        u = url.strip()
        if not re.match(r"^https?://", u, re.I):
            u = "https://" + u
        host = _host(u)
        if any(b in host for b in _BLOCKED):
            return {
                "jd_text": "", "source": host or "url", "blocked": True,
                "message": (f"{host} blocks automated access (their terms). "
                            "Open the posting, copy the job description, and paste it below — "
                            "PathFinder handles the rest."),
            }
        try:
            text = _html_to_text(_fetch(u))
            if len(text) < 120:
                return {"jd_text": "", "source": host, "blocked": True,
                        "message": "That page didn't return a readable description — please paste the job text below."}
            return {"jd_text": text[:20000], "source": host, "blocked": False, "message": ""}
        except Exception as exc:
            print(f"[PathFinder] JD fetch failed for {host}: {exc}", file=sys.stderr)
            return {"jd_text": "", "source": host, "blocked": True,
                    "message": "Couldn't fetch that URL — please paste the job description below instead."}

    return {"jd_text": "", "source": "", "blocked": True,
            "message": "Paste a job description, or provide a public job-posting URL."}
