"""News feed component — scrollable card list of flagged articles.

NOTE: This module is not used by the running dashboard (app.py uses
st.button() widgets directly per the M21 fix). Retained for backward
compatibility and test coverage. Related CSS class `.article-card` in
dark_theme.css is also unused by the live app.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Optional

from src.models import Article


def format_time_ago(
    published_at: Optional[datetime],
    now: Optional[datetime] = None,
) -> str:
    """Return a human-readable relative time string.

    Returns 'just now', 'Xm ago', 'Xh ago', or 'Xd ago'.
    Returns 'unknown' if published_at is None.
    """
    if published_at is None:
        return "unknown"
    if now is None:
        now = datetime.now(tz=timezone.utc)
    # Ensure both are tz-aware to prevent TypeError on subtraction.
    # Check utcoffset() instead of tzinfo to handle tzinfo objects
    # that return None from utcoffset() (still considered naive).
    if published_at.utcoffset() is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    if now.utcoffset() is None:
        now = now.replace(tzinfo=timezone.utc)
    delta_seconds = int((now - published_at).total_seconds())
    if delta_seconds < 60:
        return "just now"
    if delta_seconds < 3600:
        return f"{delta_seconds // 60}m ago"
    if delta_seconds < 86400:
        return f"{delta_seconds // 3600}h ago"
    return f"{delta_seconds // 86400}d ago"


def confidence_class(confidence: Optional[float]) -> str:
    """Return the CSS class for a confidence badge."""
    if confidence is not None and confidence >= 0.8:
        return "confidence-high"
    return "confidence-medium"


def render_article_card(article: Article) -> str:
    """Render a single article as an HTML card.

    All user-facing text is HTML-escaped to prevent XSS.
    """
    title = html.escape(article.title or "")
    source = html.escape(article.source_name or "")
    country = html.escape(article.country_name or "")
    conf = article.confidence if article.confidence is not None else 0.0
    conf_cls = confidence_class(article.confidence)
    time_ago = format_time_ago(article.published_at)

    return (
        f'<div class="article-card" data-article-id="{html.escape(article.id)}">'
        f'<div class="article-title">{title}</div>'
        f'<div class="article-meta">'
        f'<span class="{conf_cls}">{conf:.2f}</span>'
        f" | {country}"
        f" | {source}"
        f" | {time_ago}"
        f"</div>"
        f"</div>"
    )


def render_news_feed(articles: list[Article]) -> str:
    """Render a scrollable news feed of article cards.

    Articles are sorted by confidence descending.
    Returns HTML with a 'news-feed' wrapper div.
    """
    if not articles:
        return '<div class="news-feed"><p style="color:#8b949e;">No articles found.</p></div>'

    sorted_articles = sorted(
        articles,
        key=lambda a: a.confidence if a.confidence is not None else 0.0,
        reverse=True,
    )
    cards = [render_article_card(a) for a in sorted_articles]
    return f'<div class="news-feed">{"".join(cards)}</div>'
