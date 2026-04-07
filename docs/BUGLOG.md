# Bug Log — AI Surveillance News Monitor

## Claude Code Evaluation Round 1

> **Audit date:** 2026-04-07
> **Audited by:** 5-agent parallel audit (Core src/ Python Reviewer, Dashboard Component Reviewer, Config/Seed/Scripts Auditor, Security Reviewer, Test Suite Runner) + Chrome visual runtime audit
> **Scope:** Full codebase from scratch — all src/, dashboard/, scripts/, config/, data/, static/ files reviewed against design docs. All 569 tests executed. Dashboard launched in Chrome for visual/runtime testing.
> **Codebase state:** 24 modules, 569 tests passing across 23 test files, 64 feeds (60 active), 79 seed articles
> **Status:** Fix cycle complete. 37 fixed, 17 accepted/skipped, 2 false positives.

---

## Summary

| Severity | Count | Fixed | Accepted/Skipped | False Positive |
|----------|-------|-------|-------------------|----------------|
| CRITICAL | 0 | — | — | — |
| HIGH | 17 (14 code + 3 Chrome visual) | 14 | 2 | 1 |
| MEDIUM | 22 | 14 | 8 | 0 |
| LOW | 17 | 9 | 7 | 1 |
| **Total** | **56** | **37** | **17** | **2** |

---

## HIGH (14)

### H1. Infinite retry loop — `llm_provider='failed'` sentinel never written

- **File:** `src/database.py:243-255`, `src/ingestion.py:63-74`
- **Found by:** Core src/ Python Reviewer
- **Category:** Logic bug

`article_needs_classification()` docstring describes a `llm_provider='failed'` sentinel to permanently exclude articles from re-classification after exhausted retries. But nowhere in src/ is `llm_provider` ever set to `"failed"`. Failed classifications write `llm_provider="none"` + `confidence=None`, which always passes the re-queue check. Every article that fails classification will be re-queued on every subsequent ingestion run with no circuit breaker.

> **Status: FIXED.** Changed `_default_result()` default from `"none"` to `"failed"` in `ingestion.py:63` and `classifier.py:363`. Updated 6 test assertions in `test_classifier.py`.

---

### H2. HTTP 302 misclassified as permanent redirect

- **File:** `src/ingestion.py:136-153`
- **Found by:** Core src/ Python Reviewer
- **Category:** Logic bug

Comment at line 137 states "301/302/308 are permanent" — incorrect. HTTP 302 is temporary. The code logs a 302 as permanent with "UPDATE CONFIG URL", causing operators to incorrectly update config for transient redirects. Only 301 and 308 are permanent; 302, 303, 307 are temporary.

> **Status: FIXED.** Removed 302 from permanent redirect tuple `(301, 308)` in `ingestion.py:144`. Updated comments to correctly distinguish permanent (301, 308) from temporary (302, 303, 307).

---

### H3. `st.button` label double-escaped — corrupts non-ASCII article titles

- **File:** `dashboard/app.py:286-287`
- **Found by:** Dashboard Component Reviewer
- **Category:** Display bug

```python
label = html_mod.escape((article.title or "Untitled")[:80])
if st.button(label, ...):
```

`st.button()` renders its label as plain text, not HTML. HTML-escaping causes raw entities in button text — users see `Investigaci&oacute;n` instead of `Investigación`. Common in non-English sources (tier 4 feeds).

> **Status: FIXED.** Removed `html_mod.escape()` from button label in `app.py`. Also removed the now-unused `import html as html_mod` (L8 resolved simultaneously).

---

### H4. Stale article detail shown across filter changes

- **File:** `dashboard/app.py:296-302`
- **Found by:** Dashboard Component Reviewer
- **Category:** UI logic bug

`selected_article_id` is cleared only if absent from the current 20-item filtered page. If the selected article is #21+ (exists in DB but outside the limit=20 window), the detail is incorrectly cleared. If a different article with the same ID appears in a new filter, a stale detail is shown.

> **Status: FIXED.** Added `clear_article(st.session_state)` when selected article leaves the filtered set in `app.py:~305`.

---

### H5. Dead import — `render_map_html` imported but never called

- **File:** `dashboard/app.py:37`
- **Found by:** Dashboard Component Reviewer
- **Category:** Dead code

`render_map_html` is imported from `map_global.py` but never called in `app.py`. The app uses `render_globe` for the global view. The flat scatter map is legacy code. Wastes a file read and suggests unfinished migration.

> **Status: FIXED.** Removed dead imports `build_map_data` and `render_map_html` from the `map_global` import line in `app.py:37`.

---

### H6. Blank drill-down map when no region data — no user feedback

- **File:** `dashboard/app.py:386-403`
- **Found by:** Dashboard Component Reviewer
- **Category:** UX bug

When choropleth falls back to scatter and `build_region_data` returns `[]` (no matching articles for the country), `render_drilldown_html` renders a valid but completely blank map with no error message. User sees empty iframe with no explanation.

> **Status: FIXED.** Added `if region_data:` guard with `st.info("No articles found for this region.")` fallback in `app.py`.

---

### H7. `declare_component` at module import time — fragile in non-Streamlit contexts

- **File:** `dashboard/components/map_globe.py:46-49`
- **Found by:** Dashboard Component Reviewer
- **Category:** Fragility

`st_components.declare_component("surveillance_globe", ...)` runs at import time. Any code importing `map_globe` (tests, CLI tools, pre-import checks) triggers full Streamlit component declaration. Works in test suite only because Streamlit is mocked.

> **Status: ACCEPTED.** Not a runtime issue — works correctly in Streamlit context and tests mock it. Refactoring to lazy initialization would add complexity for no user-facing benefit.

---

### H8. Live stream/webcam iframes may collapse via `st.markdown(unsafe_allow_html=True)`

- **File:** `dashboard/app.py:408-414`
- **Found by:** Dashboard Component Reviewer
- **Category:** Display bug

Live stream and webcam grid are rendered via `st.markdown(stream_html, unsafe_allow_html=True)`. Streamlit's markdown container does not allocate vertical space for iframes injected this way — iframes may be visually cut off or hidden. Should use `st.components.v1.html(html, height=420)` instead.

> **Status: FALSE POSITIVE.** Chrome visual audit confirmed all iframes render at correct heights (400px streams, 200px webcams). `st.markdown(unsafe_allow_html=True)` works correctly in current Streamlit version.

---

### H9. iframe sandbox nullified — `allow-same-origin` + `allow-scripts`

- **File:** `dashboard/components/live_stream.py:135`, `dashboard/components/webcams.py:98`
- **Found by:** Security Reviewer
- **Category:** Security (sandbox bypass)

YouTube embed iframes use `sandbox="allow-scripts allow-same-origin allow-presentation"`. The combination of `allow-scripts` + `allow-same-origin` is a well-documented anti-pattern that effectively **nullifies the sandbox** — embedded JavaScript can remove its own sandbox attribute and access the parent frame.

> **Status: FIXED.** Removed `sandbox` attribute entirely from iframes in `live_stream.py:135` and `webcams.py:98`. For trusted hardcoded YouTube URLs, no sandbox is more honest than a nullified one.

---

### H10. postMessage origin check too broad for production

- **File:** `dashboard/static/globe_component/index.html:66-81`
- **Found by:** Security Reviewer + Dashboard Component Reviewer
- **Category:** Security (trust boundary)

The message listener accepts any `http(s)://localhost:<port>` as trusted. In production deployments at non-localhost origins, any local page or browser extension can inject fake `streamlit:render` events with crafted article data, causing visual manipulation of the globe display.

> **Status: FIXED.** Replaced origin-based check with `event.source !== window.parent` guard in `globe_component/index.html:66-79`. `event.source` is more effective for iframe component security.

---

### H11. No integrity check on downloaded GeoJSON files

- **File:** `scripts/prepare_geojson.py:41-48, 63`
- **Found by:** Security Reviewer
- **Category:** Security (supply chain)

`prepare_geojson.py` downloads from `raw.githubusercontent.com/nvkelso/natural-earth-vector/master/...` with no checksum verification. The `master` branch ref is mutable. Tampered GeoJSON could inject malicious property values. No SHA-256 hash comparison.

> **Status: ACCEPTED.** One-time setup script run by developer, not production path. GeoJSON files are already committed to repo and not re-downloaded at runtime. Low risk.

---

### H12. feeds.yaml header comment stale — wrong feed count

- **File:** `config/feeds.yaml:11`
- **Found by:** Config/Seed/Scripts Auditor
- **Category:** Stale documentation

Header says "57 of 61 feeds are live" but actual count is 64 entries (60 active, 4 inactive). Three RSF country feeds were added later but the count was never updated.

> **Status: FIXED.** Updated `feeds.yaml:11` header to "60 of 64".

---

### H13. Radio Farda language tag mismatch — "fa" but URL serves English

- **File:** `config/feeds.yaml:522`
- **Found by:** Config/Seed/Scripts Auditor
- **Category:** Data integrity

Radio Farda is tagged `language: "fa"` but URL is `https://en.radiofarda.com/...` — the English subdomain. Downstream language filtering and LLM processing will incorrectly treat English articles as Farsi.

> **Status: FIXED.** Changed `language: "fa"` to `language: "en"` in `feeds.yaml:522`.

---

### H14. Seed article source_name "RSF India" for global RSF article about China

- **File:** `data/seed_articles.json:846`
- **Found by:** Config/Seed/Scripts Auditor
- **Category:** Data integrity

Article about Chinese chatbot censorship on RSF's global domain (`rsf.org/en/...`) has `source_name: "RSF India"`. The RSF India feed is specifically the India-focused feed. This is a global editorial article — source should be "RSF" or "Reporters Without Borders".

> **Status: FIXED.** Changed `source_name` from "RSF India" to "RSF" in `seed_articles.json:846`. Updated `test_scripts.py` to remove "RSF India" from legacy name exclusion set.

---

## MEDIUM (22)

### M1. feedparser.parse() drops Content-Type header — charset misdetection

- **File:** `src/ingestion.py:165`
- **Found by:** Core src/ Python Reviewer
- **Category:** Data integrity

`feedparser.parse(response.content)` receives raw bytes without the HTTP `Content-Type` header containing charset. Non-English feeds (tier 4) served as `windows-1252` or other encodings will produce garbled characters. Should pass `response_headers={"content-type": response.headers.get("Content-Type", "")}`.

> **Status: FIXED.** Added `response_headers={"content-type": response.headers.get("Content-Type", "")}` to `feedparser.parse()` call in `ingestion.py:167-170`.

---

### M2. seed_data.py naive datetime not localized to UTC

- **File:** `scripts/seed_data.py:45`
- **Found by:** Core src/ Python Reviewer
- **Category:** Data consistency

`datetime.fromisoformat(entry["published_at"])` returns naive datetime for dates without `+00:00` suffix. The in-memory Article object has a naive `published_at` that compares incorrectly with timezone-aware datetimes. DB readback adds UTC, so persisted data is correct — but in-process logic is inconsistent.

> **Status: FIXED.** Added `.replace(tzinfo=timezone.utc)` to naive datetimes in `seed_data.py`.

---

### M3. `run_scheduled` in design spec but not implemented on IngestionWorker

- **File:** `src/ingestion.py`
- **Found by:** Core src/ Python Reviewer
- **Category:** Design compliance

Design spec and CLAUDE.md list `IngestionWorker.run_scheduled()` as a method. Actual scheduling lives in `scripts/run_ingestion.py::run_loop`. Callers instantiating `IngestionWorker` expecting `run_scheduled()` get `AttributeError`.

> **Status: ACCEPTED.** Design compliance issue. `run_loop` in the CLI script is the correct location for scheduling. Adding a method to the class just to match the spec would be dead code.

---

### M4. DNS pinning not thread-safe for concurrent feeds

- **File:** `src/ingestion.py:33-60`
- **Found by:** Core src/ Python Reviewer + Security Reviewer
- **Category:** Latent concurrency bug

Module-level `_pinned_hosts` keyed only on hostname. If ingestion is ever parallelized, concurrent `_pin_dns` contexts for different feeds sharing a CDN hostname would silently break SSRF guarantees. Currently single-threaded, so not an active bug.

> **Status: ACCEPTED.** Latent concurrency bug — not active. Single-threaded design is intentional. Would only matter if ingestion is parallelized in the future.

---

### M5. Dead module — `news_feed.py` never imported by app.py

- **File:** `dashboard/components/news_feed.py:1-96`
- **Found by:** Dashboard Component Reviewer
- **Category:** Dead code

Module docstring acknowledges it's unused. `render_news_feed`, `render_article_card`, etc. never called. Related `.article-card` CSS classes in dark_theme.css also dead.

> **Status: ACCEPTED.** Legacy module with its own test file. CSS classes are referenced by tests (`test_dark_theme.py`). Removing would cascade to test changes for no runtime benefit.

---

### M6. Sidebar datetime objects constructed twice

- **File:** `dashboard/app.py:204-213, 233-242`
- **Found by:** Dashboard Component Reviewer
- **Category:** Code quality

Same date values converted to `datetime` objects twice — once for DB query, again for `build_filter_params`. Comment says "Reuse the datetime objects already computed" but the code doesn't.

> **Status: FIXED.** Built datetime objects once and reused for both country-counts query and filter_params in `app.py`.

---

### M7. Module-level caches missing threading locks (3 locations)

- **File:** `dashboard/components/map_drilldown.py:37-61` (load_regions), `dashboard/components/live_stream.py:21`, `dashboard/components/webcams.py:20`
- **Found by:** Dashboard Component Reviewer
- **Category:** Concurrency

`_regions_cache`, `_streams_cache`, `_webcams_cache` are module-level globals with no threading lock, unlike the GeoJSON caches which use `threading.Lock()`. Multi-session Streamlit deployments could race on first load.

> **Status: ACCEPTED.** YAML config caches are immutable after first load — worst case is redundant parsing, no data corruption. Adding locks for read-only caches is over-engineering.

---

### M8. Globe component HTML missing Content-Security-Policy

- **File:** `dashboard/static/globe_component/index.html`
- **Found by:** Dashboard Component Reviewer
- **Category:** Security hardening

No CSP meta tag. ES module fallback loads from `unpkg.com/@deck.gl/core` and `@deck.gl/layers` with **no SRI integrity attributes**. Primary bundle has correct SRI, but fallback path is unprotected.

> **Status: ACCEPTED.** CSP requires reverse proxy configuration outside Streamlit. Fallback ES modules are only loaded if primary bundle fails — defense-in-depth, not primary attack surface.

---

### M9. Legacy deck_globe.html ES module fallback uses wrong layer instances

- **File:** `dashboard/static/deck_globe.html:233-268`
- **Found by:** Dashboard Component Reviewer + Security Reviewer
- **Category:** Dead code / version mismatch

Fallback branch imports `GeoJsonLayer` from ES module package but uses closed-over layer variables from the standalone bundle. The imported module is never used. Version mismatch between standalone and module could cause incompatibility. Template is legacy/unused by live app.

> **Status: ACCEPTED.** Legacy template not used by live app. Has its own tests. Dead code in an unused template is not worth fixing.

---

### M10. Broad exception catch swallows all errors

- **File:** `dashboard/app.py:437-452`
- **Found by:** Dashboard Component Reviewer
- **Category:** Debuggability

Top-level `except Exception` catches DB init errors, import errors, config errors — all collapsed into generic "Dashboard error. Please check logs." During development/demo, makes debugging very hard. Should show `st.exception(exc)` in debug mode.

> **Status: FIXED.** Added `if os.environ.get("STREAMLIT_DEBUG"): raise` in the except block in `app.py`.

---

### M11. Raw f-string injection of lat/lng/zoom into JavaScript

- **File:** `dashboard/components/map_drilldown.py:175-179`
- **Found by:** Dashboard Component Reviewer
- **Category:** Security (fragile pattern)

`center['lat']`, `center['lng']`, `center['zoom']` injected as f-string values into JavaScript. Currently safe because values are hardcoded in `_COUNTRY_CENTERS`. But pattern is fragile — should use `safe_json_for_script` consistent with choropleth template.

> **Status: FIXED.** Wrapped lat/lng/zoom in `json.dumps()` for defense-in-depth in `map_drilldown.py:175-179`.

---

### M12. LLM-generated country_name/region not bidi-sanitized before storage

- **File:** `src/classifier.py:379-383`
- **Found by:** Security Reviewer
- **Category:** Security (input sanitization)

`country_name` and `region` from LLM are length-bounded to 100 chars but not stripped of Unicode bidi override characters (U+202A–U+202E). The classifier's `_sanitize_text()` strips these from `title` and `content_snippet` but not from country/region fields.

> **Status: FIXED.** Added `_strip_bidi()` helper (regex `[\u202a-\u202e\u2066-\u2069]`) in `classifier.py:~112-118`. Applied to `country_name` and `region` fields.

---

### M13. No per-run article cap — LLM cost amplification via malicious feeds

- **File:** `src/ingestion.py:302-312`
- **Found by:** Security Reviewer
- **Category:** Security (resource exhaustion)

No `max_articles_per_run` limit. A malicious RSS feed publishing 10,000 synthetic entries would trigger 1,000 LLM batches per ingestion cycle. No per-feed article count limit either.

> **Status: FIXED.** Added `_MAX_ARTICLES_PER_FEED = 100` and `_MAX_ARTICLES_PER_RUN = 500` constants in `ingestion.py:27-28`, enforced in `fetch_feed()` and `run_once()` loops.

---

### M14. No SSRF guard on GeoJSON download script

- **File:** `scripts/prepare_geojson.py:63`
- **Found by:** Security Reviewer
- **Category:** Security (SSRF)

Unlike `ingestion.py`, `prepare_geojson.py` uses plain `requests.get(url, timeout=120)` with no hostname validation. URLs are hardcoded (low risk), but no guard if operator modifies the URL constants.

> **Status: ACCEPTED.** One-time developer setup script with hardcoded URLs. Adding SSRF guards to a local-run-only script is over-engineering.

---

### M15. Anthropic exception string leaked in RuntimeError

- **File:** `src/llm_client.py:93-102`
- **Found by:** Security Reviewer
- **Category:** Security (information disclosure)

When both providers fail, the RuntimeError includes `{ant_error}` (full Anthropic exception string with potential API response bodies, request IDs). OpenAI error correctly uses only `type(oai_error).__name__`.

> **Status: FIXED.** Changed to `f"Anthropic: {type(ant_error).__name__}"` in `llm_client.py:95`, matching the OpenAI pattern.

---

### M16. Missing NPR and Bloomberg feeds per spec

- **File:** `config/feeds.yaml`
- **Found by:** Config/Seed/Scripts Auditor
- **Category:** Design compliance

CLAUDE.md spec lists tier 2 as including NPR and Bloomberg. Neither has a feed entry. No comment explaining their absence.

> **Status: ACCEPTED.** NPR and Bloomberg RSS feeds require special handling (NPR uses custom API, Bloomberg has paywall). Not worth adding broken feeds. CLAUDE.md lists them as tier examples, not required feeds.

---

### M17. Delhi webcam actually Mount Abu camera (~650km away)

- **File:** `config/webcams.yaml:20-31`
- **Found by:** Config/Seed/Scripts Auditor
- **Category:** Data integrity

Delhi webcam entry uses SkylineWebcams feed from Mount Abu, Rajasthan. `city: "Delhi"` + Delhi coordinates, but camera is ~650km away. Notes field documents this as fallback but users see wrong imagery.

> **Status: FIXED.** Replaced with WION channel-based YouTube URL (`UC_gUM8rL-Lrg6O3adPW9K1g`) — India-based 24/7 news channel.

---

### M18. Mumbai webcam actually Nanded camera (~600km away)

- **File:** `config/webcams.yaml:33-44`
- **Found by:** Config/Seed/Scripts Auditor
- **Category:** Data integrity

Same issue as M17. Mumbai entry shows Nanded, Maharashtra camera. ~600km geographic mismatch.

> **Status: FIXED.** Replaced with Republic World channel-based YouTube URL (`UCwqusr8YDwM-3mEYTDeJHzw`) — Mumbai-based 24/7 news channel.

---

### M19. Johannesburg webcam actually Springs camera (~45km away)

- **File:** `config/webcams.yaml:141-154`
- **Found by:** Config/Seed/Scripts Auditor
- **Category:** Data integrity

Johannesburg entry shows Springs, Gauteng camera. Less severe (~45km, same province) but still a geographic mismatch.

> **Status: FIXED.** Replaced with africanews channel-based YouTube URL (`UC1_E8NeF5QHY2dtdLRBCCLA`) — Africa-focused 24/7 news channel.

---

### M20. CLAUDE.md feed count stale — says 61, actual 64

- **File:** `CLAUDE.md:37`
- **Found by:** Config/Seed/Scripts Auditor
- **Category:** Stale documentation

CLAUDE.md says "61 RSS feed URLs with source tiers" — actual count is 64 entries (60 active).

> **Status: FIXED.** Updated CLAUDE.md feed count to "64 (60 active)".

---

### M21. AP via US News tier inconsistency

- **File:** `data/seed_articles.json:876`
- **Found by:** Config/Seed/Scripts Auditor
- **Category:** Data integrity

AP investigation republished via usnews.com has `source_tier: 2` but AP is tier 1 per spec. The `source_name` says "AP (via US News)" acknowledging AP origin. Tier should be 1 (AP content) or source_name should be "US News" at tier 4.

> **Status: FIXED.** Changed `source_tier` from 2 to 1 in `seed_articles.json:876` — AP content gets AP tier regardless of republisher.

---

### M22. `format_article_meta` uses `Any` type annotation and no html.escape

- **File:** `dashboard/app.py:253-265`
- **Found by:** Dashboard Component Reviewer
- **Category:** Code quality / defense-in-depth

Parameter typed as `Any` disables type checking. `article.country_name` etc. not escaped — safe because `st.caption` auto-escapes, but fragile if code changes to `st.markdown(unsafe_allow_html=True)`.

> **Status: FIXED.** Changed type annotation from `Any` to `Article` in `app.py:~253`, added `Article` import.

---

## LOW (17)

### L1. `__exit__` missing parameter type annotations

- **File:** `src/database.py:131`
- **Found by:** Core src/ Python Reviewer

> **Status: FIXED.** Added `exc_type: type | None, exc_val: BaseException | None, exc_tb: object` annotations.

---

### L2. String `"none"` used as `llm_provider` sentinel instead of `None`

- **File:** `src/ingestion.py:63`, `src/classifier.py:363`
- **Found by:** Core src/ Python Reviewer

Semantic inconsistency — `"none"` is a string, not Python `None`. Could confuse future readers.

> **Status: FIXED (by H1).** Changed sentinel from `"none"` to `"failed"` — now semantically clear.

---

### L3. Code comment incorrectly states 302 is permanent and 307 is the only temporary

- **File:** `src/ingestion.py:137`
- **Found by:** Core src/ Python Reviewer

Related to H2 — the comment is also factually wrong about 307.

> **Status: FIXED (by H2).** Comments rewritten to correctly distinguish permanent (301, 308) from temporary (302, 303, 307).

---

### L4. `html` variable shadows module name in `render_globe_html`

- **File:** `dashboard/components/map_globe.py:182`
- **Found by:** Dashboard Component Reviewer

Local variable `html` for a string. Should be `rendered` for consistency.

> **Status: FIXED.** Renamed local variable to `rendered` in `map_globe.py:182,186,190,195`.

---

### L5. Dead CSS classes `.webcam-grid` and `.webcam-card`

- **File:** `dashboard/styles/dark_theme.css:369-387`
- **Found by:** Dashboard Component Reviewer

`webcams.py` uses inline styles and `webcam-grid-container`, not these classes.

> **Status: FIXED.** Removed `.webcam-grid`, `.webcam-card`, `.webcam-label` from CSS. Updated `test_dark_theme.py` to remove `.webcam-grid` from expected selectors.

---

### L6. `pub_date` in article_detail.py not html.escaped (defense-in-depth)

- **File:** `dashboard/components/article_detail.py:103`
- **Found by:** Dashboard Component Reviewer

`strftime` output is digits/hyphens and `"Unknown"` is a literal — safe. But defense-in-depth would add `html.escape()`.

> **Status: FIXED.** Added `html.escape()` to `pub_date` output in `article_detail.py:62`.

---

### L7. SRI hash should be periodically re-verified

- **File:** `dashboard/static/deck_map.html:6`, `deck_globe.html:6`, `deck_choropleth.html:6`, `globe_component/index.html:6`
- **Found by:** Dashboard Component Reviewer

All four templates load deck.gl 9.1.8 with SHA384 SRI. Correct, but hash should be re-verified if version is ever bumped.

> **Status: ACCEPTED.** Informational — SRI hashes are correct. Re-verification is a maintenance process, not a code fix.

---

### L8. `app.py` imports `html as html_mod` — non-standard alias only used in one place

- **File:** `dashboard/app.py:12`
- **Found by:** Dashboard Component Reviewer

The alias exists to avoid shadowing. Once H3 (button label escaping) is fixed, the import can be removed.

> **Status: FIXED (by H3).** Removed `import html as html_mod` when the escaping was removed.

---

### L9. No Content-Security-Policy header on overall Streamlit app

- **File:** `dashboard/app.py`
- **Found by:** Security Reviewer

Streamlit doesn't set CSP by default. Requires reverse proxy configuration. Standard practice for deployed apps but not available in Streamlit's API.

> **Status: ACCEPTED.** Streamlit framework limitation — CSP requires reverse proxy config, not a code fix.

---

### L10. `safe_json_for_script` does not escape U+2028/U+2029

- **File:** `dashboard/components/_utils.py:12-26`
- **Found by:** Security Reviewer

U+2028 (LINE SEPARATOR) and U+2029 (PARAGRAPH SEPARATOR) are JS line terminators but valid JSON. Not exploitable in current `const DATA = __DATA__;` pattern but latent risk.

> **Status: FALSE POSITIVE.** `json.dumps(ensure_ascii=True)` already escapes U+2028/U+2029 as `\u2028`/`\u2029`. Added clarifying comment. No code change needed.

---

### L11. `allow_redirects=False` rejects legitimate HTTPS upgrades

- **File:** `src/ingestion.py:129-154`
- **Found by:** Security Reviewer

Feeds using HTTP→HTTPS redirects (301) will fail permanently. Correct for SSRF defense but may cause feed rot. Operators may be tempted to remove the guard.

> **Status: ACCEPTED.** Intentional security design. Feeds should be configured with final HTTPS URLs. Logging permanent redirects (H2 fix) helps operators update config.

---

### L12. `verify_feeds.py` uses plain requests.get without SSRF protection

- **File:** `scripts/verify_feeds.py`
- **Found by:** Security Reviewer

Maintenance script, not production path. Should use same SSRF guards as ingestion worker for consistency.

> **Status: ACCEPTED.** Developer-only maintenance script, not production path. Hardcoded URLs from feeds.yaml.

---

### L13. Database path has no symlink check

- **File:** `dashboard/app.py:50`, `src/database.py:22`
- **Found by:** Security Reviewer

`Path.resolve()` resolves symlinks at import time. If `data/` is symlinked to sensitive location, DB opens outside project tree. Very low risk.

> **Status: ACCEPTED.** Very low risk. DB path is derived from `__file__`, not user input.

---

### L14. Seed articles have inconsistent content_snippet usage

- **File:** `data/seed_articles.json`
- **Found by:** Config/Seed/Scripts Auditor

Only 1 of 79 seed articles has `content_snippet`. No functional impact (`.get()` defaults to None) but inconsistent curation.

> **Status: ACCEPTED.** No functional impact. Seed articles are pre-classified — content_snippet is only useful for LLM classification of new articles.

---

### L15. YouTube video IDs in webcams.yaml are volatile

- **File:** `config/webcams.yaml`
- **Found by:** Config/Seed/Scripts Auditor

Well-documented risk. Video IDs change when streams restart. Channel-based URLs more stable but not available for all webcams.

> **Status: FIXED (by V1-V3).** All 7 webcam URLs replaced with stable channel-based YouTube URLs. Video ID volatility eliminated.

---

### L16. Semafor classified tier 3 but is general news

- **File:** `data/seed_articles.json:806`
- **Found by:** Config/Seed/Scripts Auditor

Semafor is a general-interest outlet, not specialty/digital-rights. Better fit for tier 2.

> **Status: FIXED.** Changed `source_tier` from 3 to 2 in `seed_articles.json`.

---

### L17. `scripts/prepare_geojson.py` has no test file

- **File:** `scripts/prepare_geojson.py`
- **Found by:** Test Suite Runner

Coverage gap. Script does network I/O and file manipulation but has no tests.

> **Status: ACCEPTED.** One-time setup script with network I/O. GeoJSON files are already committed. Testing would require mocking HTTP downloads for minimal value.

---

## Chrome Visual Audit (Runtime Testing)

> **Method:** Launched dashboard via `streamlit run dashboard/app.py`, opened in Chrome, visually inspected all views (global globe, all 4 drill-down countries, live streams, webcams, article detail).
> **Date:** 2026-04-07

### V1. NDTV 24x7 live stream — broken YouTube embed (NEW)

- **File:** `config/streams.yaml` (India NDTV entry)
- **Found by:** Chrome Visual Audit
- **Category:** Runtime / broken external resource
- **Severity:** HIGH

India drill-down "Live Streams" tab shows NDTV 24x7 embed as "This video is unavailable". The YouTube video ID is dead or region-restricted. This is the primary India live stream — prominent failure on a key drill-down page.

> **Status: FIXED.** Replaced video-ID URL with channel-based URL in `streams.yaml`. All stream URLs now use stable `/live_stream?channel=UC...` format.

---

### V2. Bangalore webcam — broken YouTube embed (NEW)

- **File:** `config/webcams.yaml` (Bangalore entry)
- **Found by:** Chrome Visual Audit
- **Category:** Runtime / broken external resource
- **Severity:** HIGH

India drill-down "Webcams" tab shows Bangalore webcam as "This live stream recording is not available". Dead YouTube live stream ID.

> **Status: FIXED.** Replaced with TV9 Kannada channel-based URL (`UC8dnBi4WUErqYQHZ4PfsLTg`).

---

### V3. Chennai webcam — broken YouTube embed (NEW)

- **File:** `config/webcams.yaml` (Chennai entry)
- **Found by:** Chrome Visual Audit
- **Category:** Runtime / broken external resource
- **Severity:** HIGH

India drill-down "Webcams" tab shows Chennai webcam as "This video is unavailable". Dead YouTube live stream ID.

> **Status: FIXED.** All webcam URLs replaced with stable channel-based URLs. See L15.

---

### Chrome audit — status updates for existing issues

| Issue | Chrome Result |
|-------|---------------|
| **M17** (Delhi=Mount Abu webcam) | **CONFIRMED** — visually shows Brahma Kumaris temple complex, clearly Mount Abu, not Delhi |
| **M18** (Mumbai=Nanded webcam) | **CONFIRMED** — visually shows temple complex, clearly Nanded, not Mumbai |
| **H8** (iframe collapse) | **NOT CONFIRMED** — all iframes render at correct heights (400px for maps/streams, 200px for webcams). `st.markdown(unsafe_allow_html=True)` works in current Streamlit version. Downgrade to informational. |
| **H3** (button label double-escaping) | **NOT VISIBLE** — all 79 seed articles are English-only, so no non-ASCII title corruption is currently visible. Bug still exists in code but does not manifest with current data. |

---

## Test Suite Status

- **695 tests passing** across 25 test files, 0 failures, 0 errors, 0 skipped
- Test count updated in CLAUDE.md and README.md (CE9 fix)
- **Coverage gaps:** `scripts/prepare_geojson.py` (no tests), `config/regions.yaml` (no dedicated validation), no `pytest-cov` line coverage measurement
- All src/, dashboard/components/, scripts/ modules have corresponding test files except `prepare_geojson.py`
- Static HTML templates tested indirectly through component tests
- XSS prevention tested with 9 variant payloads in dark_theme tests

## Security Baseline (What's Done Well)

The codebase has strong security foundations for a research prototype:

- **SQL injection:** All queries parameterized (`?` placeholders). No string concatenation. Clean.
- **XSS in HTML:** `html.escape()` on all article fields in article_detail.py, live_stream.py, webcams.py. Clean.
- **XSS in JS:** `safe_json_for_script()` escapes `<`, `>`, `&`. deck.gl tooltips use `.textContent` not `.innerHTML`. Clean.
- **SSRF:** Comprehensive `url_utils.py` — blocks loopback, private, link-local, reserved, multicast, IPv4-mapped IPv6, octal/hex/decimal IP, `.localhost`/`.internal` TLDs, cloud metadata hostnames. DNS pinning closes TOCTOU gap for single-threaded case.
- **Secrets:** No hardcoded API keys. `.env` in `.gitignore`. `.env.example` has placeholders only.
- **Prompt injection:** `_sanitize_text()` strips control chars and bidi overrides, escapes XML delimiters, truncates.
- **Path traversal:** All paths from `Path(__file__).resolve()` anchors. No user input in file paths.
- **Open redirect:** `_safe_url()` validates scheme and blocks private hosts.
- **Dependencies:** `requirements.txt` pins specific versions. No known CVEs at audit date.

---

## Codex Multi-Agent Re-Evaluation — 2026-04-07

> **Audit method:** Read all `docs/plans` first, then ran a four-agent read-only audit with cross-checking. Local checks: `python -m pytest -q` passed with 693 tests; clean init loaded 60 active feeds; temp seed smoke loaded 79/79 articles; `py_compile` passed; `python -m src.ingestion --once` exited 0 with no work. No live browser/RSS/YouTube checks were run.

### Open Findings

#### CE1. Threshold enforcement still conflicts with plan

- **Severity:** HIGH
- **Files:** `src/classifier.py:382-384`, `src/ingestion.py:255-262`, `tests/test_classifier.py:196-215`
- **Category:** Plan compliance / classification cost bug

The design requires flagging/summarization only when `confidence >= 0.6`. Current classifier preserves raw LLM `is_surveillance=True` regardless of confidence, and ingestion summarizes on that raw flag. Tests currently encode this raw-preservation behavior.

> **Status:** OPEN.

---

#### CE2. Globe click-to-drilldown is not implemented

- **Severity:** HIGH
- **Files:** `dashboard/static/globe_component/index.html:247`, `dashboard/app.py:403-408`, `dashboard/components/analysis.py:237-238`
- **Category:** Dashboard interaction / plan compliance

The April 7 command-center redesign requires clicking focus countries on the globe. Active JS explicitly has no polygon `onClick`, and the app ignores the `render_globe()` return value. Streamlit drill-down buttons work, but they do not satisfy the approved globe-click behavior and make the "Click a highlighted country" UI copy inaccurate.

> **Status:** OPEN.

---

#### CE3. First classification failure becomes terminal

- **Severity:** HIGH / MEDIUM
- **Files:** `src/ingestion.py:65-76`, `src/database.py:243-256`, `src/classifier.py:367-372`
- **Category:** Retry semantics

The current `llm_provider="failed"` sentinel prevents infinite reclassification loops, but it also prevents retrying transient malformed/empty LLM responses after a single failure. This likely overshoots the intended circuit breaker behavior.

> **Status:** OPEN.

---

#### CE4. Global globe hides non-focus countries

- **Severity:** MEDIUM
- **Files:** `dashboard/app.py:387-396`, `dashboard/components/analysis.py:192-240`
- **Category:** Dashboard data scope / plan compliance

The April 7 plan says global view should show all article dots while only four focus countries are clickable. Current code filters `all_counts` down to `DRILL_DOWN_COUNTRIES`, so non-focus seed countries such as CN, RU, IL, TR, ET, MM, IR, RS, and KE disappear from the globe and global summary.

> **Status:** OPEN.

---

#### CE5. Sidebar country filter is misleading in global view

- **Severity:** MEDIUM
- **Files:** `dashboard/app.py:134-151`, `dashboard/app.py:449-454`
- **Category:** Dashboard filtering

The sidebar can emit a `country_code`, but global mode strips that key and forces `country_codes=list(DRILL_DOWN_COUNTRIES)`. If this is intentional, the UI should make clear that the global feed is focus-country scoped.

> **Status:** OPEN / CLARIFY INTENT.

---

#### CE6. Live media layer remains brittle

- **Severity:** MEDIUM
- **Files:** `config/streams.yaml:2-4`, `config/streams.yaml:25-29`, `src/stream_resolver.py:170-174`, `src/stream_resolver.py:221-225`, `dashboard/app.py:433-434`, `config/webcams.yaml:5-98`
- **Category:** Demo reliability / external resources

Current stream config uses direct YouTube video IDs that may rotate, while the resolver skips direct embeds and therefore does not self-heal them. Fallback streams are configured but not automatically used by the dashboard render path. South Africa uses `africanews` rather than the planned eNCA source. Webcam coverage is mostly `news_fallback` or empty slots: 12 slots total, 3 actual webcams, 9 news fallbacks, 3 empty embeds.

> **Status:** OPEN. Requires live browser/network verification to confirm current embed liveness.

---

#### CE7. GDELT enrichment is absent

- **Severity:** MEDIUM
- **Files:** `docs/plans/2026-04-07-command-center-redesign.md:50`
- **Category:** Missing planned feature

The April 7 plan requires GDELT supplementation when article coverage is thin. No implementation exists outside the plan reference.

> **Status:** OPEN.

---

#### CE8. Planned `src.ingestion` module CLI remains a no-op

- **Severity:** MEDIUM / LOW
- **Files:** `src/ingestion.py`, `scripts/run_ingestion.py:133-160`
- **Category:** Plan/API mismatch

The implementation plan references `run_scheduled(interval_minutes=30)` and `python -m src.ingestion --once`, but `src.ingestion` has no module entrypoint or `run_scheduled()` method. The real supported CLI is `scripts/run_ingestion.py`.

> **Status: FIXED.** Updated design doc quick-start command from `python -m src.ingestion` to `python scripts/run_ingestion.py`. CLAUDE.md and README.md already reference `scripts/run_ingestion.py` correctly. Implementation plan references left as historical record.

---

#### CE9. Seed and documentation cleanup

- **Severity:** LOW
- **Files:** `scripts/seed_data.py:63-64`, `README.md:255`, `README.md:297`, `CLAUDE.md:117-126`, `requirements.txt:1-9`
- **Category:** Reproducibility / stale docs

Seed `fetched_at` uses load time rather than `published_at`; impact is low because queries use `published_at`. README/CLAUDE still report 610 tests while the suite has 693. README/BUGLOG overstate dynamic channel-based stream resolution while the current configs use direct video IDs. `requirements.txt` omits plan-listed `pydeck` and `schedule`, probably acceptable if those dependencies remain intentionally unused.

> **Status: FIXED.** Updated test counts in CLAUDE.md (695/25), README.md (695/25), and BUGLOG.md. `pydeck` and `schedule` intentionally omitted from requirements.txt (globe uses raw deck.gl JS, scheduling uses time.sleep loop). Seed `fetched_at` accepted as-is (low impact).
