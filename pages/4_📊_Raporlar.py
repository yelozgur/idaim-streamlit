"""4_📊_Raporlar.py — Validation metrikleri, per-district, trend.

Plotly grafikleri:
- Lab tür dağılımı (pie)
- District bazlı lab count (bar)
- Trap durumları (timeline)
- Son 30 gün aktivite trendi
- Per-district ML tahmin istatistikleri (cells sheet'inden)
"""
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import mobile_styles
import utils
from utils import (
    load_merged_cells as load_cells,
    load_sampling_initiations, load_trap_checks, load_lab_results,
    load_watch_list, load_traps_with_state, load_labeled_cells,
    fmt_proba, fmt_count, compute_label_counts, compute_trap_counts,
    species_to_color, status_to_color,
)


# ============== PAGE SETUP ==============

st.set_page_config(page_title="Raporlar", page_icon="📊", layout="wide")
mobile_styles.inject_mobile_css()
utils.require_auth()


# ============== HEADER ==============

st.title("📊 Raporlar")
st.caption("Validation metrikleri, per-district istatistikler, operasyonel trend")


# ============== VERİ YÜKLE ==============

cells = load_cells()
inits = load_sampling_initiations()
checks = load_trap_checks()
labs = load_lab_results()
watch = load_watch_list()
labeled = load_labeled_cells()
traps_full = load_traps_with_state()


# ============== ÜST METRİKLER ==============

st.subheader("📈 Genel Durum")
col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("🗺️ Hücre", len(cells))
col2.metric("🪤 Trap Kurulmuş", len(inits))
col3.metric("🔍 Check", len(checks))
col4.metric("🧪 Lab Sonucu", len(labs))
col5.metric("👀 Watch List", len(watch))
col6.metric("📍 Active Trap", compute_trap_counts()["active"])

st.markdown("---")


# ============== TÜR DAĞILIMI ==============

st.subheader("🦟 Tür Dağılımı (Lab)")

if len(labs) > 0:
    species_count = labs["species"].value_counts().reset_index()
    species_count.columns = ["species", "count"]

    fig = px.pie(
        species_count, values="count", names="species",
        color="species",
        color_discrete_map={
            "Culex": "#1976d2", "Aedes": "#d32f2f", "Mixed": "#7b1fa2",
            "Other": "#757575", "Negative": "#bdbdbd",
        },
        hole=0.4,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=350, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Henüz lab sonucu yok.")


# ============== DISTRICT BAZLI ==============

st.subheader("📍 District Bazlı İstatistikler")

if len(labs) > 0 and len(cells) > 0:
    # Lab-confirmed hücrelerde district dağılımı
    district_stats = []
    for district in config.DISTRICTS:
        district_cells = cells[cells["district"] == district]
        n_cells = len(district_cells)

        # Lab sonuçları bu district'te
        district_cell_ids = district_cells["cell_id"].astype(int).tolist()
        district_labs = labs[labs["cell_id"].isin(district_cell_ids)]

        species_breakdown = {}
        for sp in ["Culex", "Aedes", "Mixed", "Other", "Negative"]:
            species_breakdown[sp] = int((district_labs["species"] == sp).sum())

        district_stats.append({
            "District": district,
            "Toplam Hücre": n_cells,
            "Lab Sonucu": len(district_labs),
            "Culex": species_breakdown["Culex"],
            "Aedes": species_breakdown["Aedes"],
            "Other": species_breakdown["Other"] + species_breakdown["Mixed"],
        })

    district_df = pd.DataFrame(district_stats)

    fig = go.Figure()
    for sp, color in [("Culex", "#1976d2"), ("Aedes", "#d32f2f"), ("Other", "#757575")]:
        fig.add_trace(go.Bar(
            name=sp, x=district_df["District"], y=district_df[sp],
            marker_color=color,
        ))

    fig.update_layout(
        barmode="stack", height=400,
        xaxis_title="District", yaxis_title="Lab-confirmed Hücre Sayısı",
        margin=dict(t=20, b=20, l=20, r=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("📋 Detaylı tablo"):
        st.dataframe(district_df, use_container_width=True, hide_index=True)
else:
    st.info("District analizi için lab sonucu gerekli.")


# ============== ML OUTPUT PER DISTRICT ==============

st.subheader("🤖 ML Tahmin İstatistikleri (per District)")

if len(cells) > 0 and "culex_proba" in cells.columns:
    # culex_proba parse et
    cells["culex_proba_num"] = pd.to_numeric(cells["culex_proba"], errors="coerce")

    # District bazlı istatistik
    ml_stats = []
    for district in config.DISTRICTS:
        d = cells[cells["district"] == district]
        n = len(d)
        n_high = int((d["culex_proba_num"] >= 0.7).sum())
        n_med = int(((d["culex_proba_num"] >= 0.4) & (d["culex_proba_num"] < 0.7)).sum())
        n_low = int(((d["culex_proba_num"] >= 0.1) & (d["culex_proba_num"] < 0.4)).sum())
        n_unknown = int(d["culex_proba_num"].isna().sum())

        mean_proba = d["culex_proba_num"].mean() if d["culex_proba_num"].notna().any() else None

        ml_stats.append({
            "District": district,
            "Hücre": n,
            "Yüksek (≥0.7)": n_high,
            "Orta (0.4-0.7)": n_med,
            "Düşük (0.1-0.4)": n_low,
            "Bilinmiyor": n_unknown,
            "Ortalama Proba": fmt_proba(mean_proba) if mean_proba is not None else "—",
        })

    ml_df = pd.DataFrame(ml_stats)
    st.dataframe(ml_df, use_container_width=True, hide_index=True)

    # Confidence tier dağılımı
    if "confidence_tier" in cells.columns:
        tier_count = cells["confidence_tier"].value_counts().reset_index()
        tier_count.columns = ["tier", "count"]

        fig = px.bar(
            tier_count, x="tier", y="count",
            color="tier",
            color_discrete_map={"high": "#7f0000", "medium": "#f57c00", "low": "#fbc02d", "unknown": "#9aa0a6"},
        )
        fig.update_layout(height=300, showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("ML henüz çalıştırılmadı. Sayfa 3'te retrain yapın.")


# ============== TRAP TIMELINE ==============

st.subheader("🪤 Trap Aktivite Trendi")

if len(inits) > 0 and "sampling_start_time" in inits.columns:
    inits["date"] = pd.to_datetime(inits["sampling_start_time"], errors="coerce").dt.date
    daily_inits = inits.groupby("date").size().reset_index(name="count")
    daily_inits = daily_inits.sort_values("date")

    fig = px.line(
        daily_inits, x="date", y="count",
        markers=True,
        labels={"count": "Yeni Trap", "date": "Tarih"},
    )
    fig.update_traces(line_color="#1a73e8", marker=dict(size=8))
    fig.update_layout(height=350, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Henüz trap kurulumu yok.")


# ============== LAB CONFIDENCE ==============

st.subheader("🔬 Lab Confidence Dağılımı")

if len(labs) > 0 and "lab_confidence" in labs.columns:
    conf_count = labs["lab_confidence"].value_counts().reset_index()
    conf_count.columns = ["confidence", "count"]

    fig = px.bar(
        conf_count, x="confidence", y="count",
        color="confidence",
        color_discrete_map={"high": "#4caf50", "medium": "#fbc02d", "low": "#f57c00"},
        category_orders={"confidence": ["high", "medium", "low"]},
    )
    fig.update_layout(height=300, showlegend=False, margin=dict(t=20, b=20, l=20, r=20))
    st.plotly_chart(fig, use_container_width=True)

    st.caption("""
    **lab_confidence otomatik hesaplanır:**
    - `high`: Adult + Molecular
    - `medium`: Larva + Morphological (veya diğer kombinasyonlar)
    - `low`: Egg + Morphological
    """)
else:
    st.info("Lab sonucu yok.")


# ============== SPECIMEN LIFECYCLE & METHOD ==============

st.subheader("🧪 Specimen Lifecycle & Method")

if len(labs) > 0:
    col_l1, col_l2 = st.columns(2)

    with col_l1:
        if "specimen_lifecycle" in labs.columns:
            lc = labs["specimen_lifecycle"].value_counts().reset_index()
            lc.columns = ["lifecycle", "count"]
            fig = px.pie(lc, values="count", names="lifecycle", hole=0.4)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig, use_container_width=True)

    with col_l2:
        if "identification_method" in labs.columns:
            im = labs["identification_method"].value_counts().reset_index()
            im.columns = ["method", "count"]
            fig = px.pie(im, values="count", names="method", hole=0.4)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(height=300, margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Lab sonucu yok.")


# ============== SON AKTİVİTELER ==============

st.subheader("📅 Son Aktiviteler")

col_act1, col_act2, col_act3 = st.columns(3)

with col_act1:
    st.markdown("**🪤 Son Trap Kurulumları**")
    if len(inits) > 0 and "sampling_start_time" in inits.columns:
        recent_init = inits[["trap_id", "cell_id", "operator", "sampling_start_time"]].copy()
        recent_init["sampling_start_time"] = pd.to_datetime(recent_init["sampling_start_time"], errors="coerce")
        recent_init = recent_init.sort_values("sampling_start_time", ascending=False).head(5)
        for _, row in recent_init.iterrows():
            st.caption(f"• {row['trap_id']} — cell #{int(row['cell_id']) if pd.notna(row['cell_id']) else '?'} ({row['operator']})")
    else:
        st.caption("Henüz trap yok")

with col_act2:
    st.markdown("**🔍 Son Check'ler**")
    if len(checks) > 0 and "check_datetime" in checks.columns:
        recent_check = checks[["trap_id", "trap_status", "check_datetime"]].copy()
        recent_check["check_datetime"] = pd.to_datetime(recent_check["check_datetime"], errors="coerce")
        recent_check = recent_check.sort_values("check_datetime", ascending=False).head(5)
        for _, row in recent_check.iterrows():
            st.caption(f"• {row['trap_id']} — {row['trap_status']}")
    else:
        st.caption("Henüz check yok")

with col_act3:
    st.markdown("**🧪 Son Lab Sonuçları**")
    if len(labs) > 0 and "lab_date" in labs.columns:
        recent_lab = labs[["trap_id", "species", "count", "lab_date"]].copy()
        recent_lab["lab_date"] = pd.to_datetime(recent_lab["lab_date"], errors="coerce")
        recent_lab = recent_lab.sort_values("lab_date", ascending=False).head(5)
        for _, row in recent_lab.iterrows():
            sp_emoji = {"Culex": "🔵", "Aedes": "🔴", "Mixed": "🟣", "Other": "⚪", "Negative": "⚫"}.get(row["species"], "❓")
            st.caption(f"• {row['trap_id']} — {sp_emoji} {row['species']} (×{fmt_count(row['count'])})")
    else:
        st.caption("Henüz lab sonucu yok")


# Footer
st.markdown("---")
st.caption(f"📅 Rapor zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | IDAIM Cyprus v0.5")
