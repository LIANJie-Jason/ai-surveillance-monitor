# Command Center Redesign — Single-Window Dashboard

**Date:** 2026-04-07
**Status:** Approved

## Goal

Transform the current two-page Streamlit dashboard (global view → separate drilldown page) into a single-window command center layout inspired by WorldMonitor. Globe is always visible; clicking a focus country zooms in and reveals country-specific content in adjacent panels.

## Layout

```
┌──────────────────────────────────────────────────────────┐
│ AI Surveillance & Censorship Monitor │ metrics │ metrics  │
├─────────────────────┬────────────────────────────────────┤
│                     │ LIVE ANALYSIS (from DB)            │
│                     │ Category counts, key themes,       │
│  3D Globe           │ source tiers, confidence stats     │
│  (always visible)   ├────────────────────────────────────┤
│                     │ LIVE NEWS [channel name]      LIVE │
│  Auto-rotates on    │ (iframe embed)                     │
│  global view.       ├─────────┬──────────────────────────┤
│  Zooms + stops on   │ Cam 1   │ Cam 2                    │
│  country click.     ├─────────┼──────────────────────────┤
│  Shows admin-1      │ Cam 3   │ Cam 4                    │
│  overlay.           │         │                          │
├─────────────────────┴─────────┴──────────────────────────┤
│ Latest Articles (cards, filtered by country)        →    │
└──────────────────────────────────────────────────────────┘
```

## Key Design Decisions

1. **4 focus countries only:** IN, MY, NG, ZA. Global view shows all article dots but only these 4 are clickable. Filter sidebar and news feed scoped to these 4.

2. **Globe behavior:**
   - Global: auto-rotates continuously, shows scatter dots
   - Country click: animates to country center, stops rotation, overlays admin-1 GeoJSON boundaries
   - Back: resumes auto-rotation, removes admin-1 overlay

3. **Live Analysis panel:** Dynamically generated from DB articles for selected country:
   - Article count + date range
   - Category distribution (surveillance, censorship, facial_recognition, etc.)
   - Confidence statistics
   - Source tier breakdown
   - Key themes extracted from article titles

4. **Tight spacing:** 1px `#30363d` borders between sections. No padding > 8px. No blank space. Dark theme `#0d1117`.

5. **Data enrichment:** If article coverage is thin for a country, supplement with GDELT API queries for surveillance/censorship events.

6. **Bottom news feed:** Horizontal scrollable cards. Global view shows all; country view filters to selected country.

## Globe Changes

- Merge globe + choropleth into a single deck.gl component
- On country select: `flyTo()` animation to country center + zoom
- Add admin-1 GeoJSON as conditional overlay layer (only when country selected)
- Click handler returns country code to Python via Streamlit component protocol

## Files to Modify

| File | Change |
|------|--------|
| `dashboard/app.py` | Replace two-view layout with single-window sections |
| `dashboard/static/globe_component/index.html` | Add flyTo, admin-1 overlay, stop/resume rotation |
| `dashboard/components/map_globe.py` | Pass admin-1 data, handle zoom state |
| `dashboard/components/map_drilldown.py` | Merge into globe component (admin-1 overlay) |
| `dashboard/components/live_stream.py` | Minor — render in smaller panel |
| `dashboard/components/webcams.py` | Minor — render in smaller grid |
| `dashboard/components/analysis.py` | NEW — dynamic analysis from DB articles |
| `dashboard/styles/dark_theme.css` | Tighten spacing, add section borders |
