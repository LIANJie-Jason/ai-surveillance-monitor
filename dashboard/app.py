"""AI Surveillance News Monitor — Single-window command center dashboard.

Wires together all dashboard components: globe (always visible), analysis
panel, live streams, webcams, and news feed in a tight WorldMonitor-style
layout.

Run with:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import streamlit.components.v1 as st_html_component
from streamlit_autorefresh import st_autorefresh

from dashboard.components.analysis import (
    render_country_analysis,
    render_global_summary,
    render_news_cards,
)
from dashboard.components.live_stream import (
    load_streams,
    render_live_stream,
    set_resolved_streams,
)
from dashboard.components.map_global import (
    COUNTRY_COORDS,
    DRILL_DOWN_COUNTRIES,
)
from dashboard.components.map_globe import build_globe_data, render_globe
from dashboard.components.webcams import (
    load_webcams,
    render_webcam_grid,
    set_resolved_webcams,
)
from dashboard.styles import load_dark_theme
from src.database import Database
from src.models import Article, VALID_CATEGORIES

logger = logging.getLogger(__name__)

_DB_PATH = str(Path(__file__).resolve().parent.parent / "data" / "monitor.db")


def _get_db() -> Database:
    """Return a per-session read-only Database connection."""
    if "_db" not in st.session_state:
        st.session_state["_db"] = Database(_DB_PATH, read_only=True)
    return st.session_state["_db"]


# ------------------------------------------------------------------ #
#  Pure logic helpers                                                  #
# ------------------------------------------------------------------ #


def get_view_state(state: dict[str, Any]) -> str:
    """Return 'global' or 'drilldown' based on session state."""
    country = state.get("selected_country")
    if country and isinstance(country, str) and country.strip():
        return "drilldown"
    return "global"


def select_country(state: dict[str, Any], country_code: str) -> None:
    """Set the selected country and clear article selection."""
    state["selected_country"] = country_code
    state["selected_article_id"] = None


def clear_country(state: dict[str, Any]) -> None:
    """Clear country and article selection (back to global)."""
    state["selected_country"] = None
    state["selected_article_id"] = None


def select_article(state: dict[str, Any], article_id: str) -> None:
    """Set the selected article ID."""
    state["selected_article_id"] = article_id


def clear_article(state: dict[str, Any]) -> None:
    """Clear the selected article (stay in same view)."""
    state["selected_article_id"] = None


def get_categories() -> list[str]:
    """Return sorted category list with 'All' first."""
    return ["All"] + sorted(VALID_CATEGORIES)


def get_country_options(
    country_counts: dict[str, int],
    coords: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Return sorted country list with 'All' first."""
    if coords is None:
        coords = COUNTRY_COORDS
    options = ["All"]
    for cc in sorted(country_counts):
        name = coords.get(cc, {}).get("name", cc)
        options.append(f"{cc} — {name}")
    return options


def parse_country_option(option: str) -> str:
    """Extract country code from display string like 'IN — India'."""
    if option == "All":
        return "All"
    return option.split(" — ")[0]


def get_drilldown_countries() -> tuple[str, ...]:
    """Return the tuple of drill-down country codes."""
    return DRILL_DOWN_COUNTRIES


def build_filter_params(
    country: str,
    category: str,
    min_confidence: float,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, Any]:
    """Convert sidebar filter selections to DB query kwargs."""
    params: dict[str, Any] = {"min_confidence": min_confidence}
    if country and country != "All":
        params["country_code"] = country
    if category and category != "All":
        params["category"] = category
    if date_from is not None:
        params["date_from"] = date_from.isoformat()
    if date_to is not None:
        params["date_to"] = date_to.isoformat()
    return params


def format_article_meta(article: Article) -> str:
    """Build a short metadata line for an article."""
    parts: list[str] = []
    if article.country_name:
        parts.append(article.country_name)
    if article.source_name:
        parts.append(article.source_name)
    if article.confidence is not None:
        parts.append(f"conf {article.confidence:.2f}")
    return " | ".join(parts) if parts else ""


# ------------------------------------------------------------------ #
#  Stream resolver (once per process)                                  #
# ------------------------------------------------------------------ #

_streams_resolved = False
_streams_resolving = False
_streams_lock = threading.Lock()


def _resolve_streams_once() -> None:
    """Resolve YouTube channel IDs to live video IDs once per process.

    Only sets the resolved flag on success — failures allow retry on
    the next Streamlit rerun. Uses ``_streams_resolving`` to prevent
    concurrent threads from duplicating the work.
    """
    global _streams_resolved, _streams_resolving
    with _streams_lock:
        if _streams_resolved or _streams_resolving:
            return
        _streams_resolving = True

    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        logger.info("[stream-resolver] YOUTUBE_API_KEY not set — skipping")
        with _streams_lock:
            _streams_resolved = True
            _streams_resolving = False
        return

    from src.stream_resolver import resolve_streams, resolve_webcams

    logger.info("[stream-resolver] Resolving YouTube streams (API key configured)")

    streams_raw = load_streams()
    webcams_raw = load_webcams()

    try:
        resolved_streams = resolve_streams(streams_raw, api_key)
        resolved_webcams = resolve_webcams(webcams_raw, api_key)

        s_count = sum(
            1 for sec in ("streams", "fallbacks")
            for s in resolved_streams.get(sec, {}).values()
            if "/embed/live_stream" not in s.get("embed_url", "")
            and s.get("embed_url", "")
        )
        w_count = sum(
            1 for cams in resolved_webcams.get("webcams", {}).values()
            for c in cams
            if c.get("embed_url", "")
        )
        logger.info("[stream-resolver] Done: %d streams, %d webcams resolved", s_count, w_count)

        set_resolved_streams(resolved_streams)
        set_resolved_webcams(resolved_webcams)

        with _streams_lock:
            _streams_resolved = True
    except Exception as exc:
        logger.exception("Stream resolution failed — will retry on next rerun: %s", exc)
    finally:
        with _streams_lock:
            _streams_resolving = False


# ------------------------------------------------------------------ #
#  Streamlit app                                                       #
# ------------------------------------------------------------------ #


def _init_session_state() -> None:
    """Initialize session state keys if missing."""
    if "selected_country" not in st.session_state:
        st.session_state.selected_country = None
    if "selected_article_id" not in st.session_state:
        st.session_state.selected_article_id = None


def _render_sidebar(db: Database) -> dict[str, Any]:
    """Render sidebar filters and return filter params dict."""
    with st.sidebar:
        st.header("Filters")

        categories = get_categories()
        category = st.selectbox("Category", categories, index=0)

        min_confidence = st.slider(
            "Min Confidence",
            min_value=0.0, max_value=1.0, value=0.6, step=0.05,
        )

        st.markdown("**Date Range**")
        date_from_val = st.date_input("From", value=None, key="date_from")
        date_to_val = st.date_input("To", value=None, key="date_to")

        date_from_dt: datetime | None = (
            datetime(date_from_val.year, date_from_val.month, date_from_val.day,
                     tzinfo=timezone.utc)
            if isinstance(date_from_val, date) else None
        )
        date_to_dt: datetime | None = (
            datetime(date_to_val.year, date_to_val.month, date_to_val.day,
                     hour=23, minute=59, second=59, tzinfo=timezone.utc)
            if isinstance(date_to_val, date) else None
        )

        cat_for_counts = category if category != "All" else None
        all_counts = db.get_country_counts(
            min_confidence=min_confidence,
            category=cat_for_counts,
            date_from=date_from_dt.isoformat() if date_from_dt else None,
            date_to=date_to_dt.isoformat() if date_to_dt else None,
        )
        # Filter to focus countries only
        country_counts = {
            cc: cnt for cc, cnt in all_counts.items()
            if cc in DRILL_DOWN_COUNTRIES
        }
        country_options = get_country_options(country_counts)
        country_raw = st.selectbox("Country", country_options, index=0)
        country = parse_country_option(country_raw)

        st.markdown("---")
        st.caption("AI Surveillance News Monitor")

    return build_filter_params(
        country=country,
        category=category,
        min_confidence=min_confidence,
        date_from=date_from_dt,
        date_to=date_to_dt,
    )


def _render_title_bar() -> None:
    """Render the compact title bar."""
    st.markdown(
        '<div style="display:flex;align-items:center;justify-content:space-between;'
        'padding:4px 0;border-bottom:1px solid #30363d;margin-bottom:6px;">'
        '<span style="color:#e6edf3;font-size:16px;font-weight:700;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
        'AI Surveillance &amp; Censorship Monitor</span>'
        '<span style="background:#f85149;color:#fff;padding:2px 8px;'
        'border-radius:3px;font-size:10px;font-weight:600;">LIVE</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_feed_and_detail(
    db: Database,
    articles: list,
    key_prefix: str,
) -> None:
    """Render the news feed + article detail column pair."""
    col_feed, col_detail = st.columns([1, 1])

    with col_feed:
        st.subheader(f"News Feed ({len(articles)} articles)")
        if not articles:
            st.info("No articles found.")
        for article in articles[:20]:
            label = (article.title or "Untitled")[:80]
            if st.button(label, key=f"{key_prefix}_{article.id}"):
                select_article(st.session_state, article.id)
                st.rerun()
            meta = format_article_meta(article)
            if meta:
                st.caption(meta)

    with col_detail:
        st.subheader("Article Detail")
        from dashboard.components.article_detail import render_article_detail
        selected_id = st.session_state.get("selected_article_id")
        current_ids = {a.id for a in articles}
        if selected_id and selected_id in current_ids:
            detail_article = db.get_article(selected_id)
        else:
            detail_article = None
            if selected_id:
                clear_article(st.session_state)
        detail_html = render_article_detail(detail_article)
        if detail_article and detail_article.url:
            # Use st.components.v1.html for iframe embedding
            wrapped = (
                f'<body style="margin:0;padding:0;background:#0d1117;'
                f'color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'
                f'\'Segoe UI\',sans-serif;">{detail_html}</body>'
            )
            st_html_component.html(wrapped, height=750, scrolling=True)
        else:
            st.markdown(detail_html, unsafe_allow_html=True)


def main() -> None:
    """Main dashboard entry point — single-window command center."""
    st.set_page_config(
        page_title="AI Surveillance Monitor",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    load_dark_theme()

    st_autorefresh(interval=60_000, key="auto_refresh")

    _init_session_state()
    _resolve_streams_once()

    try:
        db = _get_db()
        filter_params = _render_sidebar(db)

        # ── Title bar ────────────────────────────────────────────────
        _render_title_bar()

        # ── Determine state ──────────────────────────────────────────
        selected_country = st.session_state.get("selected_country")
        country_name = COUNTRY_COORDS.get(selected_country or "", {}).get("name", "")

        # ── Build globe data (4 focus countries only) ────────────────
        cc_params = {k: v for k, v in filter_params.items() if k != "country_code"}
        all_counts = db.get_country_counts(**cc_params)
        # Filter to focus countries only
        country_counts = {
            cc: cnt for cc, cnt in all_counts.items()
            if cc in DRILL_DOWN_COUNTRIES
        }
        total = sum(country_counts.values())
        globe_data = build_globe_data(country_counts)

        # ── Main layout: Globe (left) + Panels (right) ──────────────
        col_globe, col_panels = st.columns([4, 6])

        with col_globe:
            if globe_data:
                render_globe(
                    globe_data,
                    height=580,
                    key="globe",
                    selected_country=selected_country,
                )
            else:
                st.info("No data to display on the map yet.")

        with col_panels:
            if selected_country and selected_country in DRILL_DOWN_COUNTRIES:
                # ── COUNTRY DRILL-DOWN VIEW ──────────────────────────
                drill_params = {**filter_params, "country_code": selected_country}
                articles = db.get_flagged_articles(**drill_params, limit=50)

                # Back button
                if st.button("< Back to Global View", key="back_btn"):
                    clear_country(st.session_state)
                    st.rerun()

                # Analysis panel (live from DB)
                analysis_html = render_country_analysis(articles, country_name)
                st.markdown(analysis_html, unsafe_allow_html=True)

                # Live news stream
                st.markdown(
                    '<div style="color:#8b949e;font-size:11px;margin:4px 0 2px;">'
                    'LIVE NEWS</div>',
                    unsafe_allow_html=True,
                )
                stream_html = render_live_stream(selected_country)
                st_html_component.html(stream_html, height=460, scrolling=False)

                # Webcams (compact)
                st.markdown(
                    '<div style="color:#8b949e;font-size:11px;margin:4px 0 2px;">'
                    'CITY FEEDS</div>',
                    unsafe_allow_html=True,
                )
                webcam_html = render_webcam_grid(
                    selected_country, cam_height=140,
                )
                st_html_component.html(webcam_html, height=340, scrolling=False)

            else:
                # ── GLOBAL VIEW ──────────────────────────────────────
                global_params = {
                    k: v for k, v in filter_params.items()
                    if k != "country_code"
                }
                global_params["country_codes"] = list(DRILL_DOWN_COUNTRIES)
                articles = db.get_flagged_articles(**global_params, limit=50)

                # Global summary
                summary_html = render_global_summary(country_counts, total)
                st.markdown(summary_html, unsafe_allow_html=True)

                # Drill-down country buttons
                st.markdown(
                    '<div style="color:#8b949e;font-size:11px;margin:6px 0 3px;">'
                    'DRILL-DOWN COUNTRIES</div>',
                    unsafe_allow_html=True,
                )
                drill_cols = st.columns(len(DRILL_DOWN_COUNTRIES))
                for i, cc in enumerate(DRILL_DOWN_COUNTRIES):
                    name = COUNTRY_COORDS.get(cc, {}).get("name", cc)
                    if drill_cols[i].button(name, key=f"drill_{cc}"):
                        select_country(st.session_state, cc)
                        st.rerun()

        # ── Bottom: News feed cards ──────────────────────────────────
        st.markdown(
            '<div style="border-top:1px solid #30363d;margin-top:4px;'
            'padding-top:4px;">'
            '<span style="color:#8b949e;font-size:11px;">LATEST ARTICLES</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        # Reuse already-fetched articles (no duplicate DB query)
        feed_articles = articles[:20]
        cards_html = render_news_cards(feed_articles)
        st.markdown(cards_html, unsafe_allow_html=True)

        # ── Expandable detail section ────────────────────────────────
        with st.expander("Article Detail & Full Feed", expanded=False):
            _render_feed_and_detail(db, feed_articles, key_prefix="art")

    except Exception:
        logger.exception("Dashboard error")
        if os.environ.get("STREAMLIT_DEBUG"):
            raise
        st.error("Dashboard error. Please check logs for details.")


if __name__ == "__main__":
    main()
