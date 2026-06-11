"""utils.py — Tüm sayfalar için ortak helper'lar.

Cache'li veri yükleme, renk skalası, format helper'ları.

VERİ KAYNAĞI STRATEJİSİ (v0.6):
- cells_full.parquet → statik bundle, lokalden oku (37K hücre, 2MB)
- features_cache_active.parquet → aylık güncellenen GEE cache, lokalden oku
- ml_output (Sheets) → sadece yazma için, ML prediction sonuçları
- Sheets (sampling, trap_checks, lab_results, watch_list) → dinamik veri
"""
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional

import sheets_client
from config import DISTRICTS


# ============== PATHS ==============

STREAMLIT_DIR = Path(__file__).parent
DATA_DIR = STREAMLIT_DIR / "data"
CELLS_PARQUET = DATA_DIR / "cells_full.parquet"
FEATURES_PARQUET = DATA_DIR / "features_cache_active.parquet"


# ============== STATIK VERİ YÜKLEME (PARQUET) ==============

@st.cache_data(ttl=3600, show_spinner=False)
def load_static_cells() -> pd.DataFrame:
    """cells_full.parquet'tan statik hücre verisi (37K hücre, ~2MB).

    Streamlit Cloud bundle içinde. ASLA değişmez.
    """
    if not CELLS_PARQUET.exists():
        st.error(f"❌ Statik cells dosyası yok: {CELLS_PARQUET}")
        st.info("💡 `python scripts/build_cells_parquet.py` ile üret")
        return pd.DataFrame()
    df = pd.read_parquet(CELLS_PARQUET)
    # dtype düzeltme
    df["cell_id"] = pd.to_numeric(df["cell_id"], errors="coerce").astype("Int64")
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def load_static_features() -> pd.DataFrame:
    """features_cache_active.parquet'tan GEE feature'ları.

    Aylık lokalde güncellenir, Streamlit Cloud bundle'a replace edilir.
    Yoksa boş DataFrame döner (ML predict yapılamaz).
    """
    if not FEATURES_PARQUET.exists():
        st.warning(
            "⚠️ features_cache_active.parquet bulunamadı. "
            "ML predict için önce `python scripts/fetch_gee_features.py --initial` çalıştır."
        )
        return pd.DataFrame()
    df = pd.read_parquet(FEATURES_PARQUET)
    df["cell_id"] = pd.to_numeric(df["cell_id"], errors="coerce").astype("Int64")
    return df


def has_static_features() -> bool:
    """Feature cache hazır mı?"""
    return FEATURES_PARQUET.exists()


# ============== ML OUTPUT (SHEETS) ==============

@st.cache_data(ttl=300, show_spinner=False)
def load_ml_output() -> pd.DataFrame:
    """Sheets'ten sadece ML output (proba + tier).

    cells sheet'inin TAMAMINI çekmiyoruz, sadece ML kolonlarını alıyoruz.
    """
    try:
        df = sheets_client.get_cells()
    except Exception as e:
        st.warning(f"ML output yüklenemedi: {e}")
        return pd.DataFrame()
    if len(df) == 0:
        return df
    # Sadece gerekli kolonlar
    keep = ["cell_id"]
    for c in ["culex_proba", "aedes_proba", "confidence_tier", "last_updated"]:
        if c in df.columns:
            keep.append(c)
    return df[keep].copy()


def update_ml_output(species: str, proba_map: dict[int, float]):
    """Sheets'teki cells sheet'inin ML kolonlarını güncelle."""
    cells_full = sheets_client.read_sheet("cells")
    if len(cells_full) == 0:
        return
    col = f"{species}_proba"
    if col not in cells_full.columns:
        return
    cells_full[col] = cells_full["cell_id"].map(
        lambda c: float(proba_map.get(int(c), np.nan))
    )
    from utils import _proba_to_tier, clear_all_caches
    cells_full["confidence_tier"] = cells_full[col].apply(_proba_to_tier)
    cells_full["last_updated"] = pd.Timestamp.now().strftime("%Y-%m-%d")
    sheets_client.update_dataframe("cells", cells_full)
    clear_all_caches()


# ============== MERGE: CELLS + FEATURES + ML OUTPUT ==============

@st.cache_data(ttl=300, show_spinner=False)
def load_merged_cells() -> pd.DataFrame:
    """Statik cells + ML output birleşik (parquet + Sheets)."""
    cells = load_static_cells()
    if len(cells) == 0:
        return cells
    ml = load_ml_output()
    if len(ml) > 0:
        # Sadece ML output kolonlarını birleştir
        ml_cols = [c for c in ml.columns if c in ["cell_id", "culex_proba", "aedes_proba", "confidence_tier", "last_updated"]]
        cells = cells.merge(ml[ml_cols], on="cell_id", how="left", suffixes=("", "_ml"))
    return cells


# ============== ESKİ SHEETS'TEN OKUMA (geriye uyumluluk) ==============

@st.cache_data(ttl=300, show_spinner=False)
def load_cells() -> pd.DataFrame:
    """DEPRECATED: load_static_cells() veya load_merged_cells() kullan.

    Geriye uyumluluk için Sheets'ten okur.
    """
    return load_merged_cells()


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


def safe_cell_id(v) -> str:
    """Cell_id'yi güvenli string'e çevir (Int64, None, NaN korumalı)."""
    try:
        if pd.isna(v):
            return "?"
        return str(int(float(v)))
    except (ValueError, TypeError):
        return "?"


def safe_int(v, default=0) -> int:
    """Güvenli int çevirme (None/NaN korumalı)."""
    try:
        if pd.isna(v):
            return default
        return int(v)
    except (ValueError, TypeError):
        return default


def _proba_to_tier(p) -> str:
    """ML olasılığını confidence tier'a çevir."""
    if pd.isna(p):
        return "unknown"
    try:
        p = float(p)
    except (ValueError, TypeError):
        return "unknown"
    if p >= 0.7:
        return "high"
    if p >= 0.4:
        return "medium"
    if p >= 0.2:
        return "low"
    return "unknown"


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
