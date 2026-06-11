"""2_🗺️_Dashboard.py — Operasyonel dashboard.

- Plotly scatter_map (WebGL) ile 37K hücre — hızlı render
- Watch list paneli (sağda)
- Filtreler: tür, confidence, district
- Toplu trap kur (watch list'ten seçili → Sayfa 1'e prefill)
"""
import streamlit as st
import pandas as pd
import numpy as np
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
    fmt_proba, fmt_count, safe_cell_id, compute_trap_counts, compute_label_counts,
    proba_to_color, state_to_color, status_to_color, species_to_color,
    clear_all_caches,
)


# ============== PAGE SETUP ==============

st.set_page_config(page_title="Dashboard", page_icon="🗺️", layout="wide")
mobile_styles.inject_mobile_css()
utils.require_auth()


# ============== HEADER ==============

st.title("🗺️ Dashboard")
st.caption("642 grid hücre + trap'ler + lab sonuçları + ML watch list")

# Cache temizleme butonu
col_refresh, col_info = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 Yenile", use_container_width=True, help="Cache temizle"):
        clear_all_caches()
        st.rerun()
with col_info:
    st.caption("Sheets'ten okunmuş veriler 5dk cache'li. Manuel yenile için tıkla.")


# ============== METRICS ROW ==============

trap_counts = compute_trap_counts()
label_counts = compute_label_counts()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("🗺️ Hücre", f"{len(load_cells())}")
col2.metric("🪤 Aktif Trap", f"{trap_counts['active']}")
col3.metric("🔍 Toplam Check", f"{len(load_trap_checks())}")
col4.metric("🧪 Lab Sonucu", f"{label_counts['total']}")
col5.metric("👀 Watch List", f"{len(load_watch_list())}")

st.markdown("---")


# ============== FILTERS ==============

st.subheader("🎛️ Filtreler")
fcol1, fcol2, fcol3, fcol4 = st.columns(4)

with fcol1:
    species_filter = st.selectbox(
        "Tür / Renk skalası",
        ["Culex (proba)", "Aedes (proba)", "Lab sonuçları"],
        key="dash_species",
    )

with fcol2:
    district_filter = st.multiselect(
        "District",
        options=config.DISTRICTS,
        default=config.DISTRICTS,
        key="dash_district",
    )

with fcol3:
    confidence_filter = st.selectbox(
        "Confidence",
        ["Tümü", "Sadece yüksek (≥0.7)", "Orta+yüksek (≥0.4)", "Sadece unknown"],
        key="dash_confidence",
    )

with fcol4:
    show_traps = st.checkbox("🪤 Trap'leri göster", value=True)
    show_labs = st.checkbox("🧪 Lab markerları göster", value=True)
    show_watch_only = st.checkbox("👀 Sadece watch list", value=False)


# ============== HARİTA ==============

st.markdown("---")
st.subheader("🗺️ Harita")

cells = load_cells()
traps_df = load_traps_with_state()
labs_df = load_lab_results()
watch_df = load_watch_list()

# Filtre uygula
if len(cells) > 0 and len(district_filter) < len(config.DISTRICTS):
    cells = cells[cells["district"].isin(district_filter)]

# Watch list filter
if show_watch_only and len(watch_df) > 0:
    if species_filter == "Culex (proba)":
        watch_cells = watch_df[watch_df["species"] == "culex"]["cell_id"].tolist()
    elif species_filter == "Aedes (proba)":
        watch_cells = watch_df[watch_df["species"] == "aedes"]["cell_id"].tolist()
    else:
        watch_cells = watch_df["cell_id"].tolist()
    if len(cells) > 0:
        cells = cells[cells["cell_id"].isin(watch_cells)]

# Confidence filter
if len(cells) > 0 and confidence_filter != "Tümü":
    if species_filter == "Culex (proba)":
        col = "culex_proba"
    elif species_filter == "Aedes (proba)":
        col = "aedes_proba"
    else:
        col = "culex_proba"  # lab modunda varsayılan

    if confidence_filter == "Sadece yüksek (≥0.7)":
        cells = cells[pd.to_numeric(cells[col], errors="coerce") >= 0.7]
    elif confidence_filter == "Orta+yüksek (≥0.4)":
        cells = cells[pd.to_numeric(cells[col], errors="coerce") >= 0.4]
    elif confidence_filter == "Sadece unknown":
        cells = cells[pd.to_numeric(cells[col], errors="coerce").isna()]



# ============== PLOTLY HARİTA (WebGL — Folium yerine, 100x hızlı) ==============

if len(cells) == 0:
    st.warning("Filtreler sonrası gösterilecek hücre kalmadı. Filtreleri gevşet.")
    st.stop()

# Proba parse
if species_filter == "Culex (proba)":
    proba_col = "culex_proba"
elif species_filter == "Aedes (proba)":
    proba_col = "aedes_proba"
else:
    proba_col = "culex_proba"  # lab modu

cells_view = cells.copy()
cells_view[proba_col] = pd.to_numeric(cells_view[proba_col], errors="coerce")
cells_view["cv_cell_id_str"] = cells_view["cell_id"].apply(safe_cell_id)

# Hover text hazırla
cells_view["hover_text"] = cells_view.apply(
    lambda r: (
        f"<b>Hücre #{r['cv_cell_id_str']}</b><br>"
        f"District: {r.get('district', '?')}<br>"
        f"Lat/Lon: {r['lat']:.4f}, {r['lon']:.4f}<br>"
        f"Culex: {fmt_proba(r.get('culex_proba'))}<br>"
        f"Aedes: {fmt_proba(r.get('aedes_proba'))}<br>"
        f"Confidence: {r.get('confidence_tier', '?')}"
    ),
    axis=1
)

# Ana hücre katmanı (Plotly scatter_map — WebGL)
fig = go.Figure()

# Hücreler
fig.add_trace(go.Scattermap(
    lat=cells_view["lat"],
    lon=cells_view["lon"],
    mode="markers",
    marker=dict(
        size=8,
        color=cells_view[proba_col].fillna(0).values,
        colorscale=[
            [0.0, "#bbdefb"],
            [0.1, "#fbc02d"],
            [0.3, "#f57c00"],
            [0.5, "#d32f2f"],
            [0.7, "#7f0000"],
            [1.0, "#7f0000"],
        ],
        cmin=0,
        cmax=1,
        showscale=True,
        colorbar=dict(title="Proba", x=1.02),
        opacity=0.7,
    ),
    text=cells_view["hover_text"],
    hoverinfo="text",
    name="Hücreler",
))

# Trap'ler
if show_traps and len(traps_df) > 0:
    trap_view = traps_df.dropna(subset=["lat", "lon"]).copy()
    if len(trap_view) > 0:
        trap_view["color"] = trap_view.apply(
            lambda r: status_to_color(r.get("last_check")) if pd.notna(r.get("last_check"))
            else state_to_color(r.get("state", "active")),
            axis=1,
        )
        trap_view["hover"] = trap_view.apply(
            lambda r: (
                f"<b>🪤 {r['trap_id']}</b><br>"
                f"Cell: #{safe_cell_id(r.get('cell_id'))}<br>"
                f"Operator: {r.get('operator', '?')}<br>"
                f"State: {r.get('state', '?')}<br>"
                f"Son check: {r.get('last_check', '—')}"
            ),
            axis=1,
        )
        fig.add_trace(go.Scattermap(
            lat=trap_view["lat"],
            lon=trap_view["lon"],
            mode="markers",
            marker=dict(
                size=18,
                color=trap_view["color"].tolist(),
                symbol="circle",
                line=dict(color="white", width=2),
            ),
            text=trap_view["hover"],
            hoverinfo="text",
            name="🪤 Trap'ler",
        ))

# Lab sonuçları
if show_labs and len(labs_df) > 0:
    lab_view = labs_df.merge(
        cells_view[["cell_id", "lat", "lon"]].rename(columns={"cell_id": "cell_id_lab"}),
        left_on="cell_id", right_on="cell_id_lab", how="left",
    ).dropna(subset=["lat", "lon"])
    if len(lab_view) > 0:
        lab_view["color"] = lab_view["species"].apply(species_to_color)
        lab_view["letter"] = lab_view["species"].str[:1]
        fig.add_trace(go.Scattermap(
            lat=lab_view["lat"],
            lon=lab_view["lon"],
            mode="markers",
            marker=dict(
                size=22,
                color=lab_view["color"].tolist(),
                symbol="circle",
                line=dict(color="white", width=2),
            ),
            text=lab_view.apply(
                lambda r: f"<b>🧪 {r.get('species', '?')}</b> ×{fmt_count(r.get('count'))}<br>"
                          f"Trap: {r.get('trap_id', '?')}<br>"
                          f"Confidence: {r.get('lab_confidence', '?')}",
                axis=1,
            ),
            hoverinfo="text",
            name="🧪 Lab",
        ))

# Layout (Cyprus ortası, OpenStreetMap)
fig.update_layout(
    map=dict(
        style="open-street-map",
        center=dict(lat=34.9, lon=33.2),
        zoom=9,
    ),
    height=550,
    margin=dict(t=0, b=0, l=0, r=0),
    showlegend=True,
    legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01, bgcolor="rgba(255,255,255,0.8)"),
)

# Render et (config ile scroll/zoom aktif)
st.plotly_chart(fig, use_container_width=True, config={
    "scrollZoom": True,
    "displayModeBar": True,
    "displaylogo": False,
})

st.caption(f"📊 Toplam: {len(cells_view):,} hücre gösteriliyor (Plotly WebGL, hızlı)")


# İlk versiyon: tüm hücreleri render et (MarkerCluster optimize eder)


# ============== WATCH LIST ==============

st.markdown("---")
st.subheader("👀 Watch List")
st.caption("ML'in önerdiği yüksek olasılıklı hücreler (henüz trap kurulmamış)")

watch_df = load_watch_list()
if len(watch_df) == 0:
    st.info("Watch list boş. ML Retrain sayfasından model çalıştırın.")
else:
    # Tür filtresi
    wspecies = st.radio(
        "Tür",
        ["culex", "aedes"],
        horizontal=True,
        key="watch_species",
    )
    wdf = watch_df[watch_df["species"] == wspecies].copy()
    wdf = wdf.sort_values("proba", ascending=False).head(50)

    if len(wdf) == 0:
        st.info(f"{wspecies} için watch list boş.")
    else:
        # District bazlı özet
        st.caption(f"📊 {len(wdf)} hücre watch'ta, district bazlı:")
        district_summary = wdf.groupby("district").size().reset_index(name="count")
        dcols = st.columns(min(6, len(district_summary)))
        for i, (_, drow) in enumerate(district_summary.iterrows()):
            with dcols[i % len(dcols)]:
                st.metric(drow["district"], int(drow["count"]))

        # Tablo
        display_df = wdf[["cell_id", "district", "proba", "threshold_used", "visited"]].copy()
        display_df["proba"] = display_df["proba"].apply(fmt_proba)
        display_df["threshold_used"] = display_df["threshold_used"].apply(fmt_proba)
        display_df.columns = ["Cell", "District", "Proba", "Threshold", "Ziyaret"]

        st.dataframe(display_df, use_container_width=True, height=300)

        # Toplu trap kur (Sayfa 1'e yönlendir)
        st.markdown("##### 🎯 Trap Kur (Watch List'ten)")
        st.caption("Seçili hücreler için trap kurulumu başlat")

        # Session state ile Sayfa 1'e prefill
        if "prefill_cells" not in st.session_state:
            st.session_state.prefill_cells = []

        # Multiselect
        cell_options = wdf["cell_id"].astype(str) + " — " + wdf["district"] + " (proba=" + wdf["proba"].apply(fmt_proba) + ")"
        selected = st.multiselect(
            "Hücre seç (trap kurmak için)",
            options=cell_options.tolist(),
            key="watch_selected",
        )

        if st.button("🪤 Seçili Hücreler İçin Sayfa 1'e Git", type="primary"):
            if not selected:
                st.warning("Önce hücre seçin")
            else:
                # Cell_id'leri parse et
                selected_ids = [int(s.split(" — ")[0]) for s in selected]
                st.session_state.prefill_cells = selected_ids
                st.switch_page("pages/1_📥_Veri_Girişi.py")


# ============== ÖZET İSTATİSTİKLER ==============

st.markdown("---")
st.subheader("📈 Özet")

scol1, scol2 = st.columns(2)

with scol1:
    st.markdown("**🧪 Lab Türleri (per species)**")
    if len(labs_df) > 0:
        species_count = labs_df["species"].value_counts()
        for sp, cnt in species_count.items():
            color = species_to_color(sp)
            st.markdown(
                f'<span style="background:{color};color:white;padding:2px 10px;border-radius:12px;font-size:14px">{sp}</span> {int(cnt)} trap',
                unsafe_allow_html=True,
            )
    else:
        st.caption("Henüz lab sonucu yok")

with scol2:
    st.markdown("**🪤 Trap Durumları**")
    if len(traps_df) > 0:
        # Son check bazlı
        if "last_check" in traps_df.columns:
            status_count = traps_df["last_check"].value_counts(dropna=False)
            for st_name, cnt in status_count.items():
                if pd.isna(st_name):
                    label, color = "Kontrol edilmedi", "#bbdefb"
                else:
                    label, color = st_name, status_to_color(st_name)
                st.markdown(
                    f'<span style="background:{color};color:white;padding:2px 10px;border-radius:12px;font-size:14px">{label}</span> {int(cnt)} trap',
                    unsafe_allow_html=True,
                )
    else:
        st.caption("Henüz trap kurulmamış")


# Footer
st.markdown("---")
st.caption("""
🎨 **Renk skalası:** 🔴 Bordo (≥0.7) → 🔴 Kırmızı (≥0.5) → 🟠 Turuncu (≥0.3) → 🟡 Sarı (≥0.10) → 🔵 Açık mavi (low) → ⬜ Gri (unknown)
""")
