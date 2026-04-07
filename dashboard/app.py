"""AI Surveillance News Monitor — Streamlit dashboard entry point.

Wires together all dashboard components: global map, drill-down map,
news feed, article detail, live streams, webcams, and sidebar filters.

Run with:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path so absolute imports work when launched via
# ``streamlit run dashboard/app.py`` (Streamlit does not add the project root).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from dashboard.components.article_detail import render_article_detail
from dashboard.components.live_stream import render_live_stream
from dashboard.components.map_drilldown import (
    build_choropleth_data,
    build_region_data,
    get_country_center,
    render_choropleth_html,
    render_drilldown_html,
)
from dashboard.components.map_global import (
    COUNTRY_COORDS,
    DRILL_DOWN_COUNTRIES,
)
from dashboard.components.map_globe import build_globe_data, render_globe
from dashboard.components.webcams import render_webcam_grid
from dashboard.styles import load_dark_theme
from src.database import Database
from src.models import Article, VALID_CATEGORIES

logger = logging.getLogger(__name__)

_DB_PATH = str(Path(__file__).resolve().parent.parent / "data" / "monitor.db")


def _get_db() -> Database:
    """Return a per-session read-only Database connection.

    Previous versions used @st.cache_resource which shared one connection
    across all concurrent Streamlit sessions, risking thread-unsafe cursor
    operations. Read-only SQLite connections are cheap, so one per session
    (stored in session_state) is safe and avoids the threading hazard.
    """
    if "_db" not in st.session_state:
        st.session_state["_db"] = Database(_DB_PATH, read_only=True)
    return st.session_state["_db"]


# ------------------------------------------------------------------ #
#  Pure logic helpers (testable without Streamlit)                     #
# ------------------------------------------------------------------ #


def get_view_state(state: dict[str, Any]) -> str:
    """Return 'global' or 'drilldown' based on session state."""
    country = state.get("selected_country")
    if country and isinstance(country, str) and country.strip():
        return "drilldown"
    return "global"


def select_country(state: dict[str, Any], country_code: str) -> None:
    """Set the selected country and clear article selection.

    Mutates state in-place (designed for st.session_state compatibility).
    """
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
    """Return sorted country list with 'All' first.

    Builds display strings from available country_counts keys.
    Uses COUNTRY_COORDS for human-readable names when available.
    """
    if coords is None:
        coords = COUNTRY_COORDS
    options = ["All"]
    for cc in sorted(country_counts):
        name = coords.get(cc, {}).get("name", cc)
        options.append(f"{cc} — {name}")
    return options


def parse_country_option(option: str) -> str:
    """Extract country code from display string like 'IN — India'.

    Returns 'All' unchanged.
    """
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
    """Convert sidebar filter selections to DB query kwargs.

    'All' values are excluded from the params dict.
    Dates are converted to ISO strings.
    """
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


# ------------------------------------------------------------------ #
#  Streamlit app (only runs when executed as main script)             #
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
            min_value=0.0,
            max_value=1.0,
            value=0.6,
            step=0.05,
        )

        # Date range filter (rendered before Country so dates feed into
        # the country dropdown population query — R4 completeness)
        st.markdown("**Date Range**")
        date_from_val = st.date_input("From", value=None, key="date_from")
        date_to_val = st.date_input("To", value=None, key="date_to")

        # Build datetime objects once — used for both the country-counts
        # query and the final filter_params (CC4-M6: no double construction).
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

        # Country filter — populated using all active sidebar filters so
        # only countries with visible articles appear (R4 fix)
        cat_for_counts = category if category != "All" else None
        country_counts = db.get_country_counts(
            min_confidence=min_confidence,
            category=cat_for_counts,
            date_from=date_from_dt.isoformat() if date_from_dt else None,
            date_to=date_to_dt.isoformat() if date_to_dt else None,
        )
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


def format_article_meta(article: Article) -> str:
    """Build a short metadata line for an article button caption.

    Pure function — no Streamlit dependency.
    """
    parts: list[str] = []
    if article.country_name:
        parts.append(article.country_name)
    if article.source_name:
        parts.append(article.source_name)
    if article.confidence is not None:
        parts.append(f"conf {article.confidence:.2f}")
    return " | ".join(parts) if parts else ""


def _render_feed_and_detail(
    db: Database,
    articles: list,
    key_prefix: str,
) -> None:
    """Render the news feed + article detail column pair.

    Shared between global and drill-down views.
    Each article is an interactive st.button (M21 fix: removed duplicate
    HTML cards that weren't clickable).
    """
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
        selected_id = st.session_state.get("selected_article_id")
        # Only show detail if the selected article is in the current filtered set,
        # preventing stale detail display after filter changes.
        current_ids = {a.id for a in articles}
        if selected_id and selected_id in current_ids:
            detail_article = db.get_article(selected_id)
        else:
            detail_article = None
            if selected_id:
                clear_article(st.session_state)
        # render_article_detail escapes all user text via html.escape()
        detail_html = render_article_detail(detail_article)
        st.markdown(detail_html, unsafe_allow_html=True)


def _render_global_view(db: Database, filter_params: dict[str, Any]) -> None:
    """Render the global overview: map + news feed + article detail."""
    st.title("AI Surveillance & Censorship Monitor")

    # Metrics row — exclude country_code from get_country_counts (R3: it
    # doesn't accept that param; filter_params may contain it from sidebar)
    total = db.count_articles()
    cc_params = {k: v for k, v in filter_params.items() if k != "country_code"}
    country_counts = db.get_country_counts(**cc_params)
    flagged_count = sum(country_counts.values())

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Total Collected", total)
    col_m2.metric("Flagged", flagged_count)
    col_m3.metric("Countries", len(country_counts))

    # Globe view (3D rotating globe with country polygons)
    # render_globe uses declare_component for bidirectional communication;
    # clicking a focus country returns its ISO-2 code.
    globe_data = build_globe_data(country_counts)
    if globe_data:
        clicked_country = render_globe(globe_data, height=550, key="globe")
        if clicked_country and clicked_country in DRILL_DOWN_COUNTRIES:
            select_country(st.session_state, clicked_country)
            st.rerun()
    else:
        st.info("No data to display on the map yet.")

    # Drill-down buttons
    st.markdown("##### Drill-Down Countries")
    drill_cols = st.columns(len(DRILL_DOWN_COUNTRIES))
    for i, cc in enumerate(DRILL_DOWN_COUNTRIES):
        name = COUNTRY_COORDS.get(cc, {}).get("name", cc)
        if drill_cols[i].button(name, key=f"drill_{cc}"):
            select_country(st.session_state, cc)
            st.rerun()

    st.markdown("---")

    articles = db.get_flagged_articles(**filter_params, limit=20)
    _render_feed_and_detail(db, articles, key_prefix="art")


def _render_drilldown_view(
    db: Database,
    country_code: str,
    filter_params: dict[str, Any],
) -> None:
    """Render the drill-down view for a specific country."""
    country_name = COUNTRY_COORDS.get(country_code, {}).get("name", country_code)

    # Back button
    if st.button("< Back to Global View"):
        clear_country(st.session_state)
        st.rerun()

    st.title(f"Drill-Down: {country_name}")

    # Override filter with selected country
    drill_params = {**filter_params, "country_code": country_code}
    articles = db.get_flagged_articles(**drill_params, limit=20)

    # Country-specific metrics (M22 fix: distinct from global view)
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Flagged Articles", len(articles))
    category_set = {a.category for a in articles if a.category}
    col_m2.metric("Categories", len(category_set))
    conf_values = [a.confidence for a in articles if a.confidence is not None]
    avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0
    col_m3.metric("Avg Confidence", f"{avg_conf:.2f}")

    # Top row: regional map + live stream
    col_map, col_stream = st.columns([1, 1])

    with col_map:
        st.subheader("Regional Map")
        center = get_country_center(country_code)
        if center:
            # Choropleth with admin-1 region fills (fallback to scatter dots)
            admin1_counts = build_choropleth_data(articles, country_code)
            choropleth_html = render_choropleth_html(
                admin1_counts, country_code, center,
            )
            if choropleth_html:
                st.components.v1.html(
                    choropleth_html, height=400, scrolling=False,
                )
            else:
                region_data = build_region_data(articles, country_code)
                if region_data:
                    drill_html = render_drilldown_html(region_data, center)
                    st.components.v1.html(
                        drill_html, height=400, scrolling=False,
                    )
                else:
                    st.info("No region-level article data to display on the map.")
        else:
            st.info("No regional map available.")

    with col_stream:
        st.subheader("Live Stream")
        # render_live_stream escapes all user text via html.escape()
        stream_html = render_live_stream(country_code)
        st.markdown(stream_html, unsafe_allow_html=True)

    # Webcams — render_webcam_grid escapes all user text via html.escape()
    st.subheader("City Webcams")
    webcam_html = render_webcam_grid(country_code)
    st.markdown(webcam_html, unsafe_allow_html=True)

    st.markdown("---")

    _render_feed_and_detail(db, articles, key_prefix="drill_art")


def main() -> None:
    """Main dashboard entry point."""
    st.set_page_config(
        page_title="AI Surveillance Monitor",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    load_dark_theme()

    # Auto-refresh every 60s to pick up newly ingested articles
    st_autorefresh(interval=60_000, key="auto_refresh")

    _init_session_state()

    # Use cached read-only DB connection (shared across reruns)
    try:
        db = _get_db()
        filter_params = _render_sidebar(db)

        view = get_view_state(st.session_state)
        if view == "drilldown":
            _render_drilldown_view(
                db,
                st.session_state.selected_country,
                filter_params,
            )
        else:
            _render_global_view(db, filter_params)
    except Exception:
        logger.exception("Dashboard error")
        if os.environ.get("STREAMLIT_DEBUG"):
            raise
        st.error("Dashboard error. Please check logs for details.")


if __name__ == "__main__":
    main()
