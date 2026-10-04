"""export_cells_geojson.py — cells_full.parquet → GeoJSON for the web map.

The Next.js app renders the Cyprus grid on a MapLibre GL map. Parquet is
not web-friendly, so this converts the static cell geometry (cell_id, lat,
lon, district) to a GeoJSON FeatureCollection written into the web app's
public/ directory. The web app then fetches it as a static asset.

Why only these columns:
- lat/lon/district come from the Parquet (source of truth for geometry).
  The Sheets 'cells' tab has lat/lon SWAPPED — never use it for geometry.
- ML columns (culex_proba, aedes_proba, confidence_tier) are all NaN in the
  Parquet. The web app reads fresh predictions from Google Sheets and merges
  them client/server-side, so we do not duplicate them here.
- geometry_bounds is dropped: the grid is 500 m, so Point markers are
  visually adequate and keep the payload small.

Usage:
    .venv/bin/python export_cells_geojson.py
    .venv/bin/python export_cells_geojson.py --out /path/to/IDAIM-web/public/cells.geojson
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent

# Default output: the web app's public/ dir, created by create-next-app.
DEFAULT_OUT = Path.home() / "Personal Projects" / "IDAIM-web" / "public" / "cells.geojson"

# Cyprus land bbox — the app filters the map to this so sea cells and
# neighbouring countries are not drawn (see Dashboard _filter_cyprus_safe).
CYPRUS_LAT = (34.55, 35.70)
CYPRUS_LON = (32.40, 34.60)


def to_feature_collection(df: pd.DataFrame) -> dict:
    """Build a GeoJSON FeatureCollection with Point geometry.

    GeoJSON coordinates are [lon, lat] — the reverse of the Parquet column
    order. Getting this backwards is the single most common GeoJSON bug.
    """
    features = []
    for cell_id, lat, lon, district in zip(
        df["cell_id"].astype(int),
        df["lat"].astype(float),
        df["lon"].astype(float),
        df["district"].fillna("Unknown").astype(str),
    ):
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                "properties": {"cell_id": cell_id, "district": district},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(REPO / "data" / "cells_full.parquet"))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--no-bbox-filter", action="store_true",
                        help="Keep cells outside the Cyprus land bbox")
    args = parser.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    if not src.exists():
        print(f"FATAL: source parquet not found: {src}", file=sys.stderr)
        return 1

    print(f"Reading {src} ...")
    df = pd.read_parquet(src)
    print(f"  {len(df):,} cells, columns: {list(df.columns)}")

    if not args.no_bbox_filter:
        before = len(df)
        df = df[
            df["lat"].between(*CYPRUS_LAT)
            & df["lon"].between(*CYPRUS_LON)
        ]
        print(f"  bbox filter lat{CYPRUS_LAT} lon{CYPRUS_LON}: "
              f"{len(df):,} kept, {before - len(df):,} dropped")

    fc = to_feature_collection(df)

    out.parent.mkdir(parents=True, exist_ok=True)
    # Compact separators: this file is fetched by every map load.
    out.write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
    size_mb = out.stat().st_size / 1024 / 1024

    print(f"\nWrote {out}")
    print(f"  {len(fc['features']):,} features, {size_mb:.2f} MB")
    print(f"  first feature: {json.dumps(fc['features'][0])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
