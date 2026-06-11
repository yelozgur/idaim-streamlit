"""2_🗺️_Dashboard.py — Operasyonel dashboard.

- Folium harita: 642 hücre (proba heatmap), trap markers, lab markers
- Watch list paneli (sağda)
- Filtreler: tür, confidence, district
- Toplu trap kur (watch list'ten seçili → Sayfa 1'e prefill)
"""
import streamlit as st
import pandas as pd
import numpy as np
from streamlit_folium import st_folium
import folium
from folium.plugins import HeatMap, MarkerCluster

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
    proba_to_color, state_to_color, status_to_color, species_to_color,
    fmt_proba, fmt_count, safe_cell_id, compute_trap_counts, compute_label_counts,
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


# Folium harita oluştur
if len(cells) == 0:
    st.warning("Filtreler sonrası gösterilecek hücre kalmadı. Filtreleri gevşet.")
    st.stop()

# Cyprus merkez
m = folium.Map(
    location=[34.9, 33.2],
    zoom_start=9,
    tiles="OpenStreetMap",
    control_scale=True,
)

# Hangi kolon kullanılacak
proba_col = "culex_proba" if "Culex" in species_filter else (
    "aedes_proba" if "Aedes" in species_filter else "culex_proba"
)

# Hücreler (CircleMarker)
cells_layer = folium.FeatureGroup(name="Hücreler", show=True)
for _, row in cells.iterrows():
    proba = pd.to_numeric(row.get(proba_col), errors="coerce")
    color = proba_to_color(proba, threshold=0.10)

    popup_html = f"""
    <b>Hücre #{safe_cell_id(row['cell_id'])}</b><br>
    District: {row.get('district', '?')}<br>
    Lat/Lon: {row['lat']:.4f}, {row['lon']:.4f}<br>
    <hr>
    <b>Culex proba:</b> {fmt_proba(row.get('culex_proba'))}<br>
    <b>Aedes proba:</b> {fmt_proba(row.get('aedes_proba'))}<br>
    <b>Confidence:</b> {row.get('confidence_tier', '?')}<br>
    <b>Son güncelleme:</b> {row.get('last_updated', '?')}
    """

    folium.CircleMarker(
        location=[row["lat"], row["lon"]],
        radius=6,
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=f"#{safe_cell_id(row['cell_id'])} | {row.get('district', '?')} | {fmt_proba(proba)}",
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.6,
        weight=1,
    ).add_to(cells_layer)
cells_layer.add_to(m)


# Trap markers
if show_traps and len(traps_df) > 0:
    traps_layer = folium.FeatureGroup(name="🪤 Trap'ler", show=True)
    for _, row in traps_df.iterrows():
        if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
            continue

        # Renk: state veya son check durumu
        if pd.notna(row.get("last_check")):
            color = status_to_color(row["last_check"])
        else:
            color = state_to_color(row.get("state", "active"))

        popup_html = f"""
        <b>Trap {row['trap_id']}</b><br>
        Hücre: #{safe_cell_id(row['cell_id'])} ({row.get('district', '?')})<br>
        Operator: {row.get('operator', '?')}<br>
        Method: {row.get('sampling_method', '?')}<br>
        State: {row.get('state', '?')}<br>
        <hr>
        <b>Son check:</b> {row.get('last_check', '—')}<br>
        <b>Check zamanı:</b> {row.get('last_check_time', '—')}<br>
        <b>Check sayısı:</b> {fmt_count(row.get('n_checks'))}
        """

        # Icon tipi
        icon = "circle" if row.get("state") == "active" else "circle"
        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{row['trap_id']} ({row.get('last_check', row.get('state', '?'))})",
            icon=folium.Icon(color=color.split("#")[0] if not color.startswith("#") else "blue",
                            icon_color=color, icon="bug", prefix="fa"),
        ).add_to(traps_layer)
    traps_layer.add_to(m)


# Lab markers
if show_labs and len(labs_df) > 0:
    labs_layer = folium.FeatureGroup(name="🧪 Lab Sonuçları", show=True)
    for _, row in labs_df.iterrows():
        # Cell bilgisi
        cell = cells[cells["cell_id"] == row["cell_id"]]
        if len(cell) == 0:
            continue
        lat, lon = cell.iloc[0]["lat"], cell.iloc[0]["lon"]

        color = species_to_color(row.get("species", "Other"))
        species_short = row.get("species", "?")[:1]  # C / A / M / O / N

        popup_html = f"""
        <b>Lab — {row['lab_id']}</b><br>
        Trap: {row['trap_id']}<br>
        Hücre: #{safe_cell_id(row['cell_id'])}<br>
        <hr>
        <b>Tür:</b> {row.get('species', '?')}<br>
        <b>Birey:</b> {fmt_count(row.get('count'))}<br>
        <b>Lifecycle:</b> {row.get('specimen_lifecycle', '?')}<br>
        <b>Method:</b> {row.get('identification_method', '?')}<br>
        <b>Confidence:</b> {row.get('lab_confidence', '?')}<br>
        <b>Tarih:</b> {row.get('lab_date', '?')}<br>
        <b>Operator:</b> {row.get('lab_operator', '?')}
        """

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{row.get('species', '?')} ×{fmt_count(row.get('count'))}",
            icon=folium.DivIcon(
                html=f'<div style="background:{color};color:white;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:12px;border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.3)">{species_short}</div>',
                icon_size=(24, 24),
                icon_anchor=(12, 12),
            ),
        ).add_to(labs_layer)
    labs_layer.add_to(m)


# Layer control
folium.LayerControl(collapsed=False).add_to(m)


# Haritayı göster
map_data = st_folium(
    m,
    height=550,
    returned_objects=["last_clicked"],
    key="dashboard_map",
    use_container_width=True,
)


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
