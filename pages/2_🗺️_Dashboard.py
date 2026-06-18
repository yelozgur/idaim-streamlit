"""2_🗺️_Dashboard.py — Operational dashboard.

- Folium map: cells (proba heatmap), trap markers, lab markers
- Watch list panel
- Filters: species, confidence, district
- Trap setup shortcut from watch list
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
    load_cells, load_sampling_initiations, load_trap_checks, load_lab_results,
    load_watch_list, load_traps_with_state, load_labeled_cells,
    proba_to_color, state_to_color, status_to_color, species_to_color,
    hex_to_folium_name,
    fmt_proba, fmt_count, compute_trap_counts, compute_label_counts,
    clear_all_caches, require_auth,
)


# ============== PAGE SETUP ==============

st.set_page_config(page_title="Dashboard", page_icon="🗺️", layout="wide")
mobile_styles.inject_mobile_css()
require_auth()


# Cyprus bounding box (filter out cells outside Cyprus, e.g. Egypt)
# Cyprus lat range: ~34.5-35.5, lon range: ~32.5-34.5
CYPRUS_LAT_MIN, CYPRUS_LAT_MAX = 34.0, 36.0
CYPRUS_LON_MIN, CYPRUS_LON_MAX = 32.0, 35.0


def _filter_cyprus(df: pd.DataFrame) -> pd.DataFrame:
    """Drop cells outside Cyprus bounding box."""
    if len(df) == 0:
        return df
    mask = (
        (df["lat"] >= CYPRUS_LAT_MIN) & (df["lat"] <= CYPRUS_LAT_MAX) &
        (df["lon"] >= CYPRUS_LON_MIN) & (df["lon"] <= CYPRUS_LON_MAX)
    )
    return df[mask].copy()


def _filter_cyprus_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to Cyprus, but if no cells remain keep all (defensive)."""
    if len(df) == 0:
        return df
    cyprus = _filter_cyprus(df)
    if len(cyprus) == 0:
        return df  # fallback: keep all
    return cyprus


# ============== HEADER ==============

st.title("Dashboard")
st.caption("Grid cells + traps + lab results + ML watch list")

col_refresh, col_info = st.columns([1, 5])
with col_refresh:
    if st.button("Refresh", use_container_width=True, help="Clear cache"):
        clear_all_caches()
        st.rerun()
with col_info:
    st.caption("Sheets data is cached for 5 min. Click Refresh to force reload.")


# ============== METRICS ROW ==============

trap_counts = compute_trap_counts()
label_counts = compute_label_counts()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Cells", f"{len(load_cells())}")
col2.metric("Active Traps", f"{trap_counts['active']}")
col3.metric("Total Checks", f"{len(load_trap_checks())}")
col4.metric("Lab Results", f"{label_counts['total']}")
col5.metric("Watch List", f"{len(load_watch_list())}")

st.markdown("---")


# ============== FILTERS ==============

st.subheader("Filters")
fcol1, fcol2, fcol3, fcol4 = st.columns(4)

with fcol1:
    species_filter = st.selectbox(
        "Color scale",
        ["Culex (proba)", "Aedes (proba)", "Lab results"],
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
        ["All", "High only (>=0.7)", "Medium+High (>=0.4)", "Unknown only"],
        key="dash_confidence",
    )

with fcol4:
    show_traps = st.checkbox("Show traps", value=True)
    show_labs = st.checkbox("Show lab markers", value=True)
    show_watch_only = st.checkbox("Watch list only", value=False)


# ============== MAP ==============

st.markdown("---")
st.subheader("Map")

all_cells = load_cells()
cells = _filter_cyprus_safe(all_cells)
traps_df = load_traps_with_state()
labs_df = load_lab_results()
watch_df = load_watch_list()

# Defensive warning if Cyprus filter dropped most cells
if len(cells) < len(all_cells) * 0.5 and len(all_cells) > 10:
    st.warning(f"{len(all_cells) - len(cells)} cells outside Cyprus bounds. Clean the cells sheet to remove them.")

# Filters
if len(cells) > 0 and len(district_filter) < len(config.DISTRICTS):
    cells = cells[cells["district"].isin(district_filter)]

if show_watch_only and len(watch_df) > 0:
    if species_filter == "Culex (proba)":
        watch_cells = watch_df[watch_df["species"] == "culex"]["cell_id"].tolist()
    elif species_filter == "Aedes (proba)":
        watch_cells = watch_df[watch_df["species"] == "aedes"]["cell_id"].tolist()
    else:
        watch_cells = watch_df["cell_id"].tolist()
    if len(cells) > 0:
        cells = cells[cells["cell_id"].isin(watch_cells)]

if len(cells) > 0 and confidence_filter != "All":
    if species_filter == "Culex (proba)":
        col = "culex_proba"
    elif species_filter == "Aedes (proba)":
        col = "aedes_proba"
    else:
        col = "culex_proba"

    if confidence_filter == "High only (>=0.7)":
        cells = cells[pd.to_numeric(cells[col], errors="coerce") >= 0.7]
    elif confidence_filter == "Medium+High (>=0.4)":
        cells = cells[pd.to_numeric(cells[col], errors="coerce") >= 0.4]
    elif confidence_filter == "Unknown only":
        cells = cells[pd.to_numeric(cells[col], errors="coerce").isna()]


if len(cells) == 0:
    st.warning("No cells after filters. Loosen the filters.")
    st.stop()

# Cyprus center
m = folium.Map(
    location=[34.9, 33.2],
    zoom_start=9,
    tiles="OpenStreetMap",
    control_scale=True,
)

proba_col = "culex_proba" if "Culex" in species_filter else (
    "aedes_proba" if "Aedes" in species_filter else "culex_proba"
)


# ============== CELLS — vectorized subset rendering ==============

# For large grids (37K cells), only pin high-probability cells. Show all via
# lighter rendering if grid is small.
N_CELLS = len(cells)
SUBSET_THRESHOLD = 5000

if N_CELLS > SUBSET_THRESHOLD:
    # Show only high-probability cells (>= 0.3) as pins
    pin_df = cells[pd.to_numeric(cells[proba_col], errors="coerce").fillna(0) >= 0.3].copy()
    st.caption(f"Large grid ({N_CELLS} cells) — showing {len(pin_df)} high-probability pins (>= 0.3). All cells still on the map layer.")
else:
    pin_df = cells
    st.caption(f"{N_CELLS} cells shown.")

# Vectorized: build popup + tooltip lists, then a single FeatureGroup
cells_layer = folium.FeatureGroup(name="Cells", show=True)

if len(pin_df) > 0:
    lats = pin_df["lat"].tolist()
    lons = pin_df["lon"].tolist()
    cell_ids = pin_df["cell_id"].astype(int).tolist()
    districts = pin_df.get("district", pd.Series(["?"] * len(pin_df))).tolist()
    culex_probas = pin_df.get("culex_proba", pd.Series([np.nan] * len(pin_df))).tolist()
    aedes_probas = pin_df.get("aedes_proba", pd.Series([np.nan] * len(pin_df))).tolist()
    confidence_tiers = pin_df.get("confidence_tier", pd.Series(["?"] * len(pin_df))).tolist()
    last_updated = pin_df.get("last_updated", pd.Series(["?"] * len(pin_df))).tolist()
    selected_probas = pin_df[proba_col].tolist()

    for lat, lon, cid, dist, cp, ap, ct, lu, sp in zip(
        lats, lons, cell_ids, districts, culex_probas, aedes_probas,
        confidence_tiers, last_updated, selected_probas,
    ):
        color = proba_to_color(sp, threshold=0.10)
        popup_html = f"""
        <b>Cell #{cid}</b><br>
        District: {dist}<br>
        Lat/Lon: {lat:.4f}, {lon:.4f}<br>
        <hr>
        <b>Culex proba:</b> {fmt_proba(cp)}<br>
        <b>Aedes proba:</b> {fmt_proba(ap)}<br>
        <b>Confidence:</b> {ct}<br>
        <b>Last updated:</b> {lu}
        """
        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"#{cid} | {dist} | {fmt_proba(sp)}",
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.6,
            weight=1,
        ).add_to(cells_layer)

cells_layer.add_to(m)


# ============== TRAPS ==============

if show_traps and len(traps_df) > 0:
    traps_layer = folium.FeatureGroup(name="Traps", show=True)
    for _, row in traps_df.iterrows():
        if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
            continue

        if pd.notna(row.get("last_check")):
            color = status_to_color(row["last_check"])
        else:
            color = state_to_color(row.get("state", "active"))

        popup_html = f"""
        <b>Trap {row['trap_id']}</b><br>
        Cell: #{int(row['cell_id'])} ({row.get('district', '?')})<br>
        Operator: {row.get('operator', '?')}<br>
        Method: {row.get('sampling_method', '?')}<br>
        State: {row.get('state', '?')}<br>
        <hr>
        <b>Last check:</b> {row.get('last_check', '—')}<br>
        <b>Check time:</b> {row.get('last_check_time', '—')}<br>
        <b>Check count:</b> {fmt_count(row.get('n_checks'))}
        """

        folium.Marker(
            location=[row["lat"], row["lon"]],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{row['trap_id']} ({row.get('last_check', row.get('state', '?'))})",
            icon=folium.Icon(
                color=hex_to_folium_name(color),
                icon_color="white",
                icon="bug", prefix="fa",
            ),
        ).add_to(traps_layer)
    traps_layer.add_to(m)


# ============== LAB MARKERS ==============

if show_labs and len(labs_df) > 0:
    labs_layer = folium.FeatureGroup(name="Lab Results", show=True)
    for _, row in labs_df.iterrows():
        cell = cells[cells["cell_id"] == row["cell_id"]]
        if len(cell) == 0:
            continue
        lat, lon = cell.iloc[0]["lat"], cell.iloc[0]["lon"]

        color = species_to_color(row.get("species", "Other"))
        species_short = row.get("species", "?")[:1]

        popup_html = f"""
        <b>Lab — {row['lab_id']}</b><br>
        Trap: {row['trap_id']}<br>
        Cell: #{int(row['cell_id'])}<br>
        <hr>
        <b>Species:</b> {row.get('species', '?')}<br>
        <b>Count:</b> {fmt_count(row.get('count'))}<br>
        <b>Lifecycle:</b> {row.get('specimen_lifecycle', '?')}<br>
        <b>Method:</b> {row.get('identification_method', '?')}<br>
        <b>Confidence:</b> {row.get('lab_confidence', '?')}<br>
        <b>Date:</b> {row.get('lab_date', '?')}<br>
        <b>Operator:</b> {row.get('lab_operator', '?')}
        """

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{row.get('species', '?')} x{fmt_count(row.get('count'))}",
            icon=folium.DivIcon(
                html=f'<div style="background:{color};color:white;border-radius:50%;width:24px;height:24px;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:12px;border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.3)">{species_short}</div>',
                icon_size=(24, 24),
                icon_anchor=(12, 12),
            ),
        ).add_to(labs_layer)
    labs_layer.add_to(m)


folium.LayerControl(collapsed=False).add_to(m)

map_data = st_folium(
    m,
    height=550,
    returned_objects=["last_clicked"],
    key="dashboard_map",
    use_container_width=True,
)

# v0.6.1: Show nearest cell info on map click (previously captured but ignored)
if map_data and map_data.get("last_clicked"):
    clicked = map_data["last_clicked"]
    clicked_lat = clicked.get("lat")
    clicked_lon = clicked.get("lng")
    if clicked_lat is not None and clicked_lon is not None and len(cells) > 0:
        # Scaled Euclidean (lon scaled by cos(lat) at Cyprus ~35°N)
        lat_rad = np.radians(clicked_lat)
        lon_scale = np.cos(lat_rad)
        cell_dist_km = (
            ((cells["lat"] - clicked_lat) ** 2
             + ((cells["lon"] - clicked_lon) * lon_scale) ** 2) ** 0.5
            * 111.0
        )
        nearest_idx = cell_dist_km.idxmin()
        nearest = cells.loc[nearest_idx]
        dist_km = float(cell_dist_km.loc[nearest_idx])
        st.info(
            f"Clicked: nearest cell **#{int(nearest['cell_id'])}** "
            f"({nearest.get('district', '?')}) — {dist_km:.2f} km away\n\n"
            f"Culex: {fmt_proba(nearest.get('culex_proba'))} • "
            f"Aedes: {fmt_proba(nearest.get('aedes_proba'))} • "
            f"Confidence: {nearest.get('confidence_tier', '?')}"
        )


# ============== WATCH LIST ==============

st.markdown("---")
st.subheader("Watch List")
st.caption("High-probability cells suggested by ML (no trap set up yet)")

watch_df = load_watch_list()
if len(watch_df) == 0:
    st.info("Watch list is empty. Run training from the Admin page.")
else:
    wspecies = st.radio(
        "Species",
        ["culex", "aedes"],
        horizontal=True,
        key="watch_species",
    )
    wdf = watch_df[watch_df["species"] == wspecies].copy()
    wdf = wdf.sort_values("proba", ascending=False).head(50)

    if len(wdf) == 0:
        st.info(f"No watch list entries for {wspecies}.")
    else:
        st.caption(f"{len(wdf)} cells on watch, by district:")
        district_summary = wdf.groupby("district").size().reset_index(name="count")
        dcols = st.columns(min(6, len(district_summary)))
        for i, (_, drow) in enumerate(district_summary.iterrows()):
            with dcols[i % len(dcols)]:
                st.metric(drow["district"], int(drow["count"]))

        display_df = wdf[["cell_id", "district", "proba", "threshold_used", "visited"]].copy()
        display_df["proba"] = display_df["proba"].apply(fmt_proba)
        display_df["threshold_used"] = display_df["threshold_used"].apply(fmt_proba)
        display_df.columns = ["Cell", "District", "Proba", "Threshold", "Visited"]

        st.dataframe(display_df, use_container_width=True, height=300)

        st.markdown("##### Set Up Traps (from Watch List)")
        st.caption("Start trap setup for the selected cells")

        if "prefill_cells" not in st.session_state:
            st.session_state.prefill_cells = []

        cell_options = wdf["cell_id"].astype(str) + " — " + wdf["district"] + " (proba=" + wdf["proba"].apply(fmt_proba) + ")"
        selected = st.multiselect(
            "Select cells to set up traps",
            options=cell_options.tolist(),
            key="watch_selected",
        )

        if st.button("Go to Data Entry for Selected Cells", type="primary"):
            if not selected:
                st.warning("Select cells first")
            else:
                selected_ids = [int(s.split(" — ")[0]) for s in selected]
                st.session_state.prefill_cells = selected_ids
                st.switch_page("pages/1_📥_Data_Entry.py")


# ============== SUMMARY ==============

st.markdown("---")
st.subheader("Summary")

scol1, scol2 = st.columns(2)

with scol1:
    st.markdown("**Lab species**")
    if len(labs_df) > 0:
        species_count = labs_df["species"].value_counts()
        for sp, cnt in species_count.items():
            color = species_to_color(sp)
            st.markdown(
                f'<span style="background:{color};color:white;padding:2px 10px;border-radius:12px;font-size:14px">{sp}</span> {int(cnt)} traps',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No lab results yet")

with scol2:
    st.markdown("**Trap status**")
    if len(traps_df) > 0:
        if "last_check" in traps_df.columns:
            status_count = traps_df["last_check"].value_counts(dropna=False)
            for st_name, cnt in status_count.items():
                if pd.isna(st_name):
                    label, color = "Not checked", "#bbdefb"
                else:
                    label, color = st_name, status_to_color(st_name)
                st.markdown(
                    f'<span style="background:{color};color:white;padding:2px 10px;border-radius:12px;font-size:14px">{label}</span> {int(cnt)} traps',
                    unsafe_allow_html=True,
                )
    else:
        st.caption("No traps set up yet")


st.markdown("---")
st.caption("""
Color scale: dark red (>=0.7) -> red (>=0.5) -> orange (>=0.3) -> yellow (>=0.10) -> light blue (low) -> gray (unknown)
""")
