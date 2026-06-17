"""utils.py — Tüm sayfalar için ortak helper'lar.

Cache'li veri yükleme, renk skalası, format helper'ları.
"""
import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional

import sheets_client
from config import DISTRICTS


# ============== CACHE'Lİ VERİ YÜKLEME ==============

@st.cache_data(ttl=300, show_spinner=False)
def load_cells() -> pd.DataFrame:
    """Tüm 642 hücre (cache 5dk)."""
    try:
        return sheets_client.get_cells()
    except Exception as e:
        st.error(f"Hücreler yüklenemedi: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def load_sampling_initiations() -> pd.DataFrame:
    """Tüm sampling init (cache 2dk)."""
    try:
        return sheets_client.get_sampling_initiations(active_only=False)
    except Exception as e:
        st.error(f"Sampling initiation yüklenemedi: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def load_trap_checks() -> pd.DataFrame:
    """Tüm trap check (cache 2dk)."""
    try:
        return sheets_client.get_trap_checks()
    except Exception as e:
        st.error(f"Trap check'ler yüklenemedi: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner=False)
def load_lab_results() -> pd.DataFrame:
    """Tüm lab result (cache 2dk)."""
    try:
        return sheets_client.get_lab_results()
    except Exception as e:
        st.error(f"Lab sonuçları yüklenemedi: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def load_watch_list() -> pd.DataFrame:
    """Watch list (cache 5dk)."""
    try:
        return sheets_client.get_watch_list()
    except Exception:
        return pd.DataFrame()


def clear_all_caches():
    """Tüm cache'leri temizle (veri değişikliğinden sonra)."""
    load_cells.clear()
    load_sampling_initiations.clear()
    load_trap_checks.clear()
    load_lab_results.clear()
    load_watch_list.clear()


# ============== JOINED VIEWS ==============

@st.cache_data(ttl=120, show_spinner=False)
def load_labeled_cells() -> pd.DataFrame:
    """Lab-confirmed hücreler (training data).

    lab_results → sampling_initiation → cells JOIN
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
    """Tüm trap'ler + en son check durumu + cell bilgisi."""
    inits = load_sampling_initiations()
    checks = load_trap_checks()
    cells = load_cells()

    if len(inits) == 0:
        return pd.DataFrame()

    df = inits.copy()

    # Son check durumu
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

    # Cell bilgisi
    if len(cells) > 0:
        df = df.merge(cells[["cell_id", "lon", "lat", "district", "culex_proba"]],
                      on="cell_id", how="left")
    return df


# ============== COLOR HELPERS ==============

def proba_to_color(proba: float, threshold: float = 0.10) -> str:
    """ML olasılığını Folium renk skalasına çevir."""
    if pd.isna(proba):
        return "#9aa0a6"  # gri (unknown)
    if proba >= 0.7:
        return "#7f0000"  # bordo
    if proba >= 0.5:
        return "#d32f2f"  # kırmızı
    if proba >= 0.3:
        return "#f57c00"  # turuncu
    if proba >= threshold:
        return "#fbc02d"  # sarı
    return "#bbdefb"      # açık mavi (low)


def state_to_color(state: str) -> str:
    """Trap state → renk (markers için)."""
    return {
        "active": "#4caf50",    # yeşil
        "closed": "#9e9e9e",    # gri
        "missing": "#f44336",   # kırmızı
    }.get(state, "#9e9e9e")


def status_to_color(status: str) -> str:
    """Check status → renk (markers için)."""
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
    """Lab species → renk."""
    return {
        "Culex": "#1976d2",      # mavi
        "Aedes": "#d32f2f",      # kırmızı
        "Mixed": "#7b1fa2",      # mor
        "Other": "#757575",      # gri
        "Negative": "#bdbdbd",   # açık gri
    }.get(species, "#757575")


# ============== FORMAT HELPERS ==============

def fmt_proba(p: float) -> str:
    """0.847 → '0.85' (gösterim için)."""
    if pd.isna(p):
        return "—"
    return f"{p:.2f}"


def fmt_count(n) -> str:
    """Birey sayısı formatla."""
    if pd.isna(n) or n == 0:
        return "0"
    return f"{int(n)}"


def safe_int(v, default=0) -> int:
    """Güvenli int çevirme (None/NaN korumalı)."""
    try:
        if pd.isna(v):
            return default
        return int(v)
    except (ValueError, TypeError):
        return default


# ============== METRICS ==============

def compute_label_counts() -> dict:
    """Lab-confirmed hücre sayıları (per species, per district)."""
    labeled = load_labeled_cells()
    if len(labeled) == 0:
        return {"total": 0, "culex_pos": 0, "culex_neg": 0, "aedes_pos": 0, "aedes_neg": 0}

    total = labeled["cell_id"].nunique()

    # Culex: Culex pozitif, diğer her şey negatif
    culex_pos = labeled[labeled["species"] == "Culex"]["cell_id"].nunique()
    culex_neg = total - culex_pos

    # Aedes: Aedes pozitif
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
    """Trap durum istatistikleri."""
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


# ============== AUTH HELPER ==============

def require_auth():
    """Auth check, yoksa dur."""
    if not st.session_state.get("authenticated", False):
        st.warning("🔐 Giriş yapın (ana sayfaya dönün)")
        st.stop()
