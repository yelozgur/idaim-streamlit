"""fetch_gee_features.py — Fill missing GEE features in features_cache_active.parquet.

For the 4,685 cells in cells_full.parquet that are NOT in
features_cache_active.parquet, fetch 5 dynamic features × 12 months from
Google Earth Engine (year=2024 per ALPHAEARTH_YEAR), reorder to the
June→May column order used by the existing cache, then merge and save.

GEE strategy: server-side batch. For each of 5 features, build 12
monthly-mean images, stack into a 12-band image, then `sampleRegions`
once over all points. Result: 5 GEE calls for N points (instead of N
calls per feature). 4,685 cells = ~30s.

Re-runnable: re-running finds any cells in cells_full.parquet that
still lack features (covers incremental use case — e.g. new cells added
to the Cyprus grid later).

Usage:
    .venv/bin/python fetch_gee_features.py
    .venv/bin/python fetch_gee_features.py --year 2024
    .venv/bin/python fetch_gee_features.py --limit 50   # test on 50 cells first
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Repo root
REPO = Path(__file__).resolve().parent

# Import config
sys.path.insert(0, str(REPO))
from config import DYNAMIC_FEATURES, ALPHAEARTH_YEAR


# ============== GEE INIT ==============

def init_gee():
    """Initialize GEE with cached user credentials (~/.config/earthengine/credentials).

    Service account at ~/Personal Projects/ee-yelozgur-*.json does NOT have
    earthengine.googleapis.com access (returns 403 USER_PROJECT_DENIED).
    Falls back to user's own `earthengine authenticate` credentials.
    """
    import ee
    try:
        ee.Initialize(project='ee-yelozgur')
        return ee
    except Exception as e:
        print(f'ee.Initialize failed: {e}')
        print('Run: earthengine authenticate --project=ee-yelozgur')
        sys.exit(1)


# ============== MONTHLY STACK ==============

def _monthly_lst(year: int, ee_mod) -> ee_mod.Image:
    """12-band LST image (Celsius, monthly mean of MODIS/061/MOD11A1)."""
    coll = ee_mod.ImageCollection('MODIS/061/MOD11A1').filterDate(
        f'{year}-01-01', f'{year + 1}-01-01'
    ).select('LST_Day_1km').map(
        lambda img: img.multiply(0.02).add(-273.15).copyProperties(img, ['system:time_start'])
    )
    bands = []
    for m in range(1, 13):
        start = f'{year}-{m:02d}-01'
        end = f'{year}-{m + 1:02d}-01' if m < 12 else f'{year + 1}-01-01'
        bands.append(
            coll.filterDate(start, end).mean().rename(f'm{m:02d}')
        )
    return ee_mod.Image.cat(bands)


def _monthly_ndvi(year: int, ee_mod) -> ee_mod.Image:
    """12-band NDVI image (monthly mean of MODIS/061/MOD13Q1, × 0.0001)."""
    coll = ee_mod.ImageCollection('MODIS/061/MOD13Q1').filterDate(
        f'{year}-01-01', f'{year + 1}-01-01'
    ).select('NDVI').map(
        lambda img: img.multiply(0.0001).copyProperties(img, ['system:time_start'])
    )
    bands = []
    for m in range(1, 13):
        start = f'{year}-{m:02d}-01'
        end = f'{year}-{m + 1:02d}-01' if m < 12 else f'{year + 1}-01-01'
        bands.append(
            coll.filterDate(start, end).mean().rename(f'm{m:02d}')
        )
    return ee_mod.Image.cat(bands)


def _monthly_humidity(year: int, ee_mod) -> ee_mod.Image:
    """12-band dewpoint temp image (monthly mean of ERA5-Land hourly)."""
    coll = ee_mod.ImageCollection('ECMWF/ERA5_LAND/HOURLY').filterDate(
        f'{year}-01-01', f'{year + 1}-01-01'
    ).select('dewpoint_temperature_2m')
    bands = []
    for m in range(1, 13):
        start = f'{year}-{m:02d}-01'
        end = f'{year}-{m + 1:02d}-01' if m < 12 else f'{year + 1}-01-01'
        bands.append(
            coll.filterDate(start, end).mean().rename(f'm{m:02d}')
        )
    return ee_mod.Image.cat(bands)


def _monthly_precip(year: int, ee_mod) -> ee_mod.Image:
    """12-band precip image (monthly SUM of CHIRPS daily)."""
    coll = ee_mod.ImageCollection('UCSB-CHG/CHIRPS/DAILY').filterDate(
        f'{year}-01-01', f'{year + 1}-01-01'
    ).select('precipitation')
    bands = []
    for m in range(1, 13):
        start = f'{year}-{m:02d}-01'
        end = f'{year}-{m + 1:02d}-01' if m < 12 else f'{year + 1}-01-01'
        bands.append(
            coll.filterDate(start, end).sum().rename(f'm{m:02d}')
        )
    return ee_mod.Image.cat(bands)


def _monthly_wind(year: int, ee_mod) -> ee_mod.Image:
    """12-band wind speed image (monthly mean of sqrt(u^2 + v^2) from ERA5-Land)."""
    coll = ee_mod.ImageCollection('ECMWF/ERA5_LAND/HOURLY').filterDate(
        f'{year}-01-01', f'{year + 1}-01-01'
    ).select('u_component_of_wind_10m', 'v_component_of_wind_10m').map(
        lambda img: img.expression(
            'sqrt(u*u + v*v)',
            {'u': img.select('u_component_of_wind_10m'),
             'v': img.select('v_component_of_wind_10m')}
        ).rename('wind').copyProperties(img, ['system:time_start'])
    )
    bands = []
    for m in range(1, 13):
        start = f'{year}-{m:02d}-01'
        end = f'{year}-{m + 1:02d}-01' if m < 12 else f'{year + 1}-01-01'
        bands.append(
            coll.filterDate(start, end).mean().rename(f'm{m:02d}')
        )
    return ee_mod.Image.cat(bands)


FEATURE_FNS = {
    'LST': _monthly_lst,
    'NDVI': _monthly_ndvi,
    'Humidity': _monthly_humidity,
    'Precip': _monthly_precip,
    'WindSpeed': _monthly_wind,
}


# ============== SAMPLE ==============

def fetch_features_for_points(ee_mod, points: list[tuple[int, float, float]], year: int) -> pd.DataFrame:
    """For each chunk of (cell_id, lat, lon) tuples, build a fresh FC,
    sample all 5 features, accumulate rows.

    GEE has two limits that affect this code:
    - 10MB request payload limit (too-large FC fails to even get to GEE)
    - ~1000-feature silent truncation in `sampleRegions`
    So we chunk from the start: never build a single FC larger than CHUNK_SIZE.

    points: list of (cell_id, lat, lon) tuples. We accept a list (not a
    pre-built FC) so the caller doesn't have to materialize 37K-point
    FCs in memory or via GEE.

    Returns DataFrame with cell_id + 60 columns (Jan→Dec order, reordered
    by caller). Cells with no GEE data for a given feature get NaN.
    """
    CHUNK_SIZE = 800  # safely under GEE's 1000 silent-truncation limit
    n_points = len(points)
    print(f'  Total points: {n_points}, chunk_size: {CHUNK_SIZE}')
    chunks = [points[i:i + CHUNK_SIZE] for i in range(0, n_points, CHUNK_SIZE)]
    print(f'  Split into {len(chunks)} chunks')

    # Per-feature accumulators
    feature_data: dict[str, dict[int, dict[int, float]]] = {
        f: {} for f in DYNAMIC_FEATURES
    }

    for ci, chunk in enumerate(chunks):
        chunk_fc = ee_mod.FeatureCollection([
            ee_mod.Feature(ee_mod.Geometry.Point([lon, lat]), {'cell_id': int(cid)})
            for cid, lat, lon in chunk
        ])
        print(f'  Chunk {ci + 1}/{len(chunks)} ({len(chunk)} points):')

        for feature in DYNAMIC_FEATURES:
            img = FEATURE_FNS[feature](year, ee_mod)
            sampled = img.sampleRegions(
                collection=chunk_fc,
                properties=['cell_id'],
                scale=5000,
                tileScale=4,
            )
            try:
                response = ee_mod.data.computeFeatures({'expression': sampled})
            except Exception as e:
                print(f'    {feature}: ERROR ({e})')
                continue
            feats = response.get('features', [])
            n_ok = 0
            for f in feats:
                cid = int(f['properties']['cell_id'])
                if cid not in feature_data[feature]:
                    feature_data[feature][cid] = {}
                for m in range(1, 13):
                    v = f['properties'].get(f'm{m:02d}')
                    if v is not None:
                        feature_data[feature][cid][m] = v
                        n_ok += 1
            if feats:
                print(f'    {feature}: {len(feats)} cells ({n_ok} non-null values)')

    # Build DataFrame from feature_data
    all_cids = set()
    for f in DYNAMIC_FEATURES:
        all_cids.update(feature_data[f].keys())

    rows = []
    for cid in sorted(all_cids):
        row = {'cell_id': cid}
        for feature in DYNAMIC_FEATURES:
            for m in range(1, 13):
                col = f'{feature}_{m:02d}'
                if cid in feature_data[feature] and m in feature_data[feature][cid]:
                    row[col] = feature_data[feature][cid][m]
                # else: column not in row → pandas NaN
        rows.append(row)

    df = pd.DataFrame(rows)
    print(f'\n  Total cells with at least one feature: {len(df)}')
    for f in DYNAMIC_FEATURES:
        cells_with_f = sum(1 for cid in all_cids if cid in feature_data[f])
        print(f'  {f}: {cells_with_f} cells ({cells_with_f / len(all_cids) * 100:.1f}%)')
    return df


# ============== REORDER ==============

# Existing features_cache_active.parquet column order:
# LST_06, NDVI_06, Humidity_06, Precip_06, WindSpeed_06,  (month 06)
# LST_07, NDVI_07, ..., WindSpeed_07,                     (month 07)
# ...
# LST_05, NDVI_05, Humidity_05, Precip_05, WindSpeed_05   (month 05)
# = 60 columns, order is 06, 07, 08, 09, 10, 11, 12, 01, 02, 03, 04, 05
CACHE_MONTH_ORDER = [6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5]


def reorder_to_cache_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Take df with columns cell_id, LST_01..LST_12, NDVI_01.., ... (Jan-Dec order)
    and reorder to match features_cache_active.parquet column order (06-05 cycle)."""
    out_cols = ['cell_id']
    for m in CACHE_MONTH_ORDER:
        for f in DYNAMIC_FEATURES:
            out_cols.append(f'{f}_{m:02d}')
    return df[out_cols]


# ============== MAIN ==============

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, default=ALPHAEARTH_YEAR)
    parser.add_argument('--limit', type=int, default=0,
                        help='Limit to first N missing cells (testing). 0 = all.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Compute + report, do not save')
    args = parser.parse_args()

    print(f'\n=== FETCH GEE FEATURES (year={args.year}, limit={args.limit}) ===\n')

    # Load existing
    cells_path = REPO / 'data' / 'cells_full.parquet'
    cache_path = REPO / 'data' / 'features_cache_active.parquet'

    cells = pd.read_parquet(cells_path)
    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        print(f'cells_full: {len(cells)} cells')
        print(f'features_cache_active: {len(cached)} cells (existing)')
    else:
        cached = pd.DataFrame(columns=['cell_id'])
        print(f'cells_full: {len(cells)} cells')
        print(f'features_cache_active: 0 cells (no file, will create)')

    # Find missing
    cached_ids = set(cached['cell_id'].astype(int).tolist())
    all_ids = set(cells['cell_id'].astype(int).tolist())
    missing_ids = sorted(all_ids - cached_ids)
    print(f'Missing: {len(missing_ids)} cells')

    if not missing_ids:
        print('All cells have features. Nothing to do.')
        return

    if args.limit > 0:
        missing_ids = missing_ids[:args.limit]
        print(f'  (limited to first {args.limit} for testing)')

    # Init GEE
    ee_mod = init_gee()
    print('GEE init: OK')

    # Build local point list (cell_id, lat, lon) — chunking happens inside fetch
    cell_lookup = cells.set_index('cell_id')[['lat', 'lon']].to_dict('index')
    points = []
    for cid in missing_ids:
        ll = cell_lookup[cid]
        points.append((int(cid), float(ll['lat']), float(ll['lon'])))
    print(f'Built points list: {len(points)} (will chunk inside fetch)')

    # Fetch
    t0 = time.time()
    df_new = fetch_features_for_points(ee_mod, points, args.year)
    elapsed = time.time() - t0
    print(f'\nFetch took {elapsed:.1f}s')
    print(f'New rows: {len(df_new)} (expected {len(missing_ids)})')

    if len(df_new) == 0:
        print('FATAL: no features returned. Aborting.')
        sys.exit(1)

    # Check coverage
    returned_ids = set(df_new['cell_id'].astype(int).tolist())
    missing_returned = set(missing_ids) - returned_ids
    print(f'  cells with no GEE data: {len(missing_returned)}')
    if missing_returned:
        print(f'  first 5: {sorted(missing_returned)[:5]} (likely sea or outside bbox)')

    # Reorder columns
    df_new = reorder_to_cache_columns(df_new)
    print(f'Reordered to cache column order: {list(df_new.columns[:6])} ... {list(df_new.columns[-3:])}')

    if args.dry_run:
        print(f'\nDRY RUN: would merge {len(df_new)} new rows into features_cache_active.parquet')
        print(f'  new total: {len(cached) + len(df_new)} cells')
        return

    # Merge: existing + new (concat on cell_id, no duplicates expected)
    combined = pd.concat([cached, df_new], ignore_index=True)
    # Drop any duplicate cell_ids (keep first = existing takes priority)
    combined = combined.drop_duplicates(subset='cell_id', keep='first')
    print(f'\nMerged: {len(combined)} cells total ({len(cached)} existing + {len(df_new)} new)')

    # Save
    combined.to_parquet(cache_path, index=False)
    print(f'Saved: {cache_path}')

    # Verify
    cached2 = pd.read_parquet(cache_path)
    print(f'Verified: {len(cached2)} cells in updated cache')
    print(f'Coverage: {len(cached2) / len(cells) * 100:.1f}% of cells_full.parquet')


if __name__ == '__main__':
    main()
