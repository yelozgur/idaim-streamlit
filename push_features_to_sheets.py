"""push_features_to_sheets.py — Push features_cache_active.parquet to Google Sheets.

Writes all 36,905 cells × 64 cols to a new tab 'features_active' in
DATA V2 spreadsheet. Old 'features_cache' tab (POC, 404 rows) is kept
intact for reference.

Schema (64 cols):
  cell_id, lat, lon, district, then 5 features × 12 months
  Feature order: LST_06, NDVI_06, Humidity_06, Precip_06, WindSpeed_06, ..., WindSpeed_05
  (matches features_cache_active.parquet column order — June→May cycle)

Rate limit handling: gspread append_rows with batches of 1000 rows × 64 cols.
~37 batches, ~2-3 minutes total. Sheets API has 60 writes/min/user default.

Auth (v0.7+): env-based via sheets_client._get_creds_dict(). Set
GCP_SA_JSON (HF Spaces) or GCP_SA_JSON_PATH env var. Default local
path (~/Documents/Personal Projects/ee-yelozgur-*.json) used otherwise.
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
import sheets_client  # for _get_creds_dict() — same auth as Streamlit/Dash

SHEET_ID = os.environ.get('SHEET_ID', '16wqnRUUPNBA_qhPMEdy4g9gCm_QKu5IxyCbJweStRCY')
TAB_NAME = 'features_active'
BATCH_SIZE = 1000  # rows per write

# CACHE_MONTH_ORDER must match fetch_gee_features.py
CACHE_MONTH_ORDER = [6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5]
DYNAMIC_FEATURES = ['LST', 'NDVI', 'Humidity', 'Precip', 'WindSpeed']


def main():
    print('Loading data...')
    cells = pd.read_parquet(REPO / 'data' / 'cells_full.parquet')
    cache = pd.read_parquet(REPO / 'data' / 'features_cache_active.parquet')
    print(f'  cells: {len(cells):,}')
    print(f'  cache: {len(cache):,}')

    # Build merged df: cell_id, lat, lon, district, then 60 features
    merged = cells[['cell_id', 'lat', 'lon', 'district']].merge(
        cache, on='cell_id', how='inner'  # inner: only cells with features
    )
    print(f'  merged: {len(merged):,} (cells with features)')

    # Reorder columns: cell_id, lat, lon, district, then 60 features in cache order
    feature_cols = []
    for m in CACHE_MONTH_ORDER:
        for f in DYNAMIC_FEATURES:
            feature_cols.append(f'{f}_{m:02d}')
    merged = merged[['cell_id', 'lat', 'lon', 'district'] + feature_cols]
    print(f'  columns: {len(merged.columns)} ({merged.columns[:8].tolist()} ...)')

    # Open Sheets (auth via sheets_client._get_creds_dict — env or default)
    print('Connecting to Google Sheets...')
    creds_dict = sheets_client._get_creds_dict()
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)

    # Create or recreate tab
    try:
        old = sh.worksheet(TAB_NAME)
        print(f'  Tab "{TAB_NAME}" exists, deleting...')
        sh.del_worksheet(old)
    except gspread.exceptions.WorksheetNotFound:
        print(f'  Tab "{TAB_NAME}" does not exist')

    ws = sh.add_worksheet(title=TAB_NAME, rows=len(merged) + 1, cols=len(merged.columns))
    print(f'  Created tab "{TAB_NAME}" ({len(merged) + 1} rows × {len(merged.columns)} cols)')

    # Write headers + data
    print('Writing data...')
    headers = merged.columns.tolist()

    # Round floats to 4 decimals to keep cells readable
    rows_data = []
    for _, row in merged.iterrows():
        out = []
        for c in merged.columns:
            v = row[c]
            if pd.isna(v):
                out.append('')
            elif isinstance(v, (int,)):
                out.append(str(v))
            elif isinstance(v, float):
                out.append(f'{v:.4f}')
            else:
                out.append(str(v))
        rows_data.append(out)

    n_rows = len(rows_data)
    n_batches = (n_rows + BATCH_SIZE - 1) // BATCH_SIZE
    t0 = time.time()

    for bi in range(n_batches):
        start = bi * BATCH_SIZE
        end = min(start + BATCH_SIZE, n_rows)
        batch = rows_data[start:end]
        try:
            if bi == 0:
                # First batch: include headers
                ws.append_rows([headers] + batch, value_input_option='USER_ENTERED')
            else:
                ws.append_rows(batch, value_input_option='USER_ENTERED')
        except Exception as e:
            print(f'  batch {bi + 1}/{n_batches} ERROR: {e}')
            print('  waiting 30s and retrying...')
            time.sleep(30)
            ws.append_rows(batch, value_input_option='USER_ENTERED')

        if (bi + 1) % 5 == 0 or bi == n_batches - 1:
            elapsed = time.time() - t0
            rate = (bi + 1) / elapsed if elapsed > 0 else 0
            eta = (n_batches - bi - 1) / rate if rate > 0 else 0
            print(f'  batch {bi + 1}/{n_batches}: {end:,}/{n_rows:,} rows ({elapsed:.0f}s elapsed, ETA {eta:.0f}s)')

    elapsed = time.time() - t0
    print(f'\nDONE: {n_rows:,} rows × {len(merged.columns)} cols in {elapsed:.0f}s')
    print(f'Tab: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid={ws.id}')


if __name__ == '__main__':
    main()
