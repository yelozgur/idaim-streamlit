"""train_local.py — Local ML training pipeline (no Colab).

Mimics retrain-weekly.sh's prepare + train + predict + write_watch_list
steps, runs everything locally. Used for testing dummy data or ad-hoc
retraining without Colab. NOT the production path — production uses
retrain-weekly.sh + Colab T4 + git push.

Usage:
    .venv/bin/python train_local.py --species aedes
    .venv/bin/python train_local.py --species culex
    .venv/bin/python train_local.py --species both
    .venv/bin/python train_local.py --species both --write-watchlist

Outputs:
- data/07_models/model_<species>.joblib (matches Colab output path)
- watch_list rows appended to Sheets 'watch_list' tab (if --write-watchlist)
- metrics JSON printed + saved to data/07_models/metrics_local.json

Why direct gspread: streamlit runtime is mocked in this script (avoids
`@st.cache_data` issues), so sheets_client.append_rows returns a Mock
object instead of actually writing. We use gspread directly for both
read and write of Sheets — this is fine in cron context, retrain-weekly.sh
also runs outside Streamlit.
"""
import argparse
import json
import os
import pickle
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Repo root
REPO = Path(__file__).resolve().parent

# Local training doesn't need Streamlit runtime. Mock the modules our code
# imports but doesn't actually use during local training.
import unittest.mock as mock
sys.modules['streamlit'] = mock.MagicMock()

# Now import our modules (they'll see the mocked streamlit).
sys.path.insert(0, str(REPO))

import gspread
from google.oauth2.service_account import Credentials
import json as _json

from config import DYNAMIC_FEATURES, MIN_SAMPLES

# Direct gspread (bypasses @st.cache_data mock issue, works outside Streamlit)
SHEET_ID = '16wqnRUUPNBA_qhPMEdy4g9gCm_QKu5IxyCbJweStRCY'
SA_PATH = Path('/Users/ozguryel/Documents/Personal Projects/ee-yelozgur-aceaafb59a17.json')


def _get_sheet():
    creds = Credentials.from_service_account_info(
        _json.loads(SA_PATH.read_text()),
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)


def _read_tab(ws):
    rows = ws.get_all_values()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows[1:], columns=rows[0])


def _append_rows(ws, rows):
    """Append rows in USER_ENTERED mode to Sheets."""
    if not rows:
        return 0
    headers = ws.row_values(1)
    values = [[str(r.get(h, "")) for h in headers] for r in rows]
    ws.append_rows(values, value_input_option='USER_ENTERED')
    return len(values)


def load_data():
    """Load cells (Parquet) + lab_results (Sheets) + sampling_initiation (Sheets)."""
    print('Loading cells from Parquet...')
    cells = pd.read_parquet(REPO / 'data/cells_full.parquet')
    print(f'  cells: {len(cells)} rows, lat {cells["lat"].min():.2f}-{cells["lat"].max():.2f}, lon {cells["lon"].min():.2f}-{cells["lon"].max():.2f}')

    print('Loading lab_results + sampling_initiation from Sheets (direct gspread)...')
    sh = _get_sheet()
    labs = _read_tab(sh.worksheet('lab_results'))
    inits = _read_tab(sh.worksheet('sampling_initiation'))
    print(f'  lab_results: {len(labs)} rows, sampling_initiation: {len(inits)} rows')

    return cells, labs, inits


def build_labeled(cells, labs, inits):
    """Merge to get (cell_id, lat, lon, district, species) labeled set."""
    if len(labs) == 0:
        print('  No lab data, returning empty labeled set')
        return pd.DataFrame(columns=['cell_id', 'species', 'lat', 'lon', 'district'])
    # Ensure numeric types for merge
    if 'cell_id' in labs.columns:
        labs['cell_id'] = pd.to_numeric(labs['cell_id'], errors='coerce').astype('Int64')
    if 'cell_id' in inits.columns:
        inits['cell_id'] = pd.to_numeric(inits['cell_id'], errors='coerce').astype('Int64')
    labeled = labs.merge(
        inits[['trap_id', 'cell_id', 'state']],
        on=['trap_id', 'cell_id'], how='inner', suffixes=('_lab', '_init')
    )
    labeled = labeled.merge(
        cells[['cell_id', 'lon', 'lat', 'district']],
        on='cell_id', how='left'
    )
    print(f'  labeled cells: {len(labeled)} (unique cell_ids: {labeled["cell_id"].nunique()})')
    if len(labeled) > 0 and 'species' in labeled.columns:
        print(f'  species distribution: {labeled["species"].value_counts().to_dict()}')
    return labeled


def build_features_array(cells_df, features_parquet_path):
    """Build (n, 5, 12) feature array from features Parquet."""
    if not features_parquet_path.exists():
        print(f'  WARNING: features Parquet not found at {features_parquet_path}')
        print('  Cannot train — features required for MiniRocket')
        return None, None

    features_df = pd.read_parquet(features_parquet_path)
    # features_df has columns: cell_id, then 5 features × 12 months = 60 cols
    feat_cols = [f'{f}_{m+1:02d}' for f in DYNAMIC_FEATURES for m in range(12)]
    available_cols = [c for c in feat_cols if c in features_df.columns]
    if len(available_cols) < len(feat_cols):
        print(f'  WARNING: features Parquet has {len(available_cols)}/{len(feat_cols)} expected cols')

    # Build array for cells in cells_df
    cell_ids = cells_df['cell_id'].astype(int).tolist()
    features_merged = cells_df[['cell_id']].merge(
        features_df[['cell_id'] + available_cols], on='cell_id', how='left'
    )
    # Shape: (n_cells, 5, 12)
    X = np.zeros((len(cell_ids), len(DYNAMIC_FEATURES), 12))
    for fi, feat in enumerate(DYNAMIC_FEATURES):
        for m in range(12):
            col = f'{feat}_{m+1:02d}'
            if col in features_merged.columns:
                X[:, fi, m] = pd.to_numeric(features_merged[col], errors='coerce').values
    valid_mask = ~np.all(np.isnan(X.reshape(len(cell_ids), -1)), axis=1)
    print(f'  features: {X.shape}, valid cells: {valid_mask.sum()}/{len(cell_ids)}')
    return X, valid_mask


def train_minirocket(X, y, n_jobs=-1):
    """Train MiniRocket. Returns (clf, imputer, metrics)."""
    from aeon.classification.convolution_based import MiniRocketClassifier
    from sklearn.impute import SimpleImputer

    imp = SimpleImputer(strategy='mean', keep_empty_features=True)
    # Fill all-NaN with 0 first so imputer has something to work with
    X_filled = np.nan_to_num(X, nan=0.0)
    X_flat = imp.fit_transform(X_filled.reshape(len(X_filled), -1))
    X_3d = X_flat.reshape(X_filled.shape)

    # LOOCV for small data, stratified for larger
    from sklearn.model_selection import LeaveOneOut
    from sklearn.metrics import (
        precision_recall_curve, cohen_kappa_score, roc_auc_score, auc
    )

    loo = LeaveOneOut()
    probas = np.zeros(len(y))
    failed = 0
    for train_idx, test_idx in loo.split(X_3d):
        try:
            clf = MiniRocketClassifier(n_jobs=n_jobs, random_state=42)
            # Re-fit imputer on train fold only (avoid leakage)
            train_X = X_filled[train_idx]
            test_X = X_filled[test_idx]
            train_3d_fold = train_X.reshape(train_X.shape)
            test_3d_fold = test_X.reshape(test_X.shape)
            clf.fit(train_3d_fold, y[train_idx])
            probas[test_idx] = clf.predict_proba(test_3d_fold)[:, 1]
        except Exception as e:
            print(f'  LOO fold failed: {e}')
            probas[test_idx] = 0.5
            failed += 1

    if len(np.unique(y)) < 2:
        return None, None, {'pr_auc': None, 'failed': failed}

    p, r, _ = precision_recall_curve(y, probas)
    pr_auc = float(auc(r, p))
    pred = (probas >= 0.5).astype(int)
    kappa = float(cohen_kappa_score(y, pred)) if len(np.unique(pred)) > 1 else 0.0
    roc = float(roc_auc_score(y, probas)) if len(np.unique(y)) > 1 else 0.0

    # Final model on all data
    final_clf = MiniRocketClassifier(n_jobs=n_jobs, random_state=42)
    final_clf.fit(X_3d, y)

    metrics = {
        'pr_auc': pr_auc,
        'kappa': kappa,
        'roc_auc': roc,
        'failed': failed,
        'n_train': int(len(y)),
        'n_positive': int(y.sum()),
        'n_negative': int((1 - y).sum()),
    }
    return final_clf, imp, metrics


def build_watch_list(species, proba_arr, cells, valid_mask, threshold=0.10):
    """Build watch list DataFrame from proba_arr, skip cells already in
    sampling_initiation or already visited in watch_list."""
    if proba_arr is None or not valid_mask.any():
        return pd.DataFrame()

    cell_ids = cells['cell_id'].astype(int).tolist()

    # Read existing sampling_initiation + watch_list directly (bypass mock cache)
    sh = _get_sheet()
    inits = _read_tab(sh.worksheet('sampling_initiation'))
    existing_cells = set()
    if len(inits) > 0 and 'cell_id' in inits.columns:
        existing_cells = set(pd.to_numeric(inits['cell_id'], errors='coerce').dropna().astype(int).unique().tolist())

    visited = set()
    all_watch_cells = set()
    try:
        existing_watch = _read_tab(sh.worksheet('watch_list'))
        if len(existing_watch) > 0 and 'visited' in existing_watch.columns:
            visited = set(
                pd.to_numeric(
                    existing_watch[existing_watch['visited'].astype(str).str.lower().isin(['true', '1', 'yes'])][
                        'cell_id'
                    ],
                    errors='coerce'
                ).dropna().astype(int).tolist()
            )
            all_watch_cells = set(
                pd.to_numeric(existing_watch['cell_id'], errors='coerce')
                .dropna().astype(int).tolist()
            )
    except Exception as e:
        print(f'  (skip watch_list read: {e})')

    # Skip cells in inits (currently being sampled) AND in watch_list (any status,
    # visited or not — re-training shouldn't duplicate existing watch list rows).
    skip = existing_cells | all_watch_cells
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows = []
    for i, cid in enumerate(cell_ids):
        if not valid_mask[i] or cid in skip:
            continue
        if i >= len(proba_arr):
            break
        p = float(proba_arr[i])
        if pd.isna(p) or p < threshold:
            continue
        cell = cells.iloc[i]
        rows.append({
            'cell_id': cid,
            'species': species.lower(),
            'proba': p,
            'threshold_used': float(threshold),
            'district': str(cell.get('district', 'Unknown')),
            'added_at': now,
            'visited': False,
            'trap_id': '',
        })
    return pd.DataFrame(rows).sort_values('proba', ascending=False).head(50)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--species', default='both', choices=['aedes', 'culex', 'both'])
    parser.add_argument('--threshold', type=float, default=0.10)
    parser.add_argument('--write-watchlist', action='store_true',
                        help='Append watch_list rows to Sheets (default: dry run, just print)')
    args = parser.parse_args()

    species_list = ['aedes', 'culex'] if args.species == 'both' else [args.species]
    print(f'\n=== LOCAL ML TRAINING (species={args.species}, threshold={args.threshold}, write={args.write_watchlist}) ===\n')

    # Load data
    cells, labs, inits = load_data()
    labeled = build_labeled(cells, labs, inits)

    # Build features
    X_all, valid_mask = build_features_array(cells, REPO / 'data/features_cache_active.parquet')
    if X_all is None:
        print('FATAL: features missing. Run scripts/fetch_gee_features.py first.')
        sys.exit(1)

    # Per-species training
    metrics_all = {}
    sh = _get_sheet()  # Open once, reuse
    watch_ws = sh.worksheet('watch_list')

    for species in species_list:
        target = species.capitalize()
        if target not in labeled['species'].unique():
            print(f'\n--- {species}: 0 positive samples, skipping')
            continue
        n_pos = int((labeled['species'] == target).sum())
        n_neg = int((labeled['species'] != target).sum())
        print(f'\n--- {species}: {n_pos} positive, {n_neg} negative ---')
        if n_pos < MIN_SAMPLES[species]:
            print(f'  Below MIN_SAMPLES={MIN_SAMPLES[species]}, skipping')
            continue

        # Get features for labeled cells
        labeled_ids = labeled['cell_id'].drop_duplicates().astype(int).tolist()
        cell_id_to_idx = {cid: i for i, cid in enumerate(cells['cell_id'].astype(int).tolist())}
        labeled_indices = [cell_id_to_idx[cid] for cid in labeled_ids if cid in cell_id_to_idx]
        X_labeled = X_all[labeled_indices]

        # Build y: 1 if species == target, 0 otherwise
        cell_id_to_species = dict(zip(labeled['cell_id'].astype(int), labeled['species']))
        y = np.array([1 if cell_id_to_species.get(cells.iloc[i]['cell_id']) == target else 0 for i in labeled_indices])

        # Train
        print(f'  Training MiniRocket on {len(y)} samples ({n_pos} positive)...')
        clf, imp, metrics = train_minirocket(X_labeled, y)
        if clf is None:
            print(f'  Training failed (only one class in y)')
            continue
        print(f'  Metrics: PR-AUC={metrics["pr_auc"]:.3f}, Kappa={metrics["kappa"]:.3f}, ROC-AUC={metrics["roc_auc"]:.3f}')

        # Save model
        models_dir = REPO / 'data' / '07_models'
        models_dir.mkdir(parents=True, exist_ok=True)
        with open(models_dir / f'model_{species}.joblib', 'wb') as f:
            pickle.dump({'clf': clf, 'imp': imp}, f)
        print(f'  Saved: {models_dir}/model_{species}.joblib')

        # Predict on all cells
        proba_all = clf.predict_proba(imp.transform(X_all.reshape(len(X_all), -1)).reshape(X_all.shape))[:, 1]

        # Build watch list
        watch = build_watch_list(species, proba_all, cells, valid_mask, threshold=args.threshold)
        print(f'  Watch list: {len(watch)} cells >= {args.threshold}')

        # Write to Sheets (only if --write-watchlist)
        if len(watch) > 0:
            if args.write_watchlist:
                written = _append_rows(watch_ws, watch.to_dict('records'))
                print(f'  Appended {written} watch_list rows to Sheets')
            else:
                print(f'  DRY RUN: would append {len(watch)} rows (use --write-watchlist to commit)')

        metrics_all[species] = metrics

    # Save metrics
    metrics_path = REPO / 'data' / '07_models' / 'metrics_local.json'
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, 'w') as f:
        json.dump(metrics_all, f, indent=2, default=str)
    print(f'\nMetrics saved: {metrics_path}')
    print('=== DONE ===\n')


if __name__ == '__main__':
    main()
