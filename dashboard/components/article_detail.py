"""Article detail component — right panel showing full article details."""

from __future__ import annotations

import html
from typing import Optional
from urllib.parse import urlparse

from src.models import Article
from src.url_utils import is_private_or_reserved_host


def _safe_url(url: str) -> tuple[str, bool]:
    """Return (url, is_https) if url uses http/https and is not a private IP.

    Returns ("", False) for blocked URLs.
    Blocks loopback, private, link-local, and reserved IPs to prevent SSRF-style
    link redirection from LLM-classified or RSS-supplied URLs.
    """
    if not url:
        return ("", False)
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            return ("", False)
        hostname = parsed.hostname
        if not hostname:
            return ("", False)
        if is_private_or_reserved_host(hostname):
            return ("", False)
    except ValueError:
        return ("", False)
    return (url, scheme == "https")


def render_article_detail(article: Optional[Article]) -> str:
    """Render the detail panel for a selected article.

    Returns a placeholder message if article is None.
    All user-facing text is HTML-escaped to prevent XSS.
    """
    if article is None:
        return (
            '<div class="article-detail">'
            '<p style="color:#8b949e;">Select an article from the feed to view details.</p>'
            "</div>"
        )

    title = html.escape(article.title or "")
    title_en = html.escape(article.title_en or "") if article.title_en else ""
    summary = html.escape(article.summary_en or "No summary available.")
    source = html.escape(article.source_name or "")
    category = html.escape(article.category or "")
    country = html.escape(article.country_name or "")
    conf = article.confidence if article.confidence is not None else 0.0
    tier = html.escape(str(article.source_tier))
    url, is_https = _safe_url(article.url)

    # Published date
    if article.published_at is not None:
        pub_date = html.escape(article.published_at.strftime("%Y-%m-%d"))
    else:
        pub_date = "Unknown"

    # Build headline section
    if title_en and title_en != title:
        headline_html = (
            f'<h3>{title_en}</h3>'
            f'<p class="article-meta">Original: {title}</p>'
        )
    elif title_en:
        headline_html = f"<h3>{title_en}</h3>"
    else:
        headline_html = f"<h3>{title}</h3>"

    # Build link — show insecure badge for HTTP URLs
    if url:
        escaped_url = html.escape(url)
        insecure_badge = (
            ' <span style="color:#d29922;font-size:11px;">[insecure]</span>'
            if not is_https else ""
        )
        link_html = (
            f'<a href="{escaped_url}" target="_blank" rel="noopener noreferrer">'
            f"Open Original &rarr;</a>{insecure_badge}"
        )
    else:
        link_html = '<span style="color:#8b949e;">No link available</span>'

    # Original article embed (iframe for https, link-only for http)
    embed_html = ""
    if url:
        escaped_url = html.escape(url)
        if is_https:
            embed_html = (
                f'<div style="margin-top:12px;">'
                f'<div style="color:#8b949e;font-size:11px;margin-bottom:4px;">'
                f'ORIGINAL ARTICLE</div>'
                f'<iframe src="{escaped_url}" '
                f'width="100%" height="400" '
                f'style="border:1px solid #30363d;border-radius:6px;'
                f'background:#fff;" '
                f'sandbox="allow-scripts allow-same-origin" '
                f'loading="lazy"></iframe>'
                f'</div>'
            )
        else:
            embed_html = (
                f'<div style="margin-top:12px;">'
                f'<div style="color:#8b949e;font-size:11px;margin-bottom:4px;">'
                f'ORIGINAL ARTICLE</div>'
                f'<p style="color:#d29922;font-size:12px;">'
                f'Cannot embed insecure (HTTP) page. '
                f'<a href="{escaped_url}" target="_blank" '
                f'rel="noopener noreferrer">Open in new tab &rarr;</a></p>'
                f'</div>'
            )

    return (
        f'<div class="article-detail">'
        f"{headline_html}"
        # AI summary block
        f'<div style="background:#161b22;border:1px solid #30363d;'
        f'border-radius:6px;padding:10px;margin:8px 0;">'
        f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">'
        f'<span style="background:#58a6ff;color:#fff;padding:2px 6px;'
        f'border-radius:3px;font-size:10px;font-weight:600;">AI SUMMARY</span>'
        f'</div>'
        f'<div style="color:#c9d1d9;font-size:13px;line-height:1.5;">'
        f'{summary}</div>'
        f'</div>'
        f"<table>"
        f"<tr><td><strong>Confidence</strong></td><td>{conf:.2f}</td></tr>"
        f"<tr><td><strong>Category</strong></td><td>"
        f'<span class="category-tag">{category}</span></td></tr>'
        f"<tr><td><strong>Country</strong></td><td>{country}</td></tr>"
        f"<tr><td><strong>Source</strong></td><td>{source} (Tier {tier})</td></tr>"
        f"<tr><td><strong>Published</strong></td><td>{pub_date}</td></tr>"
        f"</table>"
        f'<div style="margin-top:8px;">{link_html}</div>'
        f"{embed_html}"
        f"</div>"
    )
