# AI Surveillance & Censorship News Monitor

A prototype that continuously monitors online news sources and screens for stories about government surveillance and censorship behaviors. Built as a demonstration tool for an NSF grant.

## Overview

This tool ingests RSS feeds from 64 news sources worldwide (60 currently active), uses LLM-based classification to identify articles about surveillance and censorship, and presents the results in a real-time command-center dashboard. It classifies articles into 8 categories of surveillance behavior. The 79 seed articles span 13 countries, with deep drill-down views for 4 focus countries (India, Malaysia, Nigeria, South Africa).

The reference architecture draws on [worldmonitor](https://github.com/koala73/worldmonitor) (RSS-based global news monitoring with AI filtering).

## Architecture

The system is a two-process pipeline sharing a single SQLite database:

```
RSS Feeds (64 sources, 60 active)
        |
        v
+-------------------+       +----------------+
| Ingestion Worker  | ----> |   SQLite DB    |
| src/ingestion.py  |       |  (WAL mode)    |
+-------------------+       +----------------+
                                    |
                                    v  (read-only)
                            +------------------+
                            | Streamlit        |
                            | Dashboard        |
                            | dashboard/app.py |
                            +------------------+
                                    |
                    +---------------+---------------+
                    |       |       |       |       |
                 3D Globe Drill-  News   Live   Webcam
                         down    Feed  Streams  Grid
                         Maps
```

1. **Ingestion worker** (`src/ingestion.py`) -- fetches RSS feeds via feedparser, deduplicates by URL hash, classifies articles via LLM, and stores results to SQLite. Rate-limited with per-feed (100) and per-run (~500) article caps. Uses `llm_provider="failed"` sentinel to prevent infinite re-classification loops.
2. **Streamlit dashboard** (`dashboard/app.py`) -- reads the same SQLite database in read-only mode and renders a dark command-center web dashboard with maps, news feed, and drill-down views. Auto-refreshes every 60 seconds.

## Features

- **LLM classification with fallback** -- GPT-4.1-mini is the primary model; Claude Haiku 4.5 serves as automatic fallback. Articles are classified with confidence scores across 8 categories.
- **8 surveillance/censorship categories** -- `surveillance`, `censorship`, `facial_recognition`, `internet_shutdown`, `data_collection`, `social_media_control`, `digital_rights`, `other`.
- **URL deduplication** -- SHA-256 hash of canonicalized URLs (strips UTM parameters and trailing slashes) prevents duplicate ingestion.
- **4-tier source taxonomy** -- sources are ranked by reliability (see [Source Tiers](#source-tiers) below).
- **64 RSS feeds** across all 4 tiers (60 currently active; 4 disabled due to upstream issues).
- **79 seed articles** -- all real, web-search-verified articles across 13 countries and 7 categories, enabling a fully functional demo without API keys.
- **3D rotating globe** -- deck.gl 9.1.8 GlobeView with auto-rotation, country polygon boundaries, and focus country highlighting (IN, MY, NG, ZA). Pauses on user interaction, resumes after 3 seconds idle, stops after 60 seconds of auto-rotation. Implemented as a bidirectional Streamlit component.
- **Choropleth drill-down maps** -- country-level maps with admin-1 (state/province) boundary fills. Regions with matched articles are highlighted as filled polygons. GeoJSON boundaries from Natural Earth (public domain). Falls back to scatter dots if GeoJSON is unavailable.
- **Geo resolver** -- 130 city/alias-to-admin-1 mappings across 4 drill-down countries for accurate choropleth rendering.
- **News feed with filtering** -- filter by category, country, confidence score, and date range.
- **Article detail panel** -- full article view with SSRF protection (blocks requests to private/reserved IP ranges via `src/url_utils.py`).
- **Live streams** -- 8 YouTube live streams (4 primary + 4 fallback). Channel IDs are resolved to live video IDs at dashboard startup via the YouTube Data API v3. Falls back to SkylineWebcams links where available.
- **Webcams** -- 12 city webcam slots across 4 countries. YouTube channel IDs are resolved dynamically; unresolved slots fall back to a YouTube search for ``<city> live webcam``, then to a SkylineWebcams link (Cape Town, KL, Durban), then to a placeholder.
- **Security hardening** -- Unicode bidi-override stripping on LLM outputs, HTML escaping throughout, parameterized SQL queries, HTTPS-only embeds with private-IP blocking, `postMessage` source validation in iframe components.
- **SQLite with WAL mode** -- busy_timeout and read-only mode for the dashboard enable concurrent read/write without locking.
- **ISO 3166-1 alpha-2 country codes** throughout.

## Quick Start

### Prerequisites

- Python 3.11+
- For live ingestion: **both** an OpenAI API key and an Anthropic API key (the ingestion worker requires both; it exits if either is missing)
- For live stream/webcam embeds: a YouTube Data API v3 key (free from Google Cloud Console; dashboard works without it but streams show as placeholders)

### Install

```bash
pip install -r requirements.txt
```

### Demo mode (no API keys needed)

```bash
python scripts/seed_data.py        # Creates DB, loads feeds, and seeds 79 verified articles
streamlit run dashboard/app.py     # Launch the dashboard
```

`seed_data.py` calls `init_database()` internally, so there is no need to run `init_db.py` separately.

### Live ingestion (requires API keys)

```bash
cp .env.example .env
# Edit .env and fill in keys:
#   OPENAI_API_KEY=sk-...        (required for ingestion)
#   ANTHROPIC_API_KEY=sk-ant-... (required for ingestion)
#   YOUTUBE_API_KEY=AIza...      (optional; enables live stream embeds)

# Single pass
python scripts/run_ingestion.py --once

# Continuous monitoring, every 30 minutes (default)
python scripts/run_ingestion.py

# Custom interval (10 min) with debug logging
python scripts/run_ingestion.py --interval 600 --log-level DEBUG
```

`run_ingestion.py` also calls `init_database()` internally, so the DB is created automatically on first run.

### Clean re-initialization

To wipe stale data and re-seed from scratch:

```bash
python scripts/init_db.py --clean   # Drop articles + feeds tables, reload feeds
python scripts/seed_data.py         # Re-seed verified articles
```

## Configuration

All configuration lives in `config/`:

| File | Description |
|------|-------------|
| `feeds.yaml` | 64 RSS feed URLs with source tier assignments (1--4); 60 active |
| `regions.yaml` | Drill-down regions for IN, MY, NG, ZA (38 cities with lat/lng coordinates) |
| `streams.yaml` | 8 live video stream URLs (4 primary + 4 fallback) |
| `webcams.yaml` | 12 webcam feed URLs using channel-based YouTube embeds |

## Project Structure

```
src/
  models.py            # Article/Feed dataclasses, URL canonicalization, VALID_CATEGORIES
  database.py          # SQLite layer (upsert, queries, read_only mode, busy_timeout)
  llm_client.py        # OpenAI primary, Anthropic fallback; returns (text, provider)
  classifier.py        # LLM-based surveillance/censorship classification with bidi stripping
  summarizer.py        # LLM-based article summarization
  url_utils.py         # Shared SSRF/private-host validation (used by models, article_detail, _utils)
  stream_resolver.py   # YouTube Data API v3 — resolves channel IDs to live video IDs at startup
  ingestion.py         # RSS fetch worker with schedule loop and article caps

scripts/
  init_db.py           # Create DB + load feeds from config (supports --clean flag)
  seed_data.py         # Load verified seed articles into DB; returns (loaded, total, already_exists)
  run_ingestion.py     # CLI entry point for live RSS ingestion (single-pass or continuous)
  verify_feeds.py      # Verify RSS feed URLs are reachable
  prepare_geojson.py   # Download + simplify Natural Earth GeoJSON for maps

config/
  feeds.yaml           # 64 RSS feed URLs with source tiers (60 active)
  regions.yaml         # Drill-down regions for IN, MY, NG, ZA (38 cities + lat/lng)
  streams.yaml         # Live video stream URLs (4 primary + 4 fallback)
  webcams.yaml         # Webcam feed URLs (12 channel-based YouTube embeds)

dashboard/
  app.py               # Main Streamlit app entry point (global view + drill-down view)
  components/
    map_global.py      # deck.gl flat scatter map (legacy, used for data building + constants)
    map_globe.py       # 3D rotating globe (deck.gl 9.1.8 GlobeView + GeoJsonLayer)
    map_drilldown.py   # Regional map: choropleth (admin-1 fills) with scatter fallback
    geo_resolver.py    # Maps city/region names to admin-1 GeoJSON boundary names (130 aliases)
    _utils.py          # Shared utilities (safe_json_for_script, safe_embed_url)
    news_feed.py       # Article list with filtering (legacy, retained for compatibility)
    article_detail.py  # Single article detail view (with SSRF protection)
    live_stream.py     # Embedded video streams (HTTPS-only, URL-validated)
    webcams.py         # Webcam grid (HTTPS-only, URL-validated)
  styles/
    dark_theme.css     # Dark command-center theme (XSS-safe CSS injection)
  static/
    deck_map.html          # deck.gl flat scatter map template (legacy)
    deck_globe.html        # deck.gl 3D globe template (GlobeView + auto-rotation)
    deck_choropleth.html   # deck.gl choropleth template (admin-1 region fills)
    globe_component/
      index.html           # Streamlit bidirectional component for interactive 3D globe
    geojson/               # Natural Earth boundary data (public domain)
      countries_110m.geojson   # World country polygons (~257KB)
      admin1_IN.geojson        # India states (~184KB)
      admin1_MY.geojson        # Malaysia states (~31KB)
      admin1_NG.geojson        # Nigeria states (~65KB)
      admin1_ZA.geojson        # South Africa provinces (~51KB)

data/
  seed_articles.json   # 79 web-verified seed articles (13 countries, 7 categories)
  monitor.db           # SQLite database (gitignored)

tests/                 # 24 test files, 610 tests
```

## Source Tiers

The 64 RSS feeds are organized into a 4-tier reliability taxonomy (defined in the header of `config/feeds.yaml`):

| Tier | Type | Examples | Count |
|------|------|----------|-------|
| 1 | Wire services | Reuters, AP, AFP | 3 |
| 2 | Major international outlets | BBC, Guardian, NYT, Al Jazeera, France 24, CNN, Washington Post, NPR, Bloomberg, Deutsche Welle | 11 |
| 3 | Specialty / digital rights / cybersecurity | HRW, Amnesty, Freedom House, CPJ, RSF, Access Now, ARTICLE 19, EFF, TechCrunch, The Record, Citizen Lab | 26 |
| 4 | Regional sources | Drill-down country sources (IN, MY, NG, ZA) + non-English international | 24 |

## LLM Classification Pipeline

1. The ingestion worker fetches new articles from RSS feeds (up to 100 per feed; processing stops after ~500 articles per run, checked between feeds).
2. Each article URL is canonicalized (UTM parameters and trailing slashes stripped) and hashed with SHA-256 for deduplication.
3. New articles are sent to the classifier, which prompts the LLM to determine whether the article concerns surveillance or censorship, assign a category from the 8 valid categories, identify the relevant country (ISO 3166-1 alpha-2), and return a confidence score. Unicode bidi-override characters are stripped from LLM-generated fields.
4. The LLM client tries OpenAI (GPT-4.1-mini) first; if that fails, it falls back to Anthropic (Claude Haiku 4.5). The `LLMClient.complete()` method returns a `(text, provider)` tuple. Non-retriable errors (auth, bad request) propagate immediately; retriable errors (connection, timeout, rate limit) trigger the fallback.
5. Classification failures produce `llm_provider="failed"` records, preventing infinite re-classification loops on subsequent ingestion runs.
6. Classified articles are stored in SQLite. The summarizer generates a brief summary for each article.

## Dashboard Views

The dashboard has two view modes, toggled via session state (no tab widget):

### Global View

| Component | File | Description |
|-----------|------|-------------|
| 3D Globe | `map_globe.py` | deck.gl GlobeView with auto-rotation, country polygons, focus country highlighting. Click a country to drill down. |
| Metrics | `app.py` | Total articles, countries covered, category breakdown |
| News Feed | `app.py` | Filterable article list rendered as Streamlit buttons (category, country, confidence, date range) |

### Drill-Down View (per country)

| Component | File | Description |
|-----------|------|-------------|
| Choropleth Map | `map_drilldown.py` | Admin-1 region fills (states/provinces) with article count heatmap. Falls back to scatter dots. |
| Geo Resolver | `geo_resolver.py` | Maps city/alias names to admin-1 boundary names in GeoJSON (130 aliases across 4 countries) |
| Live Stream | `live_stream.py` | Embedded YouTube live news stream (primary + fallback per country) |
| Webcams | `webcams.py` | City webcam grid (channel-based YouTube embeds) |
| Article Detail | `article_detail.py` | Full article view with SSRF protection against private IPs |

The dashboard uses a dark command-center theme (`dashboard/styles/dark_theme.css`) and auto-refreshes every 60 seconds via `streamlit-autorefresh`.

## Seed Data

The 79 seed articles in `data/seed_articles.json` are all real, web-search-verified stories. They span 13 countries across 7 surveillance/censorship categories:

| Country | Code | Articles |
|---------|------|----------|
| India | IN | 20 |
| Malaysia | MY | 15 |
| South Africa | ZA | 12 |
| Nigeria | NG | 10 |
| China | CN | 6 |
| Russia | RU | 4 |
| Israel | IL | 3 |
| Ethiopia | ET | 2 |
| Myanmar | MM | 2 |
| Turkey | TR | 2 |
| Iran | IR | 1 |
| Kenya | KE | 1 |
| Serbia | RS | 1 |

Seed articles are loaded with `llm_provider="seed"` and `is_surveillance=True`. Source tier distribution: 1 tier-1, 7 tier-2, 44 tier-3, 27 tier-4.

The seed database enables a fully functional demo dashboard without any API keys.

## Testing

```bash
# Run all tests (610 tests across 24 test files)
python -m pytest tests/ -q

# Run a specific test file
python -m pytest tests/test_scripts.py -v
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Dashboard | Streamlit, streamlit-autorefresh |
| RSS parsing | feedparser |
| LLM providers | openai (GPT-4.1-mini), anthropic (Claude Haiku 4.5) |
| Maps | deck.gl 9.1.8 (embedded HTML/JS), Natural Earth GeoJSON |
| Database | SQLite (stdlib, WAL mode) |
| HTTP | requests |
| Configuration | PyYAML, python-dotenv |
| Testing | pytest |

## Security

- **SSRF protection** -- `src/url_utils.py` validates URLs before fetching, blocking private and reserved IP ranges. Used by article detail view and embed URL validation.
- **Parameterized SQL queries** throughout the database layer to prevent injection.
- **HTML escaping** in all dashboard rendering to prevent XSS.
- **Unicode bidi stripping** -- `classifier.py` strips U+202A--U+202E and U+2066--U+2069 from LLM-generated fields (country names, regions) to prevent log spoofing and display manipulation.
- **HTTPS-only embeds** -- `safe_embed_url()` rejects non-HTTPS schemes and private hostnames for all iframe sources.
- **postMessage validation** -- globe component validates `event.source === window.parent` for iframe communication security.
- **CSS injection prevention** -- `styles/__init__.py` rejects CSS containing `</style>` variants before injecting into Streamlit.
- **Error message sanitization** -- LLM client error messages strip raw exception details to prevent information leakage.
- **Circuit breaker** -- `llm_provider="failed"` sentinel prevents infinite re-classification loops.

## Design Decisions

- **URL deduplication via SHA-256** -- `Article._canonicalize_url()` normalizes URLs before hashing, preventing duplicate ingestion of the same article from different feed entries.
- **LLM fallback chain** -- OpenAI is preferred for speed and cost; Anthropic provides resilience if OpenAI is unavailable. Non-retriable errors propagate immediately.
- **SQLite with WAL mode** -- enables concurrent reads from the dashboard while the ingestion worker writes, without locking conflicts. `busy_timeout` handles transient contention.
- **Read-only dashboard** -- the dashboard opens the database in read-only mode, preventing any accidental writes.
- **Seed-first demo** -- the 79 verified seed articles allow the full dashboard to be demonstrated without API keys or live RSS ingestion.
- **3D globe with GlobeView** -- deck.gl 9.1.8 GlobeView renders country polygons from Natural Earth GeoJSON (public domain, bundled as static files). Implemented as a Streamlit bidirectional component for click interaction. Auto-rotation pauses on interaction and resumes after 3 seconds idle.
- **Choropleth drill-down** -- admin-1 boundaries (states/provinces) from Natural Earth, with a static city-to-admin-1 resolver (`geo_resolver.py`) mapping all `regions.yaml` aliases to GeoJSON boundary names. Falls back to scatter dots if GeoJSON is unavailable.
- **Dynamic YouTube stream resolution** -- YouTube deprecated the `live_stream?channel=` embed format. At dashboard startup, `src/stream_resolver.py` resolves channel IDs to current live video IDs via the YouTube Data API v3, producing working `youtube.com/embed/<VIDEO_ID>` URLs. Fallback chain for webcams: configured channel → YouTube search for `<city> live webcam` → SkylineWebcams link (Cape Town, KL, Durban) → placeholder. Requires `YOUTUBE_API_KEY` in `.env`; dashboard works without it but streams show placeholders. Resolution runs once per process (not per Streamlit rerun).
- **Article caps** -- per-feed cap (100, enforced within each feed) and per-run cap (~500, checked between feeds so the last feed's articles may slightly exceed the target) prevent LLM cost amplification from high-volume feeds.
- **Charset detection** -- feedparser receives `Content-Type` headers for correct charset handling of non-English feeds.

## Design Documents

- `docs/plans/2026-03-31-surveillance-monitor-design.md` -- full design doc
- `docs/plans/2026-03-31-surveillance-monitor-implementation.md` -- implementation plan
- `docs/cowork_log.md` -- session-by-session build log
- `docs/BUGLOG.md` -- CC4 audit findings (56 issues: 37 fixed, 17 accepted, 2 false positives)

## Status

23 production modules implemented. 610 tests passing across 24 test files. CC4 audit complete (0 critical issues).
