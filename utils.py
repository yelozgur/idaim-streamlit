"""utils.py — Shared helpers across pages.

Cached data loading, color scales, format helpers.
"""
import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional

import sheets_client
from config import DISTRICTS


# ============== CACHED DATA LOADERS ==============

@st.cache_data(ttl=300, show_spinner=False)
def load_cells() -> pd.DataFrame:
    """All cells (5 min cache)."""
    try:
        return sheets_client.get_cells()
    except Exception as e:
        st.error(f"Cells load error: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def load_sampling_initiations() -> pd.DataFrame:
    """All sampling inits (2 min cache)."""
    try:
        return sheets_client.get_sampling_initiations(active_only=False)
    except Exception as e:
        st.error(f"Sampling initiation load error: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def load_trap_checks() -> pd.DataFrame:
    """All trap checks (2 min cache)."""
    try:
        return sheets_client.get_trap_checks()
    except Exception as e:
        st.error(f"Trap checks load error: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def load_lab_results() -> pd.DataFrame:
    """All lab results (2 min cache)."""
    try:
        return sheets_client.get_lab_results()
    except Exception as e:
        st.error(f"Lab results load error: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def load_watch_list() -> pd.DataFrame:
    """Watch list (5 min cache)."""
    try:
        return sheets_client.get_watch_list()
    except Exception:
        return pd.DataFrame()


def clear_all_caches():
    """Clear all caches (after data change)."""
    load_cells.clear()
    load_sampling_initiations.clear()
    load_trap_checks.clear()
    load_lab_results.clear()
    load_watch_list.clear()


# ============== JOINED VIEWS ==============

@st.cache_data(ttl=120, show_spinner=False)
def load_labeled_cells() -> pd.DataFrame:
    """Lab-confirmed cells (training data).

    lab_results -> sampling_initiation -> cells JOIN
    """
    inits = load_sampling_initiations()
    labs = load_lab_results()
    cells = load_cells()

    if len(inits) == 0 or len(labs) == 0:
        return pd.DataFrame()

    merged = (labs
        .merge(inits[["trap_id", "cell_id", "state"]], on=["trap_id", "cell_id"], how="inner",
               suffixes=("_lab", "_init"))
        .merge(cells[["cell_id", "lon", "lat", "district"]], on="cell_id", how="left"))
    return merged


@st.cache_data(ttl=300, show_spinner=False)
def load_traps_with_state() -> pd.DataFrame:
    """All traps + last check + cell info."""
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


# ============== AUTH ==============

def require_auth():
    """Auth check, stops if not logged in."""
    if not st.session_state.get("authenticated", False):
        st.warning("Please sign in (go to the main page)")
        st.stop()


def require_admin():
    """Admin-only check."""
    require_auth()
    if st.session_state.get("role") != "admin":
        st.error("Access denied — admin only")
        st.stop()
