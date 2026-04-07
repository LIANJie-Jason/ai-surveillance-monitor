#!/usr/bin/env python3
"""Download and process Natural Earth GeoJSON data for dashboard visualization.

Produces:
  dashboard/static/geojson/countries_110m.geojson   -- world country boundaries
  dashboard/static/geojson/admin1_IN.geojson        -- India admin-1
  dashboard/static/geojson/admin1_MY.geojson        -- Malaysia admin-1
  dashboard/static/geojson/admin1_NG.geojson        -- Nigeria admin-1
  dashboard/static/geojson/admin1_ZA.geojson        -- South Africa admin-1
"""

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional: shapely for geometry simplification
# ---------------------------------------------------------------------------
try:
    from shapely.geometry import shape, mapping
    from shapely.validation import make_valid

    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "dashboard" / "static" / "geojson"

COUNTRIES_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_110m_admin_0_countries.geojson"
)
ADMIN1_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_10m_admin_1_states_provinces.geojson"
)

DRILLDOWN_COUNTRIES = ("IN", "MY", "NG", "ZA")
ISO2_PATTERN = re.compile(r"^[A-Z]{2}$")

# Douglas-Peucker tolerance in degrees (~0.01 for admin-1)
SIMPLIFY_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _download(url: str, label: str) -> dict:
    """Download a GeoJSON file and return parsed JSON dict."""
    print(f"  Downloading {label} ...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return resp.json()


def _valid_iso2(code: str) -> bool:
    """Return True if code is a valid 2-letter uppercase ISO code."""
    return isinstance(code, str) and bool(ISO2_PATTERN.match(code))


def _simplify_geometry(geom_dict: dict | None, tolerance: float) -> dict | None:
    """Simplify a GeoJSON geometry using Douglas-Peucker via shapely.

    Returns None for null geometries (valid per RFC 7946).
    Re-raises MemoryError. Logs and returns the original on other failures.
    """
    if geom_dict is None:
        return None
    if not HAS_SHAPELY:
        return geom_dict
    try:
        geom = shape(geom_dict)
        if not geom.is_valid:
            geom = make_valid(geom)
        simplified = geom.simplify(tolerance, preserve_topology=True)
        return mapping(simplified)
    except MemoryError:
        raise
    except Exception as exc:
        logger.warning(
            "Simplification failed for geometry (type=%s): %s — using original",
            geom_dict.get("type", "unknown"), type(exc).__name__,
        )
        return geom_dict


def _write_geojson(path: Path, feature_collection: dict) -> int:
    """Write a GeoJSON FeatureCollection to disk. Return file size in bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(feature_collection, f, ensure_ascii=False, separators=(",", ":"))
    return path.stat().st_size


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------
def process_countries(force: bool) -> Path:
    """Download and process world country boundaries (110m)."""
    out_path = OUTPUT_DIR / "countries_110m.geojson"

    if out_path.exists() and not force:
        print(f"  [skip] {out_path.name} already exists (use --force to regenerate)")
        return out_path

    raw = _download(COUNTRIES_URL, "110m countries")
    features = []

    for feat in raw.get("features", []):
        props = feat.get("properties", {})
        iso_a2 = props.get("ISO_A2", "")
        iso_a2_eh = props.get("ISO_A2_EH", "")

        # Compute fallback iso2
        iso2 = iso_a2 if _valid_iso2(iso_a2) else iso_a2_eh

        new_props = {
            "ISO_A2": iso_a2,
            "ISO_A2_EH": iso_a2_eh,
            "NAME": props.get("NAME", ""),
            "ADMIN": props.get("ADMIN", ""),
            "iso2": iso2,
        }

        features.append(
            {
                "type": "Feature",
                "properties": new_props,
                "geometry": feat.get("geometry"),
            }
        )

    fc = {"type": "FeatureCollection", "features": features}
    size = _write_geojson(out_path, fc)
    print(f"  Wrote {out_path.name} ({size:,} bytes, {len(features)} features)")
    return out_path


def process_admin1(force: bool) -> list[Path]:
    """Download and process admin-1 boundaries for drill-down countries."""
    out_paths = [OUTPUT_DIR / f"admin1_{cc}.geojson" for cc in DRILLDOWN_COUNTRIES]

    # Check if all outputs already exist
    all_exist = all(p.exists() for p in out_paths)
    if all_exist and not force:
        print("  [skip] All admin-1 files already exist (use --force to regenerate)")
        return out_paths

    raw = _download(ADMIN1_URL, "10m admin-1 states/provinces")

    # Bucket features by iso_a2
    buckets: dict[str, list] = {cc: [] for cc in DRILLDOWN_COUNTRIES}
    for feat in raw.get("features", []):
        props = feat.get("properties", {})
        iso = props.get("iso_a2", "")
        if iso in buckets:
            geometry = feat.get("geometry")
            simplified_geometry = _simplify_geometry(geometry, SIMPLIFY_TOLERANCE)
            # Skip features with null geometry (valid per RFC 7946 but
            # would cause silent rendering failures in deck.gl choropleth)
            if simplified_geometry is None:
                continue
            new_props = {
                "name": props.get("name", ""),
                "iso_a2": iso,
                "iso_3166_2": props.get("iso_3166_2", ""),
                "type_en": props.get("type_en", ""),
            }
            buckets[iso].append(
                {
                    "type": "Feature",
                    "properties": new_props,
                    "geometry": simplified_geometry,
                }
            )

    written = []
    for cc in DRILLDOWN_COUNTRIES:
        out_path = OUTPUT_DIR / f"admin1_{cc}.geojson"
        features = buckets[cc]
        fc = {"type": "FeatureCollection", "features": features}
        size = _write_geojson(out_path, fc)
        print(f"  Wrote {out_path.name} ({size:,} bytes, {len(features)} features)")
        written.append(out_path)

    return written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and process Natural Earth GeoJSON for dashboard."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate output files even if they already exist.",
    )
    args = parser.parse_args()

    print(f"Output directory: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not HAS_SHAPELY:
        print(
            "  [warn] shapely not available; admin-1 geometries will NOT be simplified"
        )

    # --- Step 1: World countries ---
    print("\n[1/2] World country boundaries (110m)")
    try:
        process_countries(args.force)
    except requests.RequestException as exc:
        print(f"  [ERROR] Failed to download countries: {exc}", file=sys.stderr)
        return 1

    # --- Step 2: Admin-1 for drill-down countries ---
    print("\n[2/2] Admin-1 boundaries for drill-down countries")
    try:
        process_admin1(args.force)
    except requests.RequestException as exc:
        print(f"  [ERROR] Failed to download admin-1 data: {exc}", file=sys.stderr)
        return 1

    # --- Summary ---
    print("\n--- Summary ---")
    for name in [
        "countries_110m.geojson",
        "admin1_IN.geojson",
        "admin1_MY.geojson",
        "admin1_NG.geojson",
        "admin1_ZA.geojson",
    ]:
        path = OUTPUT_DIR / name
        if path.exists():
            size = path.stat().st_size
            print(f"  {name:30s}  {size:>10,} bytes  ({size / 1024:.1f} KB)")
        else:
            print(f"  {name:30s}  MISSING")

    return 0


if __name__ == "__main__":
    sys.exit(main())
