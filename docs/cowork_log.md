# AI Surveillance News Monitor — Co-Work Log

## Project Overview
- **Purpose:** NSF grant demo prototype — monitors news for government surveillance/censorship stories
- **Architecture:** Two-process pipeline (RSS ingestion worker + Streamlit dashboard), SQLite, LLM classification
- **Timeline:** 2-3 weeks (started 2026-03-31)
- **Design doc:** `docs/plans/2026-03-31-surveillance-monitor-design.md`
- **Implementation plan:** `docs/plans/2026-03-31-surveillance-monitor-implementation.md`

---

## Session 1 — 2026-03-31

### Phase: Design & Planning

**Brainstorming (completed)**
- Walked through 8 clarifying questions one at a time
- Decisions: NSF demo purpose, Streamlit + embedded deck.gl map, 50+ feeds (incl. non-English), OpenAI primary + Anthropic fallback, classify in original language, country-level map with drill-down (MY/NG/IN/ZA), pre-seeded + live hybrid, classification + summarization, 2-3 week timeline
- Proposed 3 approaches; selected **Approach B: Two-Process Pipeline**
- Added live news streams (YouTube) and city webcams for drill-down views

**Design doc written**
- 10-section design covering architecture, schema, sources, LLM pipeline, dashboard layout, refresh strategy, file structure, dependencies, demo flow

**Implementation plan written**
- 19 tasks across 4 phases (Foundation, Ingestion, Dashboard, Polish)
- Full TDD with code blocks, test expectations, and commit messages

**Codex plan review — 3 rounds**
- Round 1: 8 HIGH, 7 MEDIUM, 2 LOW issues found. All fixed.
  - `time.mktime` → `calendar.timegm` (timezone bug)
  - URL canonicalization (strip UTM, guard empty)
  - `LLMClient.complete()` returns `(text, provider)` tuple
  - SQLite `busy_timeout=5000`, `read_only` mode for dashboard
  - `upsert_article` updates timestamps on conflict
  - Confidence threshold enforced in DB queries (`min_confidence=0.6`)
  - `regions.yaml` for stable drill-down geocoding
  - Streamlit native buttons instead of iframe `postMessage`
- Round 2: 4 HIGH, 4 MEDIUM, 2 LOW remaining. All fixed.
  - WAL pragma conditional on `read_only`
  - `ClassificationResult.llm_provider` field added
  - Classifier/ingestion tests updated for tuple return + `requests.get` patching
  - Seed data uses `_canonicalize_url()` + `published_at` as `fetched_at`
  - Tier taxonomy given concrete rubric
  - Task 14 (URL research) moved before Task 15 in plan body + dependency graph
- Round 3: 1 HIGH (dependency graph numbering). Fixed.

### Phase: Implementation — Module 1: Data Models

**Files:** `src/models.py` (171 lines), `tests/test_models.py` (16 tests)

**What was built:**
- `Article` — frozen dataclass with URL canonicalization, SHA-256 dedup, UTC time parsing
- `Feed` — frozen dataclass with `from_dict()` for YAML config
- `ClassificationResult` — frozen dataclass with `llm_provider` field

**Codex module audit — 4 rounds**
- Round 1: 2 HIGH, 2 MEDIUM, 1 LOW
  - `_STRIP_PARAMS` was a dataclass field → moved to module-level constant
  - No URL scheme validation → added `http`/`https` only guard
  - No host case normalization → lowercased scheme + netloc
  - Atom `updated_parsed` fallback → added `or entry.get("updated_parsed")`
- Round 2: Verified fixes; found 1 remaining MEDIUM (malformed HTTP URLs with empty host accepted)
  - Added `if not parsed.hostname: return ""` guard
- Round 3: Found edge cases (`http://:80`, `http://@/path`) → switched from `parsed.netloc` to `parsed.hostname`
- Round 4: **PASS** — all issues resolved

**Final test results:** 16/16 passed (0.02s)

**Key design decisions:**
- `calendar.timegm` for UTC-correct time parsing (not `time.mktime`)
- URL canonicalization strips UTM/tracking params before hashing
- Only `http`/`https` URLs with valid hostname accepted
- Host + scheme lowercased for deterministic dedup
- `from_rss_entry()` returns `Optional[Article]` — `None` for invalid entries
- `_STRIP_PARAMS` as module constant, not dataclass field

---

### Module 2: Database Layer

**Files:** `src/database.py` (~340 lines), `tests/test_database.py` (17 tests)

**What was built:**
- `Database` class — SQLite with WAL, `busy_timeout=5000`, `read_only` mode
- `upsert_article()` — COALESCE + CASE guard preserves classification/translation on re-ingest
- `get_flagged_articles()` — confidence threshold (0.6), country/category/date filters
- `get_country_counts()` — same filters, grouped by country
- Feed CRUD — `upsert_feed()`, `get_active_feeds()`, `update_feed_fetched()`

**Codex audit — 3 rounds**
- Round 1: 1 HIGH, 3 MEDIUM, 2 LOW
  - HIGH: Classification fields wiped on re-ingest → COALESCE + CASE guard
  - MEDIUM: Feed upsert skipped `language`/`country_focus` → fixed
  - MEDIUM: `last_fetched_at` lost on round-trip → hydrated in `get_active_feeds()`
  - MEDIUM: Date filtering relies on consistent timezone → accepted for prototype
  - LOW: `db_path` not sanitized → accepted (hardcoded, never user input)
  - LOW: Schema lacks NOT NULL → accepted for prototype
- Round 2: 1 MEDIUM remaining — `title_en` overwritten on re-ingest → COALESCE fix
- Round 3: **PASS** — no remaining issues

**Tests added for Codex findings:**
- `test_upsert_preserves_classification_on_reingest` — 7 classification fields survive
- `test_upsert_preserves_title_en_on_reingest` — translated title preserved
- `test_feed_upsert_updates_all_fields` — language, country_focus
- `test_update_feed_fetched_roundtrip` — last_fetched_at persists
- `test_read_only_mode` — read-only DB works
- `test_empty_db_queries` — empty results, no crashes

**Final test results:** 33/33 passed (17 database + 16 models)

---

### Module 3: Config Files

**Files:** `config/feeds.yaml`, `config/streams.yaml`, `config/webcams.yaml`, `config/regions.yaml`

**What was built:**
- 61 RSS feeds across 4 tiers (wire/major/specialty/regional), 6+ languages
- YouTube Live streams for 4 drill-down countries with fallback channels
- 12 city webcam placeholders (URLs to be populated in Task 14)
- 38 normalized regions with aliases + lat/lng for LLM output mapping

**Codex audit — 3 rounds**
- Round 1: FAIL — wrong RSS URLs (RSF, Lawfare, Radio Farda), tier misassignment (France 24 as AFP wire), missing aliases (NCR, Klang Valley, Sandton, Lekki), East Malaysia collision, inconsistent fallback streams, missing critical sources
  - Fixed all: corrected URLs, re-tiered France 24, added aliases, resolved collisions, added NetBlocks/OONI/ARTICLE 19
- Round 2: FAIL — RSF still index page, Lawfare /feed 404, Radio Farda wrong API path, Administrative Capital alias collision (MY/ZA)
  - Fixed: RSF→/news.xml, Lawfare→/feeds/articles, Radio Farda→correct API path, removed collision
- Round 3: **PASS**

**Final state:** 61 feeds, 38 regions, no alias collisions, 33/33 tests passing

---

### Module 4: DB Init + Seed Scripts

**Files:** `scripts/init_db.py`, `scripts/seed_data.py`, `data/seed_articles.json`, `tests/test_scripts.py`

**What was built:**
- `init_database()` — creates DB, loads 61 feeds from config. Idempotent.
- `seed_database()` — loads 50 curated articles with URL canonicalization. Idempotent.
- 50 seed articles across 14 countries, 7 categories
- Both scripts work as CLI (`python scripts/init_db.py`) and as importable functions
- 6 tests: init, idempotency, seed, JSON validation, URL canonicality

**Codex audit — 2 rounds**
- Round 1: 1 HIGH, 7 MEDIUM
  - HIGH: CLI entrypoints failed (ModuleNotFoundError) → added sys.path.insert
  - MEDIUM: os.makedirs crash on bare filename → guarded
  - MEDIUM: cwd-relative paths → resolved from repo root in main()
  - MEDIUM: EU country code invalid → changed to BE (Belgium)
  - MEDIUM: canonicalization test ineffective → strict equality check
  - MEDIUM (accepted): synthetic URLs, seed count semantics, 50 vs 200 articles
- Round 2: **PASS**

**Final test results:** 39/39 passed (0.16s)

---

### Module 5: LLM Client with Fallback

**Files:** `src/llm_client.py` (78 lines), `tests/test_llm_client.py` (8 tests)

**What was built:**
- `LLMClient` class — OpenAI primary, Anthropic fallback
- `complete()` returns `tuple[str, str]` — (response_text, provider_used)
- Narrowed exception handling: only retriable errors (connection, timeout, server, rate-limit) trigger fallback
- Non-retriable errors (auth, bad request) propagate immediately
- Logging on fallback activation for observability
- Both-fail raises `RuntimeError` with chained errors from both providers
- Input validation: rejects empty API keys at construction
- Timeout parameter (60s default) passed to both providers

**Codex audit — 2 rounds**
- Round 1: FAIL — 1 CRITICAL, 2 HIGH, 3 MEDIUM, 2 LOW
  - CRITICAL: None content from OpenAI returned silently → added None check + ValueError
  - HIGH: Bare `except Exception` catches non-retriable errors → narrowed to `_RETRIABLE_OPENAI` tuple
  - HIGH: No logging on fallback → added `logger.warning()`
  - MEDIUM: Original OpenAI error lost on both-fail → `RuntimeError` with chained errors
  - MEDIUM: Empty API keys accepted → constructor validation
  - MEDIUM: System prompt asymmetry → accepted (matches provider conventions)
  - LOW: No timeout → added `timeout` parameter
  - LOW: No retry before fallback → accepted for prototype
  - 6 test gaps identified → 5 new tests added (8 total)
- Round 2: **PASS** — all fixes verified

**Final test results:** 47/47 passed (8 LLM client + 39 existing, 0.55s)

---

### Module 6: Classifier

**Files:** `src/classifier.py` (~275 lines), `tests/test_classifier.py` (21 tests)

**What was built:**
- `Classifier` class — batch article classification via LLM with JSON output parsing
- Prompt injection defense: `<article>` delimiters, `_sanitize_text()` escapes `<`/`>`, system prompt instructs to ignore embedded instructions
- Output validation: confidence clamping, category normalization, strict `is True` check for is_surveillance, 0.6 confidence threshold
- Country code validation: 2-char ASCII alpha only (shape-only, documented trade-off)
- Country-scoped region normalization: loads `config/regions.yaml` aliases per-country, prevents cross-country collisions
- Batch size limit: `_MAX_BATCH_SIZE = 20` with `ValueError` on overflow
- Markdown fence stripping for LLM responses
- Index handling: missing/duplicate/out-of-order, bool rejection, integer-float acceptance, NaN/Inf rejection
- Graceful fallback: malformed JSON → empty list, LLM exception → empty list with logging

**Codex audit — 7 rounds**
- Round 1: CONDITIONAL PASS — 3 MEDIUM, 4 LOW, 8 test gaps
  - Prompt injection (no sanitization/delimiters)
  - Region normalization missing
  - No batch size limit
  - Non-dict JSON crashes, markdown fences, float indexes
- Round 2: FAIL — 2 MEDIUM, 1 LOW remaining
  - regions.yaml loading didn't match YAML structure (top-level `regions:` key)
  - Delimiter wrapping claimed but absent
  - Float 0.9 → 0 silent mis-assignment
- Round 3: FAIL — delimiter escaping missing, NaN/Inf crash on int()
- Round 4: FAIL — non-finite confidence, string is_surveillance, ineffective test
- Round 5: FAIL — region normalization global not country-scoped, non-ASCII country codes
- Round 6: Fixed country-scoped normalization + ASCII-only country codes
- Round 7: **PASS** — all issues resolved

**Final test results:** 68/68 passed (21 classifier + 47 existing, 0.64s)

---

### Module 7: Summarizer

**Files:** `src/summarizer.py` (~121 lines), `tests/test_summarizer.py` (12 tests)

**What was built:**
- `Summarizer` class — per-article English summarization + non-English title translation
- Uses gpt-4.1 primary / claude-sonnet-4-6 fallback (heavier models for quality)
- Prompt injection defense: `<article>` / `<headline>` delimiters, `_sanitize()` escapes `<`/`>`, system prompts instruct to ignore embedded instructions
- `_is_english()` handles en, en-US, en-GB, EN variants
- Empty LLM response detection: falls back to content_snippet
- Empty title early return: skips LLM call, returns snippet
- Translation failure graceful: returns None title_en, summary still works
- Whitespace-only translation → None

**Codex audit — 2 rounds**
- Round 1: PASS — 1 HIGH, 3 MEDIUM, 2 LOW
  - HIGH: Prompt injection → delimiters + sanitize + system prompt hardening
  - MEDIUM: No empty title guard → early return
  - MEDIUM: Fragile `!= "en"` → `_is_english()` with startswith
  - MEDIUM: Empty LLM response → fallback check
  - LOW: Truncation cosmetic, no token tracking → accepted
- Round 2: **PASS** — 2 new LOW (source_lang not sanitized, `&` not escaped) accepted

**Final test results:** 80/80 passed (12 summarizer + 68 existing, 0.71s)

---

---

### Module 8: RSS Ingestion Worker

**Files:** `src/ingestion.py` (~190 lines), `tests/test_ingestion.py` (23 tests)

**What was built:**
- `IngestionWorker` class — fetches RSS feeds, classifies, summarizes, stores to DB
- `fetch_feed()` returns `tuple[list[Article], bool]` — distinguishes failed vs empty feeds
- Cross-feed dedup via `seen_ids` set shared across feeds in one run
- `process_batch()` — classify batch + summarize flagged + upsert all
- `run_once()` — fetches all active feeds, processes in `_BATCH_SIZE=10` batches
- Bozo feed handling: warns + processes valid entries; returns `([], False)` if bozo + empty
- Per-entry try/except in `fetch_feed()` so one bad entry doesn't kill the feed
- Per-article try/except on `upsert_article()` so one DB failure doesn't drop the batch
- `classify_batch` exception caught → synthesizes defaults for all articles
- `classify_batch` result coerced to `list()` for non-list iterables (tuples, generators)
- `get_active_feeds()` wrapped in try/except for graceful abort
- Only `update_feed_fetched()` on `success=True`

**Codex audit — 3 rounds**
- Round 1: FAIL — 1 HIGH, 2 MEDIUM
  - HIGH: `classify_batch` returning `[]` causes `zip()` to silently drop all articles → pad with `_default_result()`
  - MEDIUM: `update_feed_fetched` called on failed fetch → `(articles, success)` tuple return
  - MEDIUM: No in-memory dedup across feeds → `seen_ids` set
- Round 2: FAIL — 1 HIGH, 2 MEDIUM
  - HIGH: `classify_batch` exception drops entire batch → try/except + default synthesis
  - MEDIUM: Per-entry exception kills whole feed → per-entry try/except
  - MEDIUM: `get_active_feeds()` crash kills entire run → try/except guard
  - Also fixed: bozo+empty returns False, `list()` coercion on classifier results, per-article upsert guard
- Round 3: **PASS** — 0 CRITICAL, 0 HIGH, 0 MEDIUM, 2 LOW (accepted)
  - LOW: `success=True` when all entries raised → acceptable edge case for prototype
  - LOW: No bounds on feed size → accepted for prototype

**Tests (23):**
- `fetch_feed`: returns articles+success, skips duplicates, handles bozo, HTTP error returns false, skips None articles, bozo+empty returns false, cross-feed dedup, entry exception continues
- `process_batch`: classifies+summarizes, empty list, pads short results, classifier empty, summarizer exception upserts, classifier exception upserts defaults, upsert failure continues, classifier returns tuple
- `run_once`: fetches all feeds, batching >10 articles, skips fetched on failure, per-feed exception resilience, get_active_feeds failure aborts gracefully

**Final test results:** 101/101 passed (23 ingestion + 78 existing, 0.75s)

---

### Module 9: Dark Theme CSS

**Files:** `dashboard/styles/dark_theme.css` (~340 lines), `dashboard/styles/__init__.py` (~33 lines), `tests/test_dark_theme.py` (21 tests)

**What was built:**
- Full dark command-center palette: background `#0d1117`, cards `#161b22`, borders `#30363d`, text `#e6edf3`
- 4 accent colors: red (high confidence), orange (medium), green (active), blue (links)
- Styled: sidebar, header, metrics, expanders, buttons, tabs, selectbox, text inputs, textarea, progress bars, spinners, alerts, DataFrames (cell color overrides)
- Custom components: article cards, confidence badges, category tags, country buttons, scrollable news feed, live stream containers, webcam grid
- `.stApp` uses `!important` for cascade resilience
- `load_dark_theme()`: reads CSS, injects via `st.markdown`, graceful skip on missing file, robust `</style>` injection guard via regex (`<\s*/\s*style\b[^>]*>`)
- WCAG AA contrast verified for all color pairs

**Codex audit — 3 rounds:**
- Round 1: FAIL — 2 HIGH (DataFrame cells, form inputs), 5 MEDIUM → all fixed
- Round 2: FAIL — 1 HIGH (regex bypass with `</style/>`, `</style x>`) → regex broadened
- Round 3: **PASS**

**Final test results:** 122/122 passed (21 dark theme + 101 existing, 0.94s)

---

### Module 10: Global Map Component

**Files:** `dashboard/static/deck_map.html` (~100 lines), `dashboard/components/map_global.py` (~250 lines), `tests/test_map_global.py` (25 tests)

**What was built:**
- `deck_map.html`: self-contained deck.gl template using Carto Dark Matter basemap (no API key), ScatterplotLayer, yellow-to-red color scale, hover tooltips with `textContent` (XSS-safe), `__DATA__` placeholder for JSON injection
- `COUNTRY_COORDS`: ~200 countries with lat/lng centroids and human-readable names
- `DRILL_DOWN_COUNTRIES`: tuple of 4 drill-down countries (MY, NG, IN, ZA)
- `build_map_data()`: converts `{country_code: count}` → list of dicts with lat/lng; validates count (non-negative int, rejects inf/nan/overflow/non-numeric)
- `_safe_json_for_script()`: escapes `<` as `\u003c` to prevent `</script>` XSS breakout
- `render_map_html()`: reads template, injects safely escaped JSON data

**Codex audit — 4 rounds:**
- Round 1: FAIL — 1 HIGH (XSS via `</script>` in JSON injection) → added `\u003c` escaping
- Round 2: FAIL — 1 MEDIUM (OverflowError on inf), 2 LOW → added `math.isfinite()` check
- Round 3: FAIL — 1 MEDIUM (OverflowError on huge int 10**10000) → added `OverflowError` to except
- Round 4: **PASS**

**Final test results:** 147/147 passed (25 map + 122 existing, 1.00s)

---

### Module 11: Drill-down Map Component

**Files:** `dashboard/components/map_drilldown.py` (~133 lines), `tests/test_map_drilldown.py` (20 tests)

**What was built:**
- `load_regions()` — loads `config/regions.yaml`, cached with `@lru_cache(maxsize=1)`, graceful error handling (OSError, YAMLError, invalid structure → empty dict)
- `get_country_center(cc)` — returns `{lat, lng, zoom}` copy for 4 drill-down countries, None for unknown
- `_build_alias_map(regions)` — builds lowercase alias→region lookup for case-insensitive matching
- `build_region_data(articles, country_code)` — aggregates articles by region with alias resolution (e.g. "Bombay"→"Mumbai"), skips unknown/None regions, filters by country_code, emits tooltip-compatible fields (`country_code`, `country_name`)
- `_safe_json_for_script(data)` — JSON-encodes with `\u003c` escaping (XSS prevention)
- `render_drilldown_html(data, center)` — renders deck.gl HTML with injected data and overridden view state

**Key design decisions:**
- Reuses `dashboard/static/deck_map.html` template (same as global map) with view-state override
- `country_name` set to `region_name` for tooltip compatibility (shared template reads `country_name`)
- Country_code filtering: skips articles where `article.country_code is not None and != country_code` (prevents cross-country contamination)
- lru_cache on YAML loading: static config file parsed once per process

**Codex audit — 2 rounds:**
- Round 1: 3 MEDIUM (tooltip key mismatch, no error handling for YAML, mixed-country contamination), 4 LOW (mutable return, caching, brittle view-state replacement, duplicate aliases)
  - Fixed: all 3 MEDIUM + 2 LOW (mutable return, caching)
  - Accepted: 2 LOW (brittle view-state replacement — template-controlled; duplicate alias detection — no duplicates in current YAML)
- Round 2: **PASS** — all 3 MEDIUM confirmed resolved, no new bugs

**Final test results:** 167/167 passed (20 drill-down + 147 existing, 1.03s)

---

### Module 12: News Feed and Article Detail

**Files:** `dashboard/components/news_feed.py` (~86 lines), `dashboard/components/article_detail.py` (~90 lines), `tests/test_news_feed.py` (47 tests)

**What was built:**

*news_feed.py:*
- `format_time_ago(published_at, now)` — relative time: "just now", "Xm ago", "Xh ago", "Xd ago", "unknown" for None. Handles naive datetimes via `utcoffset() is None` check.
- `confidence_class(confidence)` — returns CSS class name ("confidence-high" ≥ 0.8, "confidence-medium" otherwise)
- `render_article_card(article)` — HTML card with title, confidence badge, country, source, time ago. All text `html.escape()`d.
- `render_news_feed(articles)` — scrollable card list sorted by confidence desc. "No articles found." for empty.

*article_detail.py:*
- `_safe_url(url)` — URL scheme allowlist (http/https only) + hostname check + ValueError guard for malformed IPv6. Returns "" for dangerous/invalid URLs.
- `render_article_detail(article)` — full detail panel: EN headline, original headline (when different), AI summary, confidence, category, country, source+tier, published date, link (new tab, noopener). Returns placeholder when None. All text `html.escape()`d including `source_tier`.

**Key security measures:**
- All user-facing text HTML-escaped via `html.escape()` (title, source_name, summary_en, category, country_name, source_tier, url, article.id)
- URL scheme allowlist blocks javascript:, data:, vbscript: and hostless URLs
- Links use `target="_blank" rel="noopener noreferrer"`
- Naive datetime handling via `utcoffset() is None` (not `tzinfo is None`)

**Codex audit — 3 rounds:**
- Round 1: 1 HIGH (source_tier raw HTML injection), 2 MEDIUM (naive datetime crash, hostless URL bypass), test gaps
  - Fixed: all 3 + added 7 new tests
- Round 2: 1 MEDIUM (utcoffset check incomplete), 1 LOW (weak tier test)
  - Fixed: both
- Round 3: **PASS** (1 LOW — malformed IPv6 ValueError — also fixed)

**Final test results:** 214/214 passed (47 news feed + 167 existing, 1.12s)

---

### Module 13: Populate Actual URLs

**Files:** `config/feeds.yaml` (verified), `config/streams.yaml` (verified), `config/webcams.yaml` (populated), `tests/test_config_urls.py` (28 tests)

**What was done:**
- Verified 61 RSS feeds across 4 tiers — all have valid http/https URLs with hostnames, no duplicates
- Confirmed 8 YouTube stream embeds (4 primary + 4 fallback) — all channel IDs valid format (24 chars, UC prefix)
- Populated 12 webcam embed URLs across 4 countries — all YouTube embeds (iframe-embeddable):
  - 6 actual webcam YouTube embeds (Delhi, Mumbai, Bangalore, Penang, JB, Cape Town, JHB) — `type: "webcam"`
  - 5 news live stream fallbacks — `type: "news_fallback"` (Chennai/ABP News, KL/TV3 Malaysia, Lagos/Arise News, Abuja/AIT, Durban/SABC News)
- All webcam URLs distinct from both primary AND fallback stream URLs (prevents duplicate feeds in drill-down)
- Two SCMP feeds confirmed intentionally different (/rss/36 tech vs /rss/91 general) — cross-reference comments added
- France 24 moved from Tier 1 section to Tier 2 section (was misplaced); Tier 1 header corrected to "3 feeds"
- Added `type` field to all webcams ("webcam" vs "news_fallback") so UI can render them differently

**Known accepted limitations:**
- YouTube video IDs for live streams are ephemeral (acceptable for demo)
- Delhi, Mumbai webcams use nearest-available India cams (no city-specific cams exist)
- Lagos/Abuja use 24/7 news live streams (no Nigerian webcam infrastructure)
- KL/Durban originally used SkylineWebcams page URLs but X-Frame-Options blocked iframe embed → replaced with YouTube news streams
- 23 VERIFY markers remain in feed comment lines — URL values are clean; markers are for future production verification

**Codex audit — 4 rounds:**
- Round 1: 2 MEDIUM (SkylineWebcams X-Frame-Options for KL/Durban; Mumbai/Chennai duplicate embed_url), 3 test gaps
  - Fixed all
- Round 2: PASS on initial fixes, but stop hook caught CRITICAL: KL/Lagos/Durban webcams duplicated primary streams
  - Fixed: Chennai→ABP News, KL→Bernama TV, Lagos→Arise News, Abuja→AIT, Durban→Newzroom Afrika
  - Added `test_webcams_no_overlap_with_primary_streams`
- Round 3: 0 CRITICAL, 2 HIGH, 6 MEDIUM, 4 LOW
  - H1 (misleading coords) → added `type` field + `test_webcams_type_valid`
  - H2 (France 24 misplaced) → moved to Tier 2 section
  - M1 (SCMP double-entry) → cross-ref comments
  - M2 (tier count) → header corrected
  - M4 (fallback HTTPS) → added scheme check to `test_streams_fallback_urls_valid`
  - M5 (primary-fallback overlap) → added `test_streams_primary_fallback_no_overlap`
- Round 4: Codex verified all fixes; investigation completed (type field, overlap checks, cross-refs) — **PASS**

**Final test results:** 242/242 passed (28 config + 214 existing, 1.15s)

---

### Module 14: Live Stream and Webcam Components

**Files:** `dashboard/components/live_stream.py` (~100 lines), `dashboard/components/webcams.py` (~105 lines), `dashboard/components/_utils.py` (~18 lines), `tests/test_live_stream.py` (21 tests), `tests/test_webcams.py` (21 tests)

**What was done:**
- **live_stream.py**: `load_streams()` cached YAML loader, `get_stream_for_country(cc)` / `get_fallback_stream(cc)` return dict copies, `render_live_stream(cc, use_fallback, height)` renders YouTube iframe with LIVE badge, html.escape on all text, URL scheme validation
- **webcams.py**: `load_webcams()` cached YAML loader, `get_webcams_for_country(cc)` returns list of dict copies, `render_webcam_grid(cc, cam_height)` renders 2x2 CSS grid with city labels, LIVE/NEWS badges based on `type` field, iframe or placeholder for empty URLs
- **_utils.py**: Shared `safe_embed_url()` — validates https scheme + hostname, extracted to eliminate duplication
- All text html.escape()'d, URL scheme validated, height params int()-coerced, copies returned from getters

**Codex audit — 2 rounds:**
- Round 1: 0 CRITICAL, 0 HIGH, 3 MEDIUM (duplicate _safe_embed_url, height injection, mutable cache)
  - Fixed: extracted shared utility, added int() coercion, copy-on-read verified
- Round 2: **PASS** — 0 CRITICAL, 0 HIGH, 0 MEDIUM, 4 LOW (informational)

**Final test results:** 284/284 passed (42 new + 242 existing, 1.31s)

---

## Progress Summary

| Module | Status | Tests | Codex Rounds |
|--------|--------|-------|-------------|
| 1. Data Models | Done | 16 | 4 → PASS |
| 2. Database Layer | Done | 17 | 3 → PASS |
| 3. Config Files | Done | — | 3 → PASS |
| 4. DB Init + Seed | Done | 6 | 2 → PASS |
| 5. LLM Client | Done | 8 | 2 → PASS |
| 6. Classifier | Done | 21 | 7 → PASS |
| 7. Summarizer | Done | 12 | 2 → PASS |
| 8. Ingestion Worker | Done | 23 | 3 → PASS |
| 9. Dark Theme CSS | Done | 21 | 3 → PASS |
| 10. Global Map | Done | 25 | 4 → PASS |
| 11. Drill-down Map | Done | 20 | 2 → PASS |
| 12. News Feed + Detail | Done | 47 | 3 → PASS |
| 13. Populate URLs | Done | 28 | 4 → PASS |
| 14. Live Stream + Webcams | Done | 42 | 2 → PASS |
| **Total** | | **284** | |

---

## Session 5 — 2026-04-04

### Module 15: Main dashboard app (`dashboard/app.py`)

**Scope:** Streamlit entry point wiring all components: global map, drill-down map, news feed, article detail, live streams, webcams, sidebar filters, and routing between global/drill-down views.

**TDD workflow:**
- RED: 19 tests written, 17 failed (2 smoke tests passed)
- GREEN: `dashboard/app.py` implemented, 19/19 passed
- Full suite: 303 passed

**Files created:**
- `dashboard/app.py` — main dashboard entry point (~240 lines)
- `tests/test_dashboard_app.py` — 24 tests

**Architecture:**
- Pure logic helpers separated from Streamlit rendering for testability
- `get_view_state()` — routing logic (global vs drilldown)
- `select_country()` / `clear_country()` — state transitions
- `select_article()` / `clear_article()` — state transitions
- `build_filter_params()` — converts UI filters to DB query kwargs
- `get_categories()` — sorted list from `VALID_CATEGORIES`
- `_render_feed_and_detail()` — shared feed+detail column pair (DRY)
- `_render_sidebar()` — sidebar filters
- `_render_global_view()` — map + metrics + drill-down buttons + feed
- `_render_drilldown_view()` — regional map + live stream + webcams + feed
- `main()` — entry point with dark theme, session state, DB lifecycle

**Audit round 1 — Python reviewer (0 CRITICAL, 5 HIGH, 6 MEDIUM, 5 LOW):**

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | HIGH | Unused `db` param in `_render_sidebar` | Removed param |
| 2 | HIGH | `UnboundLocalError` risk in `main()` if DB init fails | `db = None` before try, check in finally |
| 3 | HIGH | Duplicate feed+detail block in global/drilldown | Extracted `_render_feed_and_detail()` |
| 4 | HIGH | Inline `COUNTRY_COORDS` import inside render loop | Moved to top-level import |
| 5 | HIGH | `html` variable shadows builtin in `map_drilldown.py` | Renamed to `rendered` |
| 6 | MEDIUM | `Optional[datetime]` should be `datetime \| None` | Fixed to PEP 604 style |
| 7 | MEDIUM | Bare `except Exception` hides error details | Shows exception class name |
| 8 | MEDIUM | `f"{country_name}"` unnecessary f-string | Changed to `country_name` |
| 9 | MEDIUM | Test assertions conflate key-absent with key-None | Changed to `"key" not in result` |
| 10 | MEDIUM | Import inside loop (PEP 8) | Moved to top-level |
| 11 | MEDIUM | Date filters not exposed in sidebar UI | Accepted — planned future feature |

**All HIGH and MEDIUM issues fixed. Tests expanded from 19 → 24.**

**Audit round 2 — Codex + re-verification (0 CRITICAL, 1 HIGH, 4 MEDIUM, 0 LOW):**

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | HIGH | Stale article detail after filter change | Check `selected_id in current_ids` before showing detail |
| 2 | MEDIUM | "Total Articles" metric unfiltered vs others filtered | Relabeled to "Total Collected" for clarity |
| 3 | MEDIUM | Unused imports in test file (`MagicMock`, `patch`, `pytest`) | Removed |
| 4 | MEDIUM | `unsafe_allow_html` defense-in-depth | Added escaping-contract comments at each call site |
| 5 | MEDIUM | Test coverage for Streamlit render paths | Accepted — requires live Streamlit session |

**All HIGH/MEDIUM fixed. Full suite: 308 passed.**

**Result: PASS (2 rounds)**

### Progress Table

| Module | Status | Tests | Codex Rounds |
|--------|--------|-------|--------------|
| 1. Scaffolding | Done | 0 | 1 → PASS |
| 2. Data Models | Done | 16 | 2 → PASS |
| 3. Database | Done | 17 | 3 → PASS |
| 4. Config Files | Done | 28 | 4 → PASS |
| 5. Init/Seed Scripts | Done | 6 | 2 → PASS |
| 6. LLM Client | Done | 8 | 2 → PASS |
| 7. Classifier | Done | 21 | 7 → PASS |
| 8. Summarizer | Done | 12 | 2 → PASS |
| 9. Ingestion Worker | Done | 23 | 3 → PASS |
| 10. Dark Theme CSS | Done | 21 | 3 → PASS |
| 11. Global Map | Done | 25 | 4 → PASS |
| 12. Drill-down Map | Done | 20 | 2 → PASS |
| 13. News Feed + Detail | Done | 47 | 3 → PASS |
| 14. Populate URLs | Done | 28 | 4 → PASS |
| 15. Live Stream + Webcams | Done | 42 | 2 → PASS |
| 16. Main Dashboard App | Done | 24 | 2 → PASS |
| **Total** | | **308** (was 284) | |

---

## Session 3 — 2026-04-04

### Module 17: Curate seed dataset — Replace with verified articles

**Problem:** All 166 existing seed articles had fabricated URLs (real events, fake specifics like generic article IDs `/9876543/`). User requested: "Make sure all the included news are real, not hallucinated."

**Approach:** Full replacement using web-search-verified articles from credible sources.
- Launched 7 parallel search agents across regions: India, China/Russia, Africa/SE Asia, global, plus targeted MY/NG/ZA agents
- Verification agent confirmed all 15 sampled existing articles had fabricated URLs
- Built new dataset exclusively from web-search-confirmed URLs

**Result:** 79 verified articles (down from 166 fabricated)

**Distribution:**
- **Drill-down countries:** IN:20, MY:15, NG:10, ZA:12
- **Other countries:** CN:6, RU:4, IL:3, TR:2, ET:2, MM:2, KE:1, IR:1, RS:1
- **Categories:** surveillance:23, censorship:20, digital_rights:10, internet_shutdown:7, facial_recognition:7, data_collection:6, social_media_control:6
- **Regions:** IN:6, MY:9, NG:6, ZA:9

**Sources include:** Al Jazeera, HRW, Freedom House, CPJ, Amnesty Int'l, TechCrunch, SCMP, The Wire, Malaysiakini, Premium Times, Daily Maverick, Access Now, RSF, The Moscow Times, +972 Magazine, and more (30+ distinct outlets).

**Audit — 1 round (Python reviewer):**

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | CRITICAL | AP article attributed to US News URL | Changed source to "US News & World Report (AP)", tier 2 |
| 2 | CRITICAL | `country_code: "EU"` not valid ISO 3166-1 | Removed EU AI Act article |
| 3 | HIGH | Carnegie 2026 article unverifiable | Removed |
| 4 | HIGH | Suaram/SOSMA article miscategorized as surveillance | Changed to digital_rights |
| 5 | HIGH | Mail & Guardian article miscategorized as facial_recognition | Changed to surveillance |

**All CRITICAL/HIGH fixed. Full suite: 308 passed.**

**Audit round 2 (Codex + Python reviewer):**

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | HIGH | 4 `m.thewire.in` mobile subdomain URLs risk dedup failure | Replaced with `thewire.in` equivalents |
| 2 | HIGH | `seed_database()` returns `int`, caller can't detect partial loads | Changed to `tuple[int, int]` (loaded, total); `main()` exits code 1 on partial |
| 3 | MEDIUM | CPJ naming inconsistent ("CPJ" vs full name) | Standardized to "Committee to Protect Journalists (CPJ)" |
| 4 | MEDIUM | 4 category misassignments (Amnesty NG, Baker McKenzie, Iran FoN, Turkey joint letter) | Corrected: internet_shutdown, digital_rights, surveillance, censorship |
| 5 | MEDIUM | ARTICLE 19 tier 2 (should be 1 — internationally recognized HR org) | Upgraded both instances to tier 1 |
| 6 | MEDIUM | `open(path)` without `encoding=` — cross-platform risk | Added `encoding="utf-8"` |
| 7 | MEDIUM | Per-article errors crash entire seed | Added per-article try/except with logging |

**All HIGH/MEDIUM fixed. seed_data.py fully rewritten.**

**Audit round 3 (Codex — date verification):**

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | HIGH | 10 publication dates wrong by months to years | All 10 corrected to web-verified exact dates |
| 2 | MEDIUM | No convention for approximate dates | Established: day=15 for month-level approximations, never day=01 |

Date corrections: Telangana (2024→2022), IFF (2024→2020), Chinmayanand (2019-09→2019-11), Amnesty Nigeria (2024-01→2021-10), Baker McKenzie (2024-02→2023-09), Internet Society (2023-11→2024-04), RSF 2020 (2024→2020), Malaysia MCMC (2024-01→2024-04), Myanmar drone (2024-01→2024-03), Kazakhstan (2024→2023).

**Final verification (Codex PASS):**
- Schema validation: 79/79 articles passed all required-field checks
- `country_code`: valid ISO alpha-2; `category`: valid enum; `source_tier`: 1–3; `confidence`: 0–1
- `published_at`: all ISO 8601 with timezone; raw + canonical duplicate URLs: 0; `day=01` dates: 0
- Runtime smoke check: first seed 79/79 rows, second seed 79/79 (idempotent)

**Result: PASS (3 rounds)**

---

### Module 18: Update CLAUDE.md

**Scope:** Comprehensive project documentation rewrite — architecture, file structure, design decisions, running instructions, testing, status.

**What was done:**
- Complete rewrite of `CLAUDE.md` with project overview, two-step pipeline architecture, file structure tree, all design decisions documented
- Seed dataset contract: `seed_database()` returns `(loaded, total)`, `main()` exits code 1 on partial
- Date convention documented: 52 exact dates, 27 day=15 midpoint approximations
- Valid categories, source tier taxonomy, country code conventions all recorded
- Running instructions: init_db, seed_data, dashboard, pytest

**Audit (Codex — 1 round):**

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | P1 | `python -m src.ingestion` documented but no `__main__` block exists | Removed command, added note documenting limitation |
| 2 | P1 | "52 exact publication dates" claim incomplete — 27 use day=15 | Fixed wording to "52 exact, 27 approximate (day=15)" |

Non-blocking findings for future work (not in CLAUDE.md scope):
- P1: Ingestion worker needs a runnable CLI entry point (`if __name__` block)
- P1: Transient classifier failures permanently record articles as non-surveillance (no retry)
- P2: Dashboard news feed only creates buttons for first 20 articles

**Result: PASS (1 round)**

**Full suite: 308 passed.**

### Progress Table

| Module | Status | Tests | Audit Rounds |
|--------|--------|-------|--------------|
| 1. Scaffolding | Done | 0 | 1 → PASS |
| 2. Data Models | Done | 16 | 2 → PASS |
| 3. Database | Done | 17 | 3 → PASS |
| 4. Config Files | Done | 28 | 4 → PASS |
| 5. Init/Seed Scripts | Done | 6 | 2 → PASS |
| 6. LLM Client | Done | 8 | 2 → PASS |
| 7. Classifier | Done | 21 | 7 → PASS |
| 8. Summarizer | Done | 12 | 2 → PASS |
| 9. Ingestion Worker | Done | 23 | 3 → PASS |
| 10. Dark Theme CSS | Done | 21 | 3 → PASS |
| 11. Global Map | Done | 25 | 4 → PASS |
| 12. Drill-down Map | Done | 20 | 2 → PASS |
| 13. News Feed + Detail | Done | 47 | 3 → PASS |
| 14. Populate URLs | Done | 28 | 4 → PASS |
| 15. Live Stream + Webcams | Done | 42 | 2 → PASS |
| 16. Main Dashboard App | Done | 24 | 2 → PASS |
| 17. Seed Dataset (verified) | Done | 308 (no new tests) | 3 → PASS |
| 18. Update CLAUDE.md | Done | 308 (no new tests) | 1 → PASS |
| **Total** | | **308** | |

---

### Module 19: End-to-end smoke test

**Files:** `tests/test_e2e_smoke.py` (28 tests)

**What was built:**
- Full pipeline integration test: `init_db` → `seed_data` → DB queries → dashboard component rendering
- 4 test classes covering all critical paths:
  - `TestPipelineIntegrity` (10 tests): feeds loaded, 79 articles seeded, all flagged, country counts, filtering by country/category/confidence, article round-trip, nonexistent ID, seed idempotency
  - `TestDashboardComponents` (7 tests): global map build + render, drill-down map for all 4 countries, news feed render (with articles + empty), article detail render (with article + None)
  - `TestDashboardLogic` (6 tests): view state routing, select/clear country, filter params, categories list, drill-down countries
  - `TestCrossComponent` (5 tests): filter → map → feed flow, drill-down flow, article detail from feed, seed-data ↔ JSON URL match, read-only DB mode

**Key design decisions:**
- Fixture yields `(db, db_path)` tuple — avoids private `_conn` access for read-only mode test
- Confidence threshold set to 0.95 — actually excludes 4 articles at 0.94, verifying filter works
- News feed assertion uses `html_mod.escape()` to match HTML-escaped titles in rendered output
- Categories count uses `len(VALID_CATEGORIES) + 1` instead of magic number
- `count_keys` allowlist explicitly filters params for `get_country_counts` signature

**Audit — 2 rounds (Python reviewer + Codex):**
- Round 1: FAIL — 2 HIGH, 4 MEDIUM, 2 LOW
  - E1 HIGH: `get_country_counts` received invalid `country_code` key → explicit allowlist
  - E2 HIGH: Confidence threshold test vacuously true → raised to 0.95 with strict `<` inequality
  - E3 MEDIUM: Weak `or` assertion → split into two independent assertions
  - E7 MEDIUM: Private `_conn` access → fixture yields `(db, db_path)`
  - E8 MEDIUM: Magic number 9 → `len(VALID_CATEGORIES) + 1`
  - E10 LOW: Weak None detail assertion → checks `"Select an article"` string
  - Added: `test_get_article_nonexistent` for negative-path coverage
- Round 2: **PASS** — 0 CRITICAL, 0 HIGH, 1 MEDIUM (black formatting, cosmetic), 2 LOW (accepted)

**Final test results:** 336/336 passed (28 e2e + 308 existing, 1.64s)

**Result: PASS (2 rounds)**

### Final Progress Table

| Module | Status | Tests | Audit Rounds |
|--------|--------|-------|--------------|
| 1. Scaffolding | Done | 0 | 1 → PASS |
| 2. Data Models | Done | 16 | 2 → PASS |
| 3. Database | Done | 17 | 3 → PASS |
| 4. Config Files | Done | 28 | 4 → PASS |
| 5. Init/Seed Scripts | Done | 6 | 2 → PASS |
| 6. LLM Client | Done | 8 | 2 → PASS |
| 7. Classifier | Done | 21 | 7 → PASS |
| 8. Summarizer | Done | 12 | 2 → PASS |
| 9. Ingestion Worker | Done | 23 | 3 → PASS |
| 10. Dark Theme CSS | Done | 21 | 3 → PASS |
| 11. Global Map | Done | 25 | 4 → PASS |
| 12. Drill-down Map | Done | 20 | 2 → PASS |
| 13. News Feed + Detail | Done | 47 | 3 → PASS |
| 14. Populate URLs | Done | 28 | 4 → PASS |
| 15. Live Stream + Webcams | Done | 42 | 2 → PASS |
| 16. Main Dashboard App | Done | 24 | 2 → PASS |
| 17. Seed Dataset (verified) | Done | 308 (no new tests) | 3 → PASS |
| 18. Update CLAUDE.md | Done | 308 (no new tests) | 1 → PASS |
| 19. E2E Smoke Test | Done | 28 | 2 → PASS |
| **Total** | **19/19** | **336** | |

---

## Session 3 — 2026-04-04

### Module 20: CLI Ingestion Entry Point

**Files:** `scripts/run_ingestion.py` (82 lines), `tests/test_run_ingestion.py` (24 tests)

**What was built:**
- CLI entry point for live RSS ingestion with `--once`, `--interval`, `--log-level` flags
- 5 pure functions: `parse_args()`, `load_api_keys()`, `build_components()`, `run_loop()`, `make_signal_handler()`
- `threading.Event.wait()` for interruptible sleep (graceful SIGINT/SIGTERM shutdown)
- API key loading via python-dotenv with clear error messages
- Exception handling in continuous loop body (retries on failure)

**Security fix:** `src/llm_client.py` — RuntimeError and warning log now use `type(exc).__name__` instead of `str(exc)` to prevent leaking partial API keys from OpenAI AuthenticationError messages.

**Multi-agent audit — 3 rounds**

Round 1 (Python reviewer + Security reviewer + Codex):

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | HIGH | `callable` (lowercase) invalid type annotation | → `Callable[[int, object \| None], None]` from `collections.abc` |
| 2 | MEDIUM | Test `interval=60` caused 60s real-time wait | → `interval=1` (run_loop doesn't enforce minimum) |
| 3 | MEDIUM | Worker exceptions not caught/logged in continuous loop | → Added try/except in loop body |
| 4 | MEDIUM | `llm_client.py:62` warning log leaked metadata via `str(exc)` | → `type(exc).__name__` only |
| 5 | MEDIUM | Logging to stdout instead of stderr | → `stream=sys.stderr` |
| 6 | LOW | Redundant `Optional` import | → Removed, uses `object \| None` |

Round 2 (Python reviewer + Codex):
- Python reviewer: **PASS** — all 6 Round 1 issues confirmed fixed
- Codex: **BLOCK** — 2 new issues:
  - M20-01 HIGH: First `worker.run_once()` in continuous mode was unguarded → Refactored to single guarded loop
  - M20-02 LOW: `--once --interval 1` triggered parser error → Skip interval validation when `--once` is set
  - Added 2 regression tests

Round 3 (Python reviewer): **PASS** — all issues resolved, no new findings

**Final test results:** 25/25 passed (2.46s), full suite 361/361 (3.84s)

**Key design decisions:**
- `threading.Event.wait(interval)` for interruptible sleep (not `time.sleep()`)
- Signal handler only sets event (no I/O in signal context)
- `--once` mode lets exceptions propagate; continuous mode catches and retries
- `_MIN_INTERVAL = 60` enforced only in continuous mode
- `load_api_keys()` uses `print()` to stderr (pre-logging bootstrap)
- Logging to stderr to avoid mixing with stdout data

---

### Updated Progress Table

| Module | Status | Tests | Audit Rounds |
|--------|--------|-------|--------------|
| 1. Scaffolding | Done | 0 | 1 → PASS |
| 2. Data Models | Done | 16 | 2 → PASS |
| 3. Database | Done | 17 | 3 → PASS |
| 4. Config Files | Done | 28 | 4 → PASS |
| 5. Init/Seed Scripts | Done | 6 | 2 → PASS |
| 6. LLM Client | Done | 8 | 2 → PASS |
| 7. Classifier | Done | 21 | 7 → PASS |
| 8. Summarizer | Done | 12 | 2 → PASS |
| 9. Ingestion Worker | Done | 23 | 3 → PASS |
| 10. Dark Theme CSS | Done | 21 | 3 → PASS |
| 11. Global Map | Done | 25 | 4 → PASS |
| 12. Drill-down Map | Done | 20 | 2 → PASS |
| 13. News Feed + Detail | Done | 47 | 3 → PASS |
| 14. Populate URLs | Done | 28 | 4 → PASS |
| 15. Live Stream + Webcams | Done | 42 | 2 → PASS |
| 16. Main Dashboard App | Done | 24 | 2 → PASS |
| 17. Seed Dataset (verified) | Done | 308 (no new tests) | 3 → PASS |
| 18. Update CLAUDE.md | Done | 308 (no new tests) | 1 → PASS |
| 19. E2E Smoke Test | Done | 28 | 2 → PASS |
| 20. CLI Ingestion Entry Point | Done | 25 | 4 → PASS |
| **Total** | **20/20** | **361** | |

---

## Session 6 — 2026-04-05 (continued)

### Phase: Bug Fix — H14, M16–M24

**Workflow:** Fix bugs in batches → codex audit each batch → update BUGLOG → next batch. Codex rescue agent used as gate auditor for every change.

#### H14: Batch-test RSS feeds in config (rounds 2–4)

Continued from prior session which had codex round 2 FAIL with 3 findings.

**Round 3 fixes:**
1. **HIGH — Ingestion parity:** Ported verifier's redirect (3xx), non-feed (empty `feedparser.version`), and non-200 success code (204/206) checks into `src/ingestion.py` so ingestion and verifier classify every HTTP status identically
2. **MEDIUM — Test gaps:** Added 3 verify_feeds tests: `test_verify_feed_bozo_has_entries`, `test_verify_feed_explicit_bozo_zero_entries`, `test_verify_feed_request_kwargs`
3. **MEDIUM — RSF reactivation:** RSF publishes per-country RSS at `/en/rss/{region}/{country}/feed.xml`. Updated from defunct `/en/news.xml` to working India feed (50 items). All 4 drill-down country feeds verified: IN, MY, NG, ZA

**Round 3 codex audit:** PASS
**Round 3 gate audit:** FAIL — found non-200 success codes (204/206) still diverged between verifier and ingestion

**Round 4 fix:** Added explicit `if response.status_code != 200: return ([], False)` in ingestion + test
**Round 4 gate audit:** PASS

- Files: `src/ingestion.py`, `scripts/verify_feeds.py` (unchanged), `config/feeds.yaml`, `tests/test_verify_feeds.py`, `tests/test_ingestion.py`
- Tests added: +20 (16 verify_feeds + 3 ingestion parity + 1 non-200)
- Final: 57/57 active feeds healthy, 410 tests passing

#### M18: Country and Date Range sidebar filters

- Updated `_render_sidebar(db)` to accept DB parameter
- Added Country selectbox (dynamically populated from `db.get_country_counts()`)
- Added Date From / Date To via `st.date_input` with UTC conversion
- Added pure helpers: `get_country_options()`, `parse_country_option()`
- Files: `dashboard/app.py`, `tests/test_dashboard_app.py`
- Tests added: +6
- Codex audit: PASS (416 tests)

#### M21-M22: Dashboard interaction bugs

**M21 — Article card clicks don't update detail panel:**
- Root cause: `_render_feed_and_detail()` rendered non-interactive HTML cards AND separate `st.button` elements. Users clicked HTML cards (no-op).
- Fix: Removed duplicate HTML card rendering, kept only interactive `st.button` list with `st.caption` metadata via new `format_article_meta()` helper.

**M22 — Drill-down global metrics persist:**
- Changed title to `st.title(f"Drill-Down: {country_name}")`
- Added country-specific metrics row (Flagged Articles, Categories, Avg Confidence)

- Files: `dashboard/app.py`, `tests/test_dashboard_app.py`
- Tests added: +3 (format_article_meta)
- Codex audit: FAIL (sandbox issue + false "dead code" finding on `render_news_feed` which is still tested). Gate audit: PASS (419 tests)

#### M23-M24: Test gap and drilldown bugs

**M23 — date_to and get_country_counts date filters untested:**
- Added `test_get_flagged_articles_date_to_filter` (date_to alone + combined)
- Added `test_get_country_counts_date_filters` (date_from, date_to, both)

**M24 — country_code=None articles leak into drilldown:**
- Simplified `map_drilldown.py` guard from `if article.country_code is not None and article.country_code != country_code` to `if article.country_code != country_code`
- Added `test_build_region_data_skips_none_country_code`

- Files: `dashboard/components/map_drilldown.py`, `tests/test_database.py`, `tests/test_map_drilldown.py`
- Tests added: +3
- Codex audit: PASS (422 tests)

#### Also fixed:
- **M2 BUGLOG typo:** Duplicate status line (both "Fixed" and "Open") — removed stale "Open" line

---

### Updated Progress Table

| Module | Status | Tests | Audit Rounds |
|--------|--------|-------|--------------|
| 1. Scaffolding | Done | 0 | 1 → PASS |
| 2. Data Models | Done | 16 | 2 → PASS |
| 3. Database | Done | 22 | 3 → PASS |
| 4. Config Files | Done | 28 | 4 → PASS |
| 5. Init/Seed Scripts | Done | 6 | 2 → PASS |
| 6. LLM Client | Done | 8 | 2 → PASS |
| 7. Classifier | Done | 21 | 7 → PASS |
| 8. Summarizer | Done | 12 | 2 → PASS |
| 9. Ingestion Worker | Done | 28 | 3 → PASS |
| 10. Dark Theme CSS | Done | 21 | 3 → PASS |
| 11. Global Map | Done | 25 | 4 → PASS |
| 12. Drill-down Map | Done | 21 | 2 → PASS |
| 13. News Feed + Detail | Done | 47 | 3 → PASS |
| 14. Feed URLs (verify) | Done | 44 | 4 → PASS |
| 15. Live Stream + Webcams | Done | 42 | 2 → PASS |
| 16. Main Dashboard App | Done | 36 | 2 → PASS |
| 17. Seed Dataset (verified) | Done | 308 (no new tests) | 3 → PASS |
| 18. Update CLAUDE.md | Done | 308 (no new tests) | 1 → PASS |
| 19. E2E Smoke Test | Done | 28 | 2 → PASS |
| 20. CLI Ingestion Entry Point | Done | 25 | 4 → PASS |
| **Total** | **20/20** | **422** | |

### Bug Status Summary

| Severity | Total | Fixed | Open (accepted) |
|----------|-------|-------|-----------------|
| CRITICAL | 2 | 2 | 0 |
| HIGH | 14 | 14 | 0 |
| MEDIUM | 25 | 22 | 3 (deliberate/accepted) |
| LOW | 18 | (not targeted this session) | — |

Open accepted MEDIUMs:
- M15: Delhi/Mumbai webcams show distant locations (no city-specific feeds available)
- M19: Map click-to-filter not implemented (deliberate — uses Streamlit buttons)
- M20: Seed count 79 vs 200 promised (scope reduction — quality over quantity)

---

## Session 7 — 2026-04-06

### Phase: Re-Audit Bug Fix Round 2

**Context:** A 7-agent re-audit of the codebase (after round 1 fixes) found 16 new issues:
1 HIGH (R1), 5 MEDIUM (R2–R6), 10 LOW (R7–R16). This session targets R1–R6.

**R1 (HIGH) — avg_conf denominator deflation with None confidence**
- `dashboard/app.py:333–337`: Replaced `sum(...) / len(articles)` with
  `conf_values = [a.confidence for a in articles if a.confidence is not None]`
  and `sum(conf_values) / len(conf_values) if conf_values else 0.0`
- Root cause: C2 fix introduced `confidence=None` for failed classifications,
  but avg_conf still divided by total article count including None entries

**R2 (MEDIUM) — Fragile string replacement in render_drilldown_html**
- `dashboard/static/deck_map.html`: Replaced hardcoded `latitude: 20, longitude: 30, zoom: 1.8,` with `__INITIAL_VIEW_STATE__` placeholder
- `dashboard/components/map_global.py`: Added `_DEFAULT_VIEW_STATE` constant,
  `render_map_html()` now replaces the placeholder
- `dashboard/components/map_drilldown.py`: `render_drilldown_html()` now
  replaces the placeholder with country-specific center coords

**R3 (MEDIUM) — get_country_counts TypeError with country_code**
- `dashboard/app.py:278`: Added `cc_params = {k: v for k, v in filter_params.items() if k != "country_code"}` before `get_country_counts(**cc_params)`
- Root cause: `build_filter_params()` returns `country_code` key when user
  selects a country, but `get_country_counts()` doesn't accept that parameter

**R4 (MEDIUM) — Country dropdown shows countries with no visible articles**
- `dashboard/app.py` sidebar: Reordered widgets — Category + Confidence slider
  now render before Country dropdown. Country dropdown populated using
  `min_confidence=min_confidence` (slider value) instead of `0.0`

**R5 (MEDIUM) — Seed article tier mismatches**
- `data/seed_articles.json`: Updated 5 articles:
  - Global Voices: tier 2 → 3
  - Global Voices Advox: tier 2 → 3 (codex primary audit finding)
  - South China Morning Post (×2): tier 2 → 4
  - Radio Free Asia: tier 2 → 3
- Added `test_seed_tiers_match_feeds_yaml_taxonomy` with sub-brand check

**R6 (MEDIUM) — Default provider inconsistency**
- `src/classifier.py:308`: Changed `llm_provider="default"` → `"none"` to
  match `src/ingestion.py:_default_result()`
- Updated 3 test assertions in `test_classifier.py`

**Also fixed:** R10 (LOW) — CLAUDE.md test count updated from 381 → 431.

### Tests Added (9 new → 431 total)
- `test_dashboard_app.py`: `test_avg_conf_excludes_none_confidence`,
  `test_avg_conf_all_none_returns_zero`, `test_filter_params_country_code_excluded_for_counts`,
  `test_get_country_counts_rejects_country_code_kwarg`
- `test_map_global.py`: `test_deck_map_html_has_view_state_placeholder`,
  `test_render_map_html_replaces_view_state_placeholder`
- `test_map_drilldown.py`: `test_render_drilldown_html_replaces_placeholder`
- `test_scripts.py`: `test_seed_tiers_match_feeds_yaml_taxonomy` (with sub-brand logic)
- `test_classifier.py`: `test_default_provider_consistency_between_ingestion_and_classifier`

### Audit Results
- **Codex primary audit:** PASS (all 6 fixes verified correct; found Global Voices
  Advox sub-brand at tier 2 — fixed; noted missing R4 regression test — added)
- **Codex gate audit:** PASS (no issues missed by primary; noted R4 category-not-passed
  to sidebar get_country_counts as pre-existing design choice, not regression)

### Bug Status Summary

| Severity | Total | Fixed | Open |
|----------|-------|-------|------|
| CRITICAL | 3 | 3 | 0 |
| HIGH | 15 | 15 | 0 |
| MEDIUM | 30 | 27 | 3 (accepted) |
| LOW | 28 | 2 | 26 |

Open accepted MEDIUMs (unchanged):
- M15: Delhi/Mumbai webcams show distant locations
- M19: Map click-to-filter not implemented (uses buttons)
- M20: Seed count 79 vs 200 promised (scope reduction)

## Project Status

All 20 modules implemented, audited, and passing. **431 tests** across 19 test files. All CRITICAL and HIGH bugs fixed (15/15). 27 of 30 MEDIUM bugs fixed (3 accepted deviations). Re-audit round fully resolved. The prototype supports seeded demo mode, live RSS ingestion (57 verified feeds), and full dashboard interactivity with country/date/category/confidence filters.

---

## Session 8 — 2026-04-07

### Phase: Multi-Agent Re-Evaluation After Major Code Update

**Workflow:** Re-read all current plan documents before inspecting code:
- `docs/plans/2026-03-31-surveillance-monitor-design.md`
- `docs/plans/2026-03-31-surveillance-monitor-implementation.md`
- `docs/plans/2026-04-07-command-center-redesign.md`

Then ran a four-agent read-only audit:
- A2 plan/design alignment monitor
- A3 code and error inspector
- A4 logic/integration inspector
- A5 anti-hallucination/reproducibility inspector

Each agent read the plans first, inspected code, then cross-checked the consolidated findings. No runtime code was changed.

### Local Verification

- `python -m pytest -q` — **693 passed in 4.15s**
- `python scripts/init_db.py --db /tmp/ai_surveillance_audit_2.db --config config/feeds.yaml --clean` — **60 active feeds loaded**
- Temp seed smoke — **79/79 articles seeded**, DB had **79 articles** and **60 active feeds**
- `python -m py_compile src/*.py scripts/*.py dashboard/app.py dashboard/components/*.py` — passed
- `python -m src.ingestion --once` — exits `0` but performs no work
- No live browser/RSS/YouTube network checks were run in this pass

### Cross-Checked Findings

**HIGH**
- Threshold enforcement still conflicts with the plan: classifier preserves raw `is_surveillance=True` below `0.6`, and ingestion summarizes on that raw flag. Tests currently encode the raw-preservation behavior.
- April 7 globe click-to-drilldown is not implemented: active JS has no polygon `onClick`, and `dashboard/app.py` ignores `render_globe()` return values.
- Classification failures are terminal on first attempt: `_default_result(llm_provider="failed")` plus `article_needs_classification()` prevents retry of transient malformed/empty LLM responses.

**MEDIUM**
- Global globe and global summary filter to `DRILL_DOWN_COUNTRIES`, hiding non-focus seed countries despite the April 7 "all article dots" requirement.
- Sidebar country filter is misleading in global view because global mode strips `country_code` and forces `country_codes=list(DRILL_DOWN_COUNTRIES)`.
- Live media remains brittle: direct video IDs are skipped by the resolver, fallback streams are configured but not automatically used, South Africa uses `africanews` rather than planned eNCA, and most "webcams" are news fallbacks or empty placeholders.
- GDELT enrichment is still unimplemented.
- `python -m src.ingestion --once` and `IngestionWorker.run_scheduled()` remain absent from `src.ingestion`; `scripts/run_ingestion.py` is the real CLI.

**LOW / ACCEPTED SCOPE**
- Seed dataset remains 79 rather than the original ~200 planned articles; now documented as an accepted quality-over-quantity scope reduction.
- Seed `fetched_at` uses load time rather than `published_at`; lower impact because dashboard queries use `published_at`.
- README/CLAUDE/BUGLOG contain stale test-count and dynamic-stream-resolution claims; `requirements.txt` omits plan-listed `pydeck` and `schedule`, likely acceptable because current code does not use them directly.

### Things Verified As Fixed/Consistent

- SQLite read-only dashboard connection, `busy_timeout`, and WAL write-mode handling are implemented.
- `get_flagged_articles()` and `get_country_counts()` default to `min_confidence=0.6`.
- DB date filters use `published_at`.
- Feed taxonomy is cleaner via `Feed.feed_type`; config has 64 feeds, 60 active.
- Admin-1 GeoJSON files and globe overlay plumbing exist for `IN/MY/NG/ZA`.
- Seed JSON loads idempotently and has no missing URLs or summaries.
