"""Dynamic surveillance/censorship analysis from DB articles.

Generates HTML analysis panels from article data — category distribution,
confidence stats, source tiers, key themes extracted from titles.
All text is HTML-escaped for XSS safety.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from typing import Any

from src.models import Article


# Common stop words to filter from theme extraction
_STOP_WORDS = frozenset({
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
    "is", "are", "was", "were", "be", "been", "has", "have", "had", "with",
    "from", "by", "as", "it", "its", "that", "this", "but", "not", "can",
    "will", "may", "would", "could", "should", "do", "does", "did", "new",
    "over", "after", "about", "how", "why", "what", "who", "which", "more",
    "than", "all", "no", "up", "out", "says", "said", "also", "into",
    "being", "been", "between", "under", "through", "against", "during",
    "before", "year", "years", "news", "report", "reports", "government",
})

_WORD_RE = re.compile(r"[a-z]{3,}")

# Category display labels and colors
_CATEGORY_COLORS: dict[str, str] = {
    "surveillance": "#f85149",
    "censorship": "#d29922",
    "facial_recognition": "#a371f7",
    "internet_shutdown": "#f0883e",
    "data_collection": "#58a6ff",
    "social_media_control": "#3fb950",
    "digital_rights": "#79c0ff",
    "other": "#8b949e",
}


def _extract_themes(articles: list[Article], top_n: int = 8) -> list[tuple[str, int]]:
    """Extract top themes from article titles via word frequency."""
    word_counts: Counter[str] = Counter()
    for article in articles:
        title = (article.title or "").lower()
        words = _WORD_RE.findall(title)
        word_counts.update(w for w in words if w not in _STOP_WORDS)
    return word_counts.most_common(top_n)


def _category_bar(label: str, count: int, total: int) -> str:
    """Render a single category bar."""
    pct = (count / total * 100) if total > 0 else 0
    color = _CATEGORY_COLORS.get(label, "#8b949e")
    safe_label = html.escape(label.replace("_", " ").title())
    return (
        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
        f'<span style="color:#8b949e;font-size:11px;width:120px;'
        f'text-align:right;flex-shrink:0;">{safe_label}</span>'
        f'<div style="flex:1;height:14px;background:#21262d;border-radius:3px;overflow:hidden;">'
        f'<div style="width:{pct:.1f}%;height:100%;background:{color};'
        f'border-radius:3px;min-width:2px;"></div></div>'
        f'<span style="color:#e6edf3;font-size:11px;width:24px;">{count}</span>'
        f'</div>'
    )


def render_country_analysis(articles: list[Article], country_name: str) -> str:
    """Render dynamic analysis panel for a country from its articles.

    All user-facing text is HTML-escaped.
    """
    safe_name = html.escape(country_name)
    n = len(articles)

    if n == 0:
        return (
            f'<div style="background:#161b22;border:1px solid #30363d;'
            f'border-radius:6px;padding:12px;">'
            f'<div style="color:#8b949e;font-size:13px;text-align:center;">'
            f'No surveillance/censorship articles collected for {safe_name} yet.'
            f'</div></div>'
        )

    # Date range
    dates = [a.published_at for a in articles if a.published_at]
    date_range = ""
    if dates:
        earliest = min(dates)
        latest = max(dates)
        # published_at may be str or datetime — handle both
        e_str = earliest.strftime("%Y-%m-%d") if hasattr(earliest, "strftime") else str(earliest)[:10]
        l_str = latest.strftime("%Y-%m-%d") if hasattr(latest, "strftime") else str(latest)[:10]
        date_range = f"{e_str} — {l_str}"

    # Category distribution
    cat_counts: Counter[str] = Counter()
    for a in articles:
        if a.category:
            cat_counts[a.category] += 1

    cat_bars = "".join(
        _category_bar(cat, cnt, n)
        for cat, cnt in cat_counts.most_common()
    )

    # Confidence stats
    confs = [a.confidence for a in articles if a.confidence is not None]
    avg_conf = sum(confs) / len(confs) if confs else 0.0
    high_conf = sum(1 for c in confs if c >= 0.8)

    # Source tiers
    tier_counts: Counter[int] = Counter()
    for a in articles:
        if a.source_tier is not None:
            tier_counts[a.source_tier] += 1
    tier_labels = {1: "Wire", 2: "Major", 3: "Specialty", 4: "Regional"}
    tier_html = " ".join(
        f'<span style="background:#21262d;color:#e6edf3;padding:2px 8px;'
        f'border-radius:3px;font-size:11px;border:1px solid #30363d;">'
        f'{tier_labels.get(t, f"T{t}")}: {c}</span>'
        for t, c in sorted(tier_counts.items())
    )

    # Key themes
    themes = _extract_themes(articles)
    theme_tags = " ".join(
        f'<span style="background:#21262d;color:#79c0ff;padding:2px 8px;'
        f'border-radius:10px;font-size:11px;border:1px solid #30363d;">'
        f'{html.escape(w)} ({c})</span>'
        for w, c in themes
    )

    return (
        f'<div style="background:#161b22;border:1px solid #30363d;'
        f'border-radius:6px;padding:10px;font-family:-apple-system,BlinkMacSystemFont,'
        f'\'Segoe UI\',sans-serif;">'
        # Header
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'margin-bottom:8px;">'
        f'<span style="color:#e6edf3;font-size:14px;font-weight:600;">'
        f'{safe_name} — Live Analysis</span>'
        f'<span style="background:#f85149;color:#fff;padding:2px 8px;'
        f'border-radius:3px;font-size:10px;font-weight:600;">LIVE</span>'
        f'</div>'
        # Stats row
        f'<div style="display:flex;gap:12px;margin-bottom:8px;flex-wrap:wrap;">'
        f'<div style="background:#0d1117;padding:6px 10px;border-radius:4px;'
        f'border:1px solid #30363d;">'
        f'<div style="color:#8b949e;font-size:10px;">ARTICLES</div>'
        f'<div style="color:#e6edf3;font-size:16px;font-weight:700;">{n}</div>'
        f'</div>'
        f'<div style="background:#0d1117;padding:6px 10px;border-radius:4px;'
        f'border:1px solid #30363d;">'
        f'<div style="color:#8b949e;font-size:10px;">AVG CONFIDENCE</div>'
        f'<div style="color:#e6edf3;font-size:16px;font-weight:700;">{avg_conf:.0%}</div>'
        f'</div>'
        f'<div style="background:#0d1117;padding:6px 10px;border-radius:4px;'
        f'border:1px solid #30363d;">'
        f'<div style="color:#8b949e;font-size:10px;">HIGH CONF (>80%)</div>'
        f'<div style="color:#f85149;font-size:16px;font-weight:700;">{high_conf}</div>'
        f'</div>'
        f'<div style="background:#0d1117;padding:6px 10px;border-radius:4px;'
        f'border:1px solid #30363d;">'
        f'<div style="color:#8b949e;font-size:10px;">DATE RANGE</div>'
        f'<div style="color:#e6edf3;font-size:12px;">{html.escape(date_range)}</div>'
        f'</div>'
        f'</div>'
        # Category distribution
        f'<div style="margin-bottom:6px;">'
        f'<div style="color:#8b949e;font-size:11px;margin-bottom:3px;">CATEGORY DISTRIBUTION</div>'
        f'{cat_bars}'
        f'</div>'
        # Source tiers
        f'<div style="margin-bottom:6px;">'
        f'<div style="color:#8b949e;font-size:11px;margin-bottom:3px;">SOURCES</div>'
        f'{tier_html}'
        f'</div>'
        # Key themes
        f'<div>'
        f'<div style="color:#8b949e;font-size:11px;margin-bottom:3px;">KEY THEMES</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:4px;">{theme_tags}</div>'
        f'</div>'
        f'</div>'
    )


def render_global_summary(country_counts: dict[str, int], total: int) -> str:
    """Render global summary panel when no country is selected."""
    flagged = sum(country_counts.values())
    n_countries = len(country_counts)

    # Top countries
    top = sorted(country_counts.items(), key=lambda x: -x[1])[:6]
    top_html = " ".join(
        f'<span style="background:#21262d;color:#e6edf3;padding:2px 8px;'
        f'border-radius:3px;font-size:11px;border:1px solid #30363d;">'
        f'{html.escape(cc)}: {cnt}</span>'
        for cc, cnt in top
    )

    return (
        f'<div style="background:#161b22;border:1px solid #30363d;'
        f'border-radius:6px;padding:10px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;'
        f'margin-bottom:8px;">'
        f'<span style="color:#e6edf3;font-size:14px;font-weight:600;">'
        f'Global Overview</span>'
        f'<span style="background:#3fb950;color:#fff;padding:2px 8px;'
        f'border-radius:3px;font-size:10px;font-weight:600;">MONITORING</span>'
        f'</div>'
        f'<div style="display:flex;gap:12px;margin-bottom:8px;">'
        f'<div style="background:#0d1117;padding:6px 10px;border-radius:4px;'
        f'border:1px solid #30363d;">'
        f'<div style="color:#8b949e;font-size:10px;">TOTAL COLLECTED</div>'
        f'<div style="color:#e6edf3;font-size:16px;font-weight:700;">{total}</div>'
        f'</div>'
        f'<div style="background:#0d1117;padding:6px 10px;border-radius:4px;'
        f'border:1px solid #30363d;">'
        f'<div style="color:#8b949e;font-size:10px;">FLAGGED</div>'
        f'<div style="color:#f85149;font-size:16px;font-weight:700;">{flagged}</div>'
        f'</div>'
        f'<div style="background:#0d1117;padding:6px 10px;border-radius:4px;'
        f'border:1px solid #30363d;">'
        f'<div style="color:#8b949e;font-size:10px;">COUNTRIES</div>'
        f'<div style="color:#e6edf3;font-size:16px;font-weight:700;">{n_countries}</div>'
        f'</div>'
        f'</div>'
        f'<div>'
        f'<div style="color:#8b949e;font-size:11px;margin-bottom:3px;">TOP COUNTRIES</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:4px;">{top_html}</div>'
        f'</div>'
        f'<div style="color:#8b949e;font-size:11px;margin-top:8px;text-align:center;">'
        f'Use the country buttons below to drill down</div>'
        f'</div>'
    )


def render_news_cards(articles: list[Article], max_cards: int = 12) -> str:
    """Render horizontal scrollable news cards for the bottom feed."""
    if not articles:
        return (
            '<div style="color:#8b949e;text-align:center;padding:12px;">'
            'No articles match current filters.</div>'
        )

    cards = []
    for article in articles[:max_cards]:
        title = html.escape((article.title or "Untitled")[:80])
        source = html.escape(article.source_name or "Unknown")
        category = html.escape(
            (article.category or "other").replace("_", " ").title()
        )
        cat_color = _CATEGORY_COLORS.get(article.category or "", "#8b949e")
        conf = article.confidence or 0.0
        conf_color = "#f85149" if conf >= 0.8 else "#d29922" if conf >= 0.6 else "#8b949e"
        date_str = ""
        if article.published_at:
            # published_at may be str or datetime
            if hasattr(article.published_at, "strftime"):
                date_str = article.published_at.strftime("%Y-%m-%d")
            else:
                date_str = str(article.published_at)[:10]

        # Safe URL handling: only allow http/https, use data-attr (no inline JS interpolation)
        url_data_attr = ""
        if article.url and article.url.startswith(("http://", "https://")):
            safe_url = html.escape(article.url, quote=True)
            url_data_attr = (
                f'data-url="{safe_url}" '
                f'onclick="var u=this.dataset.url;if(/^https?:\\/\\//.test(u))window.open(u,\'_blank\')"'
            )

        cards.append(
            f'<div style="min-width:220px;max-width:260px;background:#161b22;'
            f'border:1px solid #30363d;border-radius:6px;padding:10px;'
            f'flex-shrink:0;display:flex;flex-direction:column;gap:4px;'
            f'{"cursor:pointer;" if url_data_attr else ""}" '
            f'{url_data_attr}>'
            f'<div style="color:#e6edf3;font-size:12px;font-weight:600;'
            f'line-height:1.3;display:-webkit-box;-webkit-line-clamp:3;'
            f'-webkit-box-orient:vertical;overflow:hidden;">{title}</div>'
            f'<div style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;">'
            f'<span style="background:{cat_color}22;color:{cat_color};'
            f'padding:1px 6px;border-radius:3px;font-size:10px;">{category}</span>'
            f'<span style="color:{conf_color};font-size:10px;">{conf:.0%}</span>'
            f'</div>'
            f'<div style="color:#8b949e;font-size:10px;margin-top:auto;">'
            f'{source} {("| " + date_str) if date_str else ""}</div>'
            f'</div>'
        )

    cards_html = "\n".join(cards)
    return (
        f'<div style="display:flex;gap:8px;overflow-x:auto;padding:4px 0;'
        f'scrollbar-width:thin;scrollbar-color:#30363d #0d1117;">'
        f'{cards_html}'
        f'</div>'
    )
