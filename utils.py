"""utils.py — Shared helpers across pages.

Cached data loading, color scales, format helpers.

Data architecture (v0.6.5):
- 37K cells (lat/lon/district) live in data/cells_full.parquet (Streamlit
  bundle, not Sheets). Sheets' "cells" tab has lat/lon SWAPPED — do not
  read cells from Sheets. v0.6.4 fix: load_cells now merges Parquet (lat/lon)
  with Sheets (ML proba, freshest).
- Dynamic data (sampling_initiation, trap_checks, lab_results, watch_list,
  users) lives in Sheets.

Framework: v0.7+ framework-agnostic. Module-level TTL cache replaces
@st.cache_data (works in both Streamlit legacy and Plotly Dash). Use
clear_all_caches() to invalidate after data mutations.
"""
import time
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional

import sheets_client
from config import DISTRICTS

logger = logging.getLogger(__name__)

# Streamlit availability flag (Dash mode skips st.* calls)
try:
    import streamlit as _st  # noqa
    _HAS_ST = True
except ImportError:
    _HAS_ST = False


# ============== PATHS ==============

# Repo root — Parquet lives at <repo>/data/cells_full.parquet
REPO_ROOT = Path(__file__).resolve().parent
CELLS_PARQUET = REPO_ROOT / "data" / "cells_full.parquet"


# ============== MODULE-LEVEL TTL CACHE ==============

# Replaces @st.cache_data — dict with (timestamp, value) per key.
_cache: dict = {}


def _cached(ttl: int, key: str, fn, *args, **kwargs):
    """Get or compute cached value with TTL (seconds)."""
    now = time.time()
    entry = _cache.get(key)
    if entry is not None and now - entry[0] < ttl:
        return entry[1]
    val = fn(*args, **kwargs)
    _cache[key] = (now, val)
    return val


def clear_all_caches():
    """Clear all module-level caches (after data mutation)."""
    _cache.clear()


# ============== STATIC CELLS (Parquet) ==============

def _load_static_cells_impl() -> pd.DataFrame:
    if not CELLS_PARQUET.exists():
        logger.error(f"Statik cells dosyası yok: {CELLS_PARQUET}.")
        return pd.DataFrame()
    df = pd.read_parquet(CELLS_PARQUET)
    if "cell_id" in df.columns:
        df["cell_id"] = pd.to_numeric(df["cell_id"], errors="coerce").astype("Int64")
    return df


def load_static_cells() -> pd.DataFrame:
    """37K cells from data/cells_full.parquet (correct lat/lon, 1h cache)."""
    return _cached(3600, "static_cells", _load_static_cells_impl)


# ============== CACHED DATA LOADERS ==============

def _load_ml_output_impl() -> pd.DataFrame:
    try:
        df = sheets_client.get_cells()
    except Exception as e:
        logger.warning(f"ML output load error: {e}")
        return pd.DataFrame()
    if len(df) == 0:
        return df
    keep = ["cell_id"]
    for c in ["culex_proba", "aedes_proba", "confidence_tier", "last_updated"]:
        if c in df.columns:
            keep.append(c)
    return df[keep].copy()


def load_ml_output() -> pd.DataFrame:
    """ML proba + tier from Sheets (freshest predictions, 5 min cache)."""
    return _cached(300, "ml_output", _load_ml_output_impl)


def _load_merged_cells_impl() -> pd.DataFrame:
    cells = load_static_cells()
    if len(cells) == 0:
        return cells
    ml = load_ml_output()
    if len(ml) > 0:
        ml_cols = [c for c in ml.columns if c in ["cell_id", "culex_proba", "aedes_proba", "confidence_tier", "last_updated"]]
        cells = cells.copy()
        cells["cell_id"] = pd.to_numeric(cells["cell_id"], errors="coerce").astype("Int64")
        ml = ml.copy()
        ml["cell_id"] = pd.to_numeric(ml["cell_id"], errors="coerce").astype("Int64")
        cells = cells.merge(ml[ml_cols], on="cell_id", how="left", suffixes=("", "_ml"))
    return cells


def load_merged_cells() -> pd.DataFrame:
    """Cells (Parquet) + ML output (Sheets) merged. Sheet ML takes precedence (5 min cache)."""
    return _cached(300, "merged_cells", _load_merged_cells_impl)


def load_cells() -> pd.DataFrame:
    """All cells (5 min cache). Wrapper around load_merged_cells()."""
    return load_merged_cells()


def load_sampling_initiations() -> pd.DataFrame:
    """All sampling inits (2 min cache)."""
    def _impl():
        try:
            return sheets_client.get_sampling_initiations(active_only=False)
        except Exception as e:
            logger.error(f"Sampling initiation load error: {e}")
            return pd.DataFrame()
    return _cached(120, "sampling_initiations", _impl)


def load_trap_checks() -> pd.DataFrame:
    """All trap checks (2 min cache)."""
    def _impl():
        try:
            return sheets_client.get_trap_checks()
        except Exception as e:
            logger.error(f"Trap checks load error: {e}")
            return pd.DataFrame()
    return _cached(120, "trap_checks", _impl)


def load_lab_results() -> pd.DataFrame:
    """All lab results (2 min cache)."""
    def _impl():
        try:
            return sheets_client.get_lab_results()
        except Exception as e:
            logger.error(f"Lab results load error: {e}")
            return pd.DataFrame()
    return _cached(120, "lab_results", _impl)


def load_watch_list() -> pd.DataFrame:
    """Watch list (5 min cache)."""
    def _impl():
        try:
            return sheets_client.get_watch_list()
        except Exception:
            return pd.DataFrame()
    return _cached(300, "watch_list", _impl)


# ============== JOINED VIEWS ==============

def load_labeled_cells() -> pd.DataFrame:
    """Lab-confirmed cells (training data, 2 min cache)."""
    def _impl():
        inits = load_sampling_initiations()
        labs = load_lab_results()
        cells = load_cells()
        if len(inits) == 0 or len(labs) == 0:
            return pd.DataFrame()
        return (labs
            .merge(inits[["trap_id", "cell_id", "state"]], on=["trap_id", "cell_id"], how="inner",
                   suffixes=("_lab", "_init"))
            .merge(cells[["cell_id", "lon", "lat", "district"]], on="cell_id", how="left"))
    return _cached(120, "labeled_cells", _impl)


def load_traps_with_state() -> pd.DataFrame:
    """All traps + last check + cell info (5 min cache)."""
    def _impl():
        inits = load_sampling_initiations()
        checks = load_trap_checks()
        cells = load_cells()
        if len(inits) == 0:
            return pd.DataFrame()
        df = inits.copy()
        if len(checks) > 0:
            last_checks = (checks
                .sort_values("check_datetime")
                .groupby("trap_id")
                .agg(last_check=("trap_status", "last"),
                     last_check_time=("check_datetime", "last"),
                     n_checks=("check_id", "count"))
                .reset_index())
            df = df.merge(last_checks, on="trap_id", how="left")
        else:
            df["last_check"] = None
            df["last_check_time"] = None
            df["n_checks"] = 0
        if len(cells) > 0:
            df = df.merge(cells[["cell_id", "lon", "lat", "district", "culex_proba"]],
                          on="cell_id", how="left")
        return df
    return _cached(300, "traps_with_state", _impl)


# ============== COLOR HELPERS ==============

def proba_to_color(proba: float, threshold: float = 0.10) -> str:
    """ML probability to Folium color."""
    if pd.isna(proba):
        return "#9aa0a6"  # gray (unknown)
    if proba >= 0.7:
        return "#7f0000"  # dark red
    if proba >= 0.5:
        return "#d32f2f"  # red
    if proba >= 0.3:
        return "#f57c00"  # orange
    if proba >= threshold:
        return "#fbc02d"  # yellow
    return "#bbdefb"      # light blue (low)


def state_to_color(state: str) -> str:
    """Trap state -> color (markers)."""
    return {
        "active": "#4caf50",    # green
        "closed": "#9e9e9e",    # gray
        "missing": "#f44336",   # red
    }.get(state, "#9e9e9e")


def status_to_color(status: str) -> str:
    """Check status -> color (markers)."""
    if status == "Trap valid":
        return "#4caf50"
    if status == "Trap Missing":
        return "#f44336"
    if status == "Trap Disturbed":
        return "#ff9800"
    if status == "Battery out":
        return "#9e9e9e"
    return "#9e9e9e"


def species_to_color(species: str) -> str:
    """Lab species -> color."""
    return {
        "Culex": "#1976d2",      # blue
        "Aedes": "#d32f2f",      # red
        "Mixed": "#7b1fa2",      # purple
        "Other": "#757575",      # gray
        "Negative": "#bdbdbd",   # light gray
    }.get(species, "#757575")


# Folium.Icon only accepts named colors ('red', 'green', 'blue', 'orange', etc.)
# — hex strings are silently dropped (all markers fall back to blue).
# This table maps our internal hex colors to Folium named colors.
_HEX_TO_FOLIUM = {
    "#4caf50": "green",
    "#f44336": "red",
    "#ff9800": "orange",
    "#9e9e9e": "gray",
    "#1976d2": "blue",
    "#d32f2f": "red",
    "#7b1fa2": "purple",
    "#757575": "gray",
    "#bdbdbd": "lightgray",
    "#bbdefb": "lightblue",
    "#7f0000": "darkred",
    "#f57c00": "orange",
    "#fbc02d": "beige",
}


def hex_to_folium_name(hex_color: str) -> str:
    """Map a hex color to a Folium named color.

    Folium.Icon(color=..., icon_color=...) only accepts named colors
    ('red', 'green', 'blue', 'orange', 'darkred', etc.). Passing hex
    ('#4caf50') is silently dropped and falls back to default blue.
    """
    if not hex_color:
        return "blue"
    return _HEX_TO_FOLIUM.get(hex_color.lower(), "blue")


# ============== FORMAT HELPERS ==============

def fmt_proba(p: float) -> str:
    """0.847 -> '0.85'."""
    if pd.isna(p):
        return "—"
    return f"{p:.2f}"


def fmt_count(n) -> str:
    """Specimen count formatter."""
    if pd.isna(n) or n == 0:
        return "0"
    return f"{int(n)}"


def safe_int(v, default=0) -> int:
    """Safe int conversion (None/NaN safe)."""
    try:
        if pd.isna(v):
            return default
        return int(v)
    except (ValueError, TypeError):
        return default


# ============== METRICS ==============

def compute_label_counts() -> dict:
    """Lab-confirmed cell counts (per species)."""
    labeled = load_labeled_cells()
    if len(labeled) == 0:
        return {"total": 0, "culex_pos": 0, "culex_neg": 0, "aedes_pos": 0, "aedes_neg": 0}

    total = labeled["cell_id"].nunique()

    culex_pos = labeled[labeled["species"] == "Culex"]["cell_id"].nunique()
    culex_neg = total - culex_pos

    aedes_pos = labeled[labeled["species"] == "Aedes"]["cell_id"].nunique()
    aedes_neg = total - aedes_pos

    return {
        "total": int(total),
        "culex_pos": int(culex_pos),
        "culex_neg": int(culex_neg),
        "aedes_pos": int(aedes_pos),
        "aedes_neg": int(aedes_neg),
    }


def compute_trap_counts() -> dict:
    """Trap status counts."""
    inits = load_sampling_initiations()
    if len(inits) == 0:
        return {"active": 0, "closed": 0, "missing": 0, "total": 0}

    counts = inits["state"].value_counts().to_dict()
    return {
        "active": int(counts.get("active", 0)),
        "closed": int(counts.get("closed", 0)),
        "missing": int(counts.get("missing", 0)),
        "total": len(inits),
    }


# ============== AUTH (Streamlit only — Dash has no equivalent yet) ==============

def require_auth():
    """Auth check, stops if not logged in. No-op in Dash mode (TODO v0.7.1)."""
    if not _HAS_ST:
        return
    if not _st.session_state.get("authenticated", False):
        _st.warning("Please sign in (go to the main page)")
        _st.stop()


def require_admin():
    """Admin-only check. No-op in Dash mode (TODO v0.7.1)."""
    require_auth()
    if not _HAS_ST:
        return
    if _st.session_state.get("role") != "admin":
        _st.error("Access denied — admin only")
        _st.stop()


# ============== GEO HELPERS ==============

def find_nearest_cell(cells: pd.DataFrame, lat: float, lon: float) -> Optional[int]:
    """Find cell_id nearest to (lat, lon). Returns None if no cells.

    Vectorized Euclidean on Cyprus-scale lat/lon (good enough for ~0.5km grid).
    Pre-v0.7 used haversine; euclidean is ~3x faster and accuracy is identical
    at Cyprus latitude (35°N, where 1°lat ≈ 111km, 1°lon ≈ 91km).
    """
    if len(cells) == 0 or pd.isna(lat) or pd.isna(lon):
        return None
    d2 = (cells["lat"].astype(float) - float(lat)) ** 2 + (cells["lon"].astype(float) - float(lon)) ** 2
    idx = d2.idxmin()
    if pd.isna(idx):
        return None
    return int(cells.loc[idx, "cell_id"])
