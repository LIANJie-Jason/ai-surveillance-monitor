# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AI Surveillance & Censorship News Monitor** — a prototype that continuously monitors online news sources and screens for stories about government surveillance and censorship behaviors. Built as an NSF grant demo.

Reference architecture: [github.com/koala73/worldmonitor](https://github.com/koala73/worldmonitor) (RSS-based global news monitoring with AI filtering).

## Architecture

Two-process pipeline:
1. **Ingestion worker** (`src/ingestion.py`) — fetches RSS feeds via feedparser, deduplicates by URL hash, classifies via LLM, stores to SQLite
2. **Streamlit dashboard** (`dashboard/app.py`) — reads the same SQLite (read-only mode) and renders a dark command-center web dashboard with maps, news feed, and drill-down views

**Tech stack:** Python 3.11+, Streamlit, feedparser, openai, anthropic, SQLite, deck.gl (embedded HTML/JS), PyYAML

## Project Structure

```
src/
  models.py          # Article/Feed dataclasses, URL canonicalization, VALID_CATEGORIES
  database.py        # SQLite layer (upsert, queries, read_only mode, busy_timeout)
  llm_client.py      # OpenAI primary, Anthropic fallback; returns (text, provider)
  classifier.py      # LLM-based surveillance/censorship classification
  summarizer.py      # LLM-based article summarization
  url_utils.py       # Shared SSRF/private-host validation (used by models, article_detail, _utils)
  stream_resolver.py # YouTube Data API v3 — resolves channel IDs to live video IDs at startup
  ingestion.py       # RSS fetch worker with schedule loop

scripts/
  init_db.py         # Create DB + load feeds from config
  seed_data.py       # Load verified seed articles into DB; returns (loaded, total, already_exists)
  prepare_geojson.py # Download + simplify Natural Earth GeoJSON for maps

config/
  feeds.yaml         # 64 RSS feed URLs with source tiers (60 active)
  regions.yaml       # Drill-down regions for IN, MY, NG, ZA (cities + lat/lng)
  streams.yaml       # Live video stream URLs
  webcams.yaml       # Webcam feed URLs

dashboard/
  app.py             # Main Streamlit app entry point
  components/
    map_global.py    # deck.gl global scatter map (legacy flat view, still used for data building)
    map_globe.py     # 3D rotating globe view (GlobeView + GeoJsonLayer)
    map_drilldown.py # Regional map: scatter (legacy) + choropleth (admin-1 fills)
    geo_resolver.py  # Maps city/region names to admin-1 GeoJSON boundary names
    _utils.py        # Shared utilities (safe_json_for_script, safe_embed_url)
    news_feed.py     # Article list with filtering (legacy, unused by app.py)
    article_detail.py # Single article detail view
    live_stream.py   # Embedded video streams
    webcams.py       # Webcam grid
  styles/
    dark_theme.css   # Dark command-center theme
  static/
    deck_map.html        # deck.gl flat scatter map template (legacy)
    deck_globe.html      # deck.gl 3D globe template (GlobeView + auto-rotation)
    deck_choropleth.html # deck.gl choropleth template (admin-1 region fills)
    geojson/
      countries_110m.geojson  # Natural Earth 110m world country boundaries
      admin1_IN.geojson       # India admin-1 states/territories
      admin1_MY.geojson       # Malaysia admin-1 states
      admin1_NG.geojson       # Nigeria admin-1 states
      admin1_ZA.geojson       # South Africa admin-1 provinces

data/
  seed_articles.json # 79 web-verified seed articles (IN, MY, NG, ZA + global)
  monitor.db         # SQLite database (gitignored)
```

## Key Design Decisions

- **URL deduplication:** `Article._canonicalize_url()` strips trailing slashes, UTM params; `Article._hash_url()` produces SHA-256 ID
- **Categories:** `VALID_CATEGORIES` frozenset in `src/models.py`: surveillance, censorship, facial_recognition, internet_shutdown, data_collection, social_media_control, digital_rights, other
- **Country codes:** ISO 3166-1 alpha-2 (2 uppercase letters). "EU" is not valid.
- **Source tiers** (4-tier; authoritative definition lives in `config/feeds.yaml` header):
  - `1` — Wire services: Reuters, AP, AFP (highest reliability, broadest distribution)
  - `2` — Major international outlets: BBC, Guardian, NYT, Al Jazeera, France 24, CNN, Washington Post, NPR, Bloomberg, Deutsche Welle
  - `3` — Specialty / digital rights / cybersecurity: HRW, Amnesty, Freedom House, CPJ, RSF, Access Now, ARTICLE 19, EFF, TechCrunch, The Record, Citizen Lab, Lawfare, NetBlocks, Wired, RFA
  - `4` — Regional sources: drill-down countries (IN, MY, NG, ZA) + non-English international. Seed article tiers align with this taxonomy (HRW/Amnesty/CPJ = 3, not 1).
- **LLM fallback:** OpenAI primary → Anthropic fallback. `LLMClient.complete()` returns `(text, provider)` tuple
- **Seed data:** All 79 articles in `data/seed_articles.json` are real, web-search-verified. 52 have exact publication dates; 27 use day=15 midpoint (month-level approximation). `llm_provider="seed"`, `is_surveillance=True`. `seed_database()` returns `(loaded, total, already_exists)` and `main()` exits with code 1 if `loaded + already_exists < total`
- **Date convention:** Exact dates where known; month-level approximations use day=15 midpoint (never day=01)
- **Drill-down countries:** IN (India), MY (Malaysia), NG (Nigeria), ZA (South Africa) — defined in `config/regions.yaml`

## Running

```bash
# Install dependencies
pip install -r requirements.txt

# Set API keys
cp .env.example .env  # then fill in OPENAI_API_KEY, ANTHROPIC_API_KEY

# Initialize database and seed
python scripts/init_db.py
python scripts/seed_data.py

# Run dashboard (uses seeded data; no API keys needed for demo)
streamlit run dashboard/app.py

# Run live ingestion (single pass — requires API keys in .env)
python scripts/run_ingestion.py --once

# Run live ingestion (continuous, every 30 min)
python scripts/run_ingestion.py

# Custom interval (10 min) with debug logging
python scripts/run_ingestion.py --interval 600 --log-level DEBUG
```

## Testing

```bash
# Run all tests (695 tests)
python -m pytest tests/ -q

# Run specific test file
python -m pytest tests/test_scripts.py -v
```

## Status

25 modules implemented. 695 tests passing across 25 test files.

| Module | Status |
|--------|--------|
| 1-3. Foundation (scaffolding, models, database) | Done |
| 4. Config files (feeds, streams, webcams, regions) | Done |
| 5. DB init and seed scripts | Done |
| 6. LLM client with fallback | Done |
| 7. Classifier | Done |
| 8. Summarizer | Done |
| 9. RSS ingestion worker | Done |
| 10. Dark theme CSS | Done |
| 11. Global map component (flat, legacy) | Done |
| 11b. Globe view component (3D rotating globe) | Done |
| 12. Drill-down map component (scatter, legacy) | Done |
| 12b. Choropleth drill-down (admin-1 region fills) | Done |
| 12c. Geo resolver (city→admin-1 mapping) | Done |
| 13. News feed and article detail | Done |
| 14. Live stream and webcam components | Done |
| 15. Main dashboard app | Done |
| 16. Populate actual config URLs | Done |
| 17. Curate seed dataset (79 verified articles) | Done |
| 18. Update CLAUDE.md | Done |
| 19. End-to-end smoke test | Done |
| 20. CLI ingestion entry point | Done |

## Design Documents

- `docs/plans/2026-03-31-surveillance-monitor-design.md` — full design doc
- `docs/plans/2026-03-31-surveillance-monitor-implementation.md` — implementation plan with 19 tasks
- `docs/cowork_log.md` — session-by-session build log
