# AI Surveillance & Censorship News Monitor — Design Document

> **Date:** 2026-03-31
> **Purpose:** NSF grant demo prototype
> **Timeline:** 2-3 weeks
> **Approach:** Two-process pipeline (ingestion worker + Streamlit dashboard)

---

## 1. Overview

A prototype that continuously monitors 50+ online news sources (including non-English) and uses LLMs to detect and classify government surveillance and censorship stories. Results are displayed on a dark "command-center" style web dashboard with an interactive world map, news feed, and country drill-down views with live video.

Reference architecture: [github.com/koala73/worldmonitor](https://github.com/koala73/worldmonitor)

---

## 2. Architecture & Data Flow

```
┌─────────────────────────────────────────────────────┐
│                  INGESTION WORKER                    │
│                                                      │
│  RSS Feeds (50+)                                     │
│      |                                               │
│  feedparser  ->  deduplicate (SHA256 of URL)          │
│      |                                               │
│  LLM Classifier (OpenAI primary / Anthropic fallback)│
│      |  (is_surveillance, confidence, category)      │
│  If flagged (confidence >= 0.6):                     │
│      -> LLM Summarize                                │
│      -> Translate title+summary (if non-English)     │
│      -> Extract country + region via LLM             │
│      |                                               │
│  SQLite  <-- store all articles, flag relevant ones   │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                  DASHBOARD (Streamlit)                │
│                                                      │
│  Reads from same SQLite database                     │
│  Auto-refreshes every 60 seconds                     │
│  Works with pre-seeded or live data                  │
└─────────────────────────────────────────────────────┘
```

**Key design decisions:**
- Ingestion and dashboard are fully decoupled via SQLite
- Ingestion runs on a schedule (every 30 min via `schedule` library or cron)
- Single LLM call handles classification + country extraction (cost-efficient)
- Separate LLM call for summary + translation (only for flagged articles, ~5-10%)
- Pre-seeded dataset guarantees dashboard looks populated for demos

---

## 3. Database Schema

```sql
-- All collected articles (flagged or not)
CREATE TABLE articles (
    id              TEXT PRIMARY KEY,   -- SHA256 of URL
    url             TEXT UNIQUE,
    title           TEXT,
    title_en        TEXT,               -- translated title (NULL if already English)
    source_name     TEXT,               -- e.g., "Reuters", "Kompas"
    source_lang     TEXT,               -- e.g., "en", "zh", "ms"
    source_tier     INTEGER,            -- 1=wire, 2=major, 3=specialty, 4=regional
    published_at    TIMESTAMP,
    fetched_at      TIMESTAMP,
    content_snippet TEXT,               -- first ~500 chars of article body

    -- LLM classification results
    is_surveillance BOOLEAN DEFAULT 0,
    confidence      REAL,               -- 0.0 - 1.0
    category        TEXT,               -- see category list below
    country_code    TEXT,               -- ISO 3166-1 alpha-2
    country_name    TEXT,
    region          TEXT,               -- sub-national, for drill-down countries only

    -- AI summary (only for flagged articles)
    summary_en      TEXT,

    -- Metadata
    classified_at   TIMESTAMP,
    llm_provider    TEXT                -- "openai" or "anthropic"
);

-- Feed definitions
CREATE TABLE feeds (
    id              INTEGER PRIMARY KEY,
    name            TEXT,
    url             TEXT UNIQUE,
    language        TEXT,
    tier            INTEGER,
    category        TEXT,               -- "wire", "major", "specialty", "regional"
    country_focus   TEXT,               -- NULL for international, ISO code for regional
    active          BOOLEAN DEFAULT 1,
    last_fetched_at TIMESTAMP
);
```

**Classification categories:** `surveillance`, `censorship`, `facial_recognition`, `internet_shutdown`, `digital_rights`, `social_media_control`, `data_collection`, `other`

---

## 4. News Sources

### Tier 1 — Wire Services & Major International (~15 feeds)
Reuters, AP, AFP, BBC World, Al Jazeera English, Guardian World, NYT, Washington Post

### Tier 2 — Surveillance/Digital Rights Specialty (~15 feeds)
The Intercept, EFF Deeplinks, Access Now, Citizen Lab, CPJ, Ranking Digital Rights, Rest of World, The Record (Recorded Future), Wired Security

### Tier 3 — Regional Sources for Drill-Down Countries (~20+ feeds)

| Country | English Sources | Local Language Sources |
|---------|----------------|----------------------|
| **Malaysia (MY)** | Malaysiakini (EN), The Star | Malaysiakini (BM), Berita Harian |
| **Nigeria (NG)** | Premium Times, Punch, The Cable | -- (English-dominant media) |
| **India (IN)** | The Wire, Scroll.in, Indian Express, India Times | NDTV Hindi, Dainik Bhaskar |
| **South Africa (ZA)** | Daily Maverick, News24, Mail & Guardian | -- (English-dominant media) |

### Tier 4 — Non-English International (~10 feeds)
- Chinese: Caixin, South China Morning Post (EN+ZH)
- Russian: Meduza (EN+RU)
- Arabic: Al Jazeera Arabic
- Farsi: Iran Wire, Radio Farda
- French: Le Monde, RFI

**Total: ~55-60 feeds.** Stored in `feeds` table; add/remove without code changes.

---

## 5. LLM Classification Pipeline

### Step 1 — Classify + Extract Country (all articles, batched)

- **Model:** gpt-4.1-mini (primary) / claude-haiku-4-5 (fallback)
- **Batch:** 10 articles per call
- **Threshold:** flag articles with confidence >= 0.6
- **Output:** JSON with `is_surveillance`, `confidence`, `category`, `country_code`, `country_name`, `region`

```
Prompt: You are a news classifier. Given this article headline and snippet,
determine:
1. Is this about government surveillance, censorship, or digital rights? (yes/no)
2. Confidence (0.0-1.0)
3. Category: surveillance | censorship | facial_recognition | internet_shutdown |
   digital_rights | social_media_control | data_collection | other
4. Primary country (ISO code + name)
5. Sub-national region (if identifiable, for MY/NG/IN/ZA only)

Respond in JSON.
```

### Step 2 — Summarize + Translate (flagged articles only)

- **Model:** gpt-4.1 (primary) / claude-sonnet-4-6 (fallback)
- **Triggered:** only when `is_surveillance = true`
- **Handles:** English summary generation + translation of non-English titles
- **Non-English classification:** done in original language (modern LLMs handle multilingual well)

```
Prompt: Summarize this article in 2-3 sentences in English, focusing on:
- What surveillance/censorship action is described
- Which government or authority is involved
- What population is affected
```

### Cost Estimate
- ~1,000 articles/day, ~50-100 flagged
- Step 1: ~$0.50/day (gpt-4.1-mini)
- Step 2: ~$0.30/day (gpt-4.1)
- **Total: ~$0.80/day / ~$24/month**

---

## 6. Dashboard Layout

### Main View (Global)

```
+--------------------------------------------------------------+
|  TOP BAR                                                      |
|  "AI Surveillance Monitor" | Last updated: ... | Filters      |
|  [Country v] [Category v] [Date Range] [Confidence >=0.6]    |
+--------------------------------------------------------------+

+--------------------------------------------------------------+
|                                                               |
|              INTERACTIVE MAP (~55% height)                    |
|                                                               |
|   Dark deck.gl map with:                                      |
|   - Colored circles per country (size = article count)        |
|   - Color scale: yellow (few) -> red (many)                   |
|   - Hover: country name + count tooltip                       |
|   - Click MY/NG/IN/ZA: drill-down view                        |
|   - Click others: filter news feed to that country            |
|                                                               |
+--------------------------------------------------------------+

+------------------------------+-------------------------------+
|  NEWS FEED (~50% left)       |  ARTICLE DETAIL (~50% right)  |
|                              |                               |
|  Scrollable card list:       |  Selected article:            |
|  +------------------------+  |  - Headline (EN)              |
|  | 0.92 | India           |  |  - Original headline          |
|  | "Facial recognition    |  |  - AI Summary (2-3 sentences) |
|  |  deployed in Delhi..." |  |  - Confidence: 0.92           |
|  | The Wire | 2h ago      |  |  - Category: facial_recog     |
|  +------------------------+  |  - Source: The Wire (Tier 4)   |
|  +------------------------+  |  - Published: 2026-03-31       |
|  | 0.78 | Malaysia        |  |  - [Open Original ->]          |
|  | "MCMC orders block..." |  |                               |
|  +------------------------+  |                               |
+------------------------------+-------------------------------+
```

### Country Drill-Down View (MY, NG, IN, ZA)

```
+--------------------------------------------------------------+
|  COUNTRY DRILL-DOWN (e.g., India)               [<- Back]    |
+--------------------------------------------------------------+
|  +--------------+ +--------------+ +----------------------+  |
|  | REGIONAL MAP | | LIVE NEWS    | | CITY WEBCAMS         |  |
|  |   (35%)      | | STREAM (30%) | |   (35%)              |  |
|  |              | |              | | +----+ +----+        |  |
|  | Zoomed map   | | NDTV 24x7   | | |Delhi| |Mum.|       |  |
|  | with regional| | (YouTube)   | | |LIVE | |LIVE|        |  |
|  | markers      | |              | | +----+ +----+        |  |
|  |              | |              | | +----+ +----+        |  |
|  |              | |              | | |Bang.| |Chen|        |  |
|  |              | |              | | |LIVE | |LIVE|        |  |
|  +--------------+ +--------------+ | +----+ +----+        |  |
|                                     +----------------------+  |
|  +----------------------------------------------------------+ |
|  |  COUNTRY NEWS FEED (filtered articles for this country)   | |
|  +----------------------------------------------------------+ |
+--------------------------------------------------------------+
```

### Live Stream Sources

| Country | News Stream | Source |
|---------|------------|--------|
| India | NDTV 24x7 | YouTube Live |
| Malaysia | Astro Awani | YouTube Live |
| Nigeria | Channels TV | YouTube Live |
| South Africa | eNCA | YouTube Live |

### City Webcam Sources

| Country | Cities | Sources |
|---------|--------|---------|
| India | Delhi, Mumbai, Bangalore, Chennai | Webcamtaxi, SkylineWebcams |
| Malaysia | Kuala Lumpur, Penang, Johor Bahru | Webcamtaxi, SkylineWebcams |
| Nigeria | Lagos, Abuja | Webcamtaxi, YouTube city cams |
| South Africa | Cape Town, Johannesburg, Durban | SkylineWebcams, EarthCam |

Webcam and live stream URLs stored in YAML config. Loaded on-demand (drill-down click only).

### Visual Style
- Background: dark (#0d1117), light text
- Confidence colors: red (high >= 0.8), orange (medium 0.6-0.8)
- deck.gl map: dark basemap, colored scatter markers
- Auto-refresh: 60 seconds via `st_autorefresh`

---

## 7. Data Refresh Strategy

**Pre-seeded + live hybrid:**
- `seed_articles.json` ships with ~200 curated surveillance/censorship articles
- `scripts/seed_data.py` loads seed data into SQLite on first run
- Live ingestion adds new articles on top
- Dashboard always looks populated, even offline or during slow news periods

**Ingestion schedule:**
- Every 30 minutes via Python `schedule` library
- Can also be triggered manually via CLI flag

---

## 8. Project File Structure

```
AI surveillance news monitor/
├── CLAUDE.md
├── design.docx
├── requirements.txt
├── .env.example              # API keys template
├── config/
│   ├── feeds.yaml            # 50+ RSS feed definitions
│   ├── webcams.yaml          # city webcam URLs per country
│   └── streams.yaml          # live news stream URLs per country
├── src/
│   ├── __init__.py
│   ├── ingestion.py          # RSS fetch + deduplicate + schedule
│   ├── classifier.py         # LLM classification + country extraction
│   ├── summarizer.py         # LLM summary + translation (flagged only)
│   ├── llm_client.py         # OpenAI/Anthropic with fallback logic
│   ├── database.py           # SQLite operations
│   └── models.py             # dataclasses for Article, Feed, etc.
├── dashboard/
│   ├── app.py                # Streamlit entry point
│   ├── components/
│   │   ├── map_global.py     # deck.gl global map (embedded HTML/JS)
│   │   ├── map_drilldown.py  # deck.gl country zoom + regional markers
│   │   ├── news_feed.py      # scrollable card list
│   │   ├── article_detail.py # selected article panel
│   │   ├── live_stream.py    # YouTube news embed
│   │   └── webcams.py        # city webcam grid
│   ├── styles/
│   │   └── dark_theme.css    # command-center dark theme
│   └── static/
│       └── deck_map.html     # deck.gl map template
├── scripts/
│   ├── seed_data.py          # pre-seed DB with curated articles
│   └── init_db.py            # create SQLite tables
├── data/
│   ├── monitor.db            # SQLite database (gitignored)
│   └── seed_articles.json    # curated seed dataset
└── tests/
    ├── test_classifier.py
    ├── test_ingestion.py
    └── test_database.py
```

---

## 9. Key Dependencies

```
streamlit
streamlit-autorefresh
feedparser
openai
anthropic
pydeck
requests
pyyaml
python-dotenv
schedule
```

---

## 10. Demo Flow

1. Run `python scripts/init_db.py` to create database
2. Run `python scripts/seed_data.py` to load curated articles
3. Run `streamlit run dashboard/app.py` to launch dashboard
4. (Optional) Run `python -m src.ingestion` in background for live polling
5. Demo: show global map -> click India -> see drill-down with live NDTV + city webcams + filtered news
