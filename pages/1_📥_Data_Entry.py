"""1_📥_Data_Entry.py — Field data entry (3 tabs, mobile-first).

Tab 1: Sampling Initiation (Trap setup, auto Trap ID)
Tab 2: Trap Check (Field check, can be multiple)
Tab 3: Lab Result (Species identification)

Each tab provides:
- Location picker: GPS / Map / Manual
- Cell auto-detected (nearest cell, Cyprus-bounded)
- Form -> written to Sheets
- Optional photos (uploaded to Drive)
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_folium import st_folium
import folium

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import sheets_client
import drive_client
import mobile_styles
from gps_component import gps_button
from utils import require_auth


# ============== PAGE SETUP ==============

st.set_page_config(page_title="Data Entry", page_icon="📥", layout="wide")
mobile_styles.inject_mobile_css()
require_auth()


# ============== HELPERS ==============

# Cyprus bounding box (filter out cells outside Cyprus, e.g. Egypt lat ~26)
CYPRUS_LAT_MIN, CYPRUS_LAT_MAX = 34.5, 35.5
CYPRUS_LON_MIN, CYPRUS_LON_MAX = 32.5, 34.5


def filter_cyprus(cells_df: pd.DataFrame) -> pd.DataFrame:
    """Drop cells outside Cyprus bounding box."""
    if len(cells_df) == 0:
        return cells_df
    mask = (
        (cells_df["lat"] >= CYPRUS_LAT_MIN) & (cells_df["lat"] <= CYPRUS_LAT_MAX) &
        (cells_df["lon"] >= CYPRUS_LON_MIN) & (cells_df["lon"] <= CYPRUS_LON_MAX)
    )
    return cells_df[mask].copy()


def find_nearest_cell(cells_df: pd.DataFrame, lat: float, lon: float) -> tuple[int, float]:
    """Nearest cell (Euclidean — OK for Cyprus, ~300 km)."""
    if len(cells_df) == 0:
        return None, float("inf")
    cells_df = cells_df.copy()
    cells_df["dist"] = ((cells_df["lat"] - lat) ** 2 + (cells_df["lon"] - lon) ** 2) ** 0.5
    nearest = cells_df.loc[cells_df["dist"].idxmin()]
    return int(nearest["cell_id"]), float(nearest["dist"])


def get_cyprus_cells() -> pd.DataFrame:
    """Get cells, filter to Cyprus only."""
    if "cyprus_cells" not in st.session_state:
        try:
            all_cells = sheets_client.get_cells()
            st.session_state["cyprus_cells"] = filter_cyprus(all_cells)
        except Exception as e:
            st.error(f"Cells load error: {e}")
            st.session_state["cyprus_cells"] = pd.DataFrame()
    return st.session_state["cyprus_cells"]


def auto_generate_trap_id() -> str:
    """Generate next sequential TRP-XXX ID based on existing traps."""
    try:
        inits = sheets_client.get_sampling_initiations(active_only=False)
        if len(inits) == 0 or "trap_id" not in inits.columns:
            return "TRP-001"
        # Extract numeric part from existing IDs
        existing_nums = []
        for tid in inits["trap_id"].astype(str):
            t = str(tid).strip().upper()
            if t.startswith("TRP-"):
                try:
                    existing_nums.append(int(t[4:]))
                except ValueError:
                    pass
        next_num = max(existing_nums, default=0) + 1
        return f"TRP-{next_num:03d}"
    except Exception:
        return "TRP-001"


def render_location_picker(label: str, key_prefix: str) -> tuple[float, float, int] | None:
    """Location picker: GPS / Map / Manual.

    Returns: (lat, lon, cell_id) or None.
    """
    st.markdown(f"### {label}")

    method = st.radio(
        "Method",
        ["Map", "Manual", "GPS"],
        horizontal=True,
        key=f"{key_prefix}_method",
    )

    coords = None

    if method == "GPS":
        result = gps_button(label="Get my location", key=f"{key_prefix}_gps")
        if result:
            lat, lon = result
            st.success(f"Location: {lat:.5f}, {lon:.5f}")
            coords = (lat, lon)
        else:
            st.info("Click the button to get your location. Browser will ask for permission.")

    elif method == "Map":
        cells = get_cyprus_cells()
        if len(cells) == 0:
            st.warning("No Cyprus cells available. Use Manual input.")
            return None

        # Cyprus center, fit to bounds
        m = folium.Map(
            location=[34.9, 33.2],
            zoom_start=9,
            tiles="OpenStreetMap",
        )

        for _, row in cells.iterrows():
            color = "red" if pd.notna(row.get("culex_proba")) and row["culex_proba"] >= 0.5 else "gray"
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=4,
                popup=f"cell_id={row['cell_id']}<br>lat={row['lat']}<br>lon={row['lon']}",
                color=color,
                fill=True,
                fill_opacity=0.4,
            ).add_to(m)

        st.caption("Click on the map to set the location.")
        map_data = st_folium(
            m,
            height=400,
            returned_objects=["last_clicked"],
            key=f"{key_prefix}_map",
            use_container_width=True,
        )

        if map_data and map_data.get("last_clicked"):
            lat = map_data["last_clicked"]["lat"]
            lon = map_data["last_clicked"]["lng"]
            st.success(f"Selected: {lat:.5f}, {lon:.5f}")
            coords = (lat, lon)
        else:
            st.caption("Click the map to select a location.")

    else:  # Manual
        col1, col2 = st.columns(2)
        with col1:
            lat = st.number_input("Lat", value=34.9, format="%.5f", key=f"{key_prefix}_lat")
        with col2:
            lon = st.number_input("Lon", value=33.2, format="%.5f", key=f"{key_prefix}_lon")
        coords = (lat, lon)

    if coords:
        lat, lon = coords
        # Sanity check: Cyprus
        if not (CYPRUS_LAT_MIN <= lat <= CYPRUS_LAT_MAX and CYPRUS_LON_MIN <= lon <= CYPRUS_LON_MAX):
            st.warning(f"Location is outside Cyprus bounds ({lat:.2f}, {lon:.2f}). Check the coordinates.")
            return None

        try:
            cells = get_cyprus_cells()
            cell_id, dist = find_nearest_cell(cells, lat, lon)
            if cell_id is not None:
                dist_km = dist * 111
                if dist_km < 5:
                    st.success(f"Cell **#{cell_id}** (distance: {dist_km:.2f} km)")
                else:
                    st.warning(f"Nearest cell #{cell_id}, but {dist_km:.1f} km away (over 5 km)")
                return (lat, lon, cell_id)
        except Exception as e:
            st.error(f"Cell lookup error: {e}")

    return None


def photo_uploader(key: str, label: str = "Photo (optional)") -> list:
    """Upload photos, return file list."""
    files = st.file_uploader(
        label,
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key=key,
        help="Opens the camera on mobile",
    )
    if files:
        st.caption(f"{len(files)} photo(s) selected")
        cols = st.columns(min(3, len(files)))
        for i, f in enumerate(files):
            with cols[i % 3]:
                st.image(f, caption=f.name, use_container_width=True)
    return files or []


# ============== TAB 1: SAMPLING INITIATION ==============

def tab_sampling_initiation():
    st.header("Sampling Initiation")
    st.caption("Trap setup — for the field team in the field")

    # Auto-generate next Trap ID
    if "auto_trap_id" not in st.session_state:
        st.session_state["auto_trap_id"] = auto_generate_trap_id()

    col1, col2 = st.columns([3, 1])
    with col1:
        trap_id = st.text_input(
            "Trap ID (auto-generated, editable)",
            value=st.session_state["auto_trap_id"],
            help="Auto-increments from the last trap. Edit if you need a custom ID.",
        ).strip().upper()
    with col2:
        st.write("")
        st.write("")
        if st.button("Regenerate", use_container_width=True, help="Generate next ID"):
            st.session_state["auto_trap_id"] = auto_generate_trap_id()
            st.rerun()

    if not trap_id:
        st.info("Trap ID is required")
        st.stop()

    # Already exists?
    try:
        existing = sheets_client.get_sampling_initiations(active_only=False)
        if trap_id in existing.get("trap_id", []).values:
            st.warning(f"{trap_id} is already registered. Click Regenerate or change the ID.")
            # Don't stop, let user decide
    except Exception:
        pass

    st.markdown("---")

    location = render_location_picker("Select Location", key_prefix="init_loc")
    if not location:
        st.stop()
    lat, lon, cell_id = location

    st.markdown("---")

    with st.form("sampling_form", clear_on_submit=True):
        st.subheader("Details")

        col1, col2 = st.columns(2)
        with col1:
            operator = st.selectbox(
                "Operator *",
                ["Ceyda", "Marlen", "Yesim", "Gregoris", "Mustafa", "Costas", "Other"],
            )
            method = st.selectbox(
                "Sampling Method *",
                ["Ovitraps", "Larvae Collection", "BG Sentinel Trap", "EVS Trap", "Human Land Catching"],
            )

        with col2:
            start_date = st.date_input("Sampling Start *", value=datetime.now().date())
            start_time = st.time_input("Time", value=datetime.now().time())

        site_desc = st.text_area(
            "Site Description *",
            placeholder="Rural, 200 m from shore, stagnant water...",
        )
        comments = st.text_area("Comments (optional)", placeholder="Additional notes...")

        st.markdown("---")
        photos = photo_uploader("init_photos", "Photos")

        submitted = st.form_submit_button("Set Up Trap", type="primary", use_container_width=True)

    if submitted:
        if not site_desc.strip():
            st.error("Site description is required")
            st.stop()

        with st.spinner("Saving..."):
            try:
                photo_urls = []
                if photos:
                    photo_urls = drive_client.upload_photos(photos, "sampling", trap_id)

                init_id = f"INIT-{trap_id}"
                start_dt = datetime.combine(start_date, start_time)

                row = {
                    "init_id": init_id,
                    "trap_id": trap_id,
                    "cell_id": cell_id,
                    "sampling_start_time": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "operator": operator,
                    "sampling_method": method,
                    "site_description": site_desc,
                    "comments": comments,
                    "photo_urls": drive_client.urls_to_string(photo_urls),
                    "state": "active",
                }
                sheets_client.append_row("sampling_initiation", row)

                # Increment session trap_id for next entry
                st.session_state["auto_trap_id"] = auto_generate_trap_id()

                st.success(f"{trap_id} set up (cell #{cell_id})")
                st.balloons()
                st.session_state.pop("cyprus_cells", None)
                st.rerun()
            except Exception as e:
                st.error(f"Save error: {e}")


# ============== TAB 2: TRAP CHECK ==============

def tab_trap_check():
    st.header("Trap Check")
    st.caption("Field check — multiple checks per trap are allowed")

    try:
        inits = sheets_client.get_sampling_initiations(active_only=True)
    except Exception as e:
        st.error(f"Data load error: {e}")
        return

    if len(inits) == 0:
        st.info("No active traps. Set up a trap first via Sampling Initiation.")
        return

    trap_options = inits[["trap_id", "cell_id", "operator"]].fillna("").astype(str)
    trap_options["label"] = trap_options.apply(
        lambda r: f"{r['trap_id']} (cell #{r['cell_id']}, {r['operator']})", axis=1
    )

    selected_label = st.selectbox("Select trap *", trap_options["label"].tolist())
    if not selected_label:
        return

    selected = trap_options[trap_options["label"] == selected_label].iloc[0]
    trap_id = selected["trap_id"]
    cell_id = int(selected["cell_id"])

    try:
        checks = sheets_client.get_trap_checks(trap_id)
        n_checks = len(checks)
    except Exception:
        n_checks = 0

    st.caption(f"Existing checks for this trap: {n_checks}")

    if n_checks > 0:
        last_status = checks.iloc[-1].get("trap_status", "?")
        st.caption(f"Last check: **{last_status}** ({checks.iloc[-1].get('check_datetime', '?')})")

    st.markdown("---")

    with st.form("check_form", clear_on_submit=True):
        st.subheader(f"Check #{n_checks + 1} — {trap_id}")

        col1, col2 = st.columns(2)
        with col1:
            check_date = st.date_input("Date *", value=datetime.now().date())
        with col2:
            check_time = st.time_input("Time *", value=datetime.now().time())

        status = st.selectbox(
            "Trap Status *",
            ["Trap valid", "Trap Missing", "Trap Disturbed", "Battery out", "Other"],
        )

        comments = st.text_area("Comments", placeholder="Observation notes...")

        st.markdown("---")
        photos = photo_uploader("check_photos", "Photos")

        submitted = st.form_submit_button("Save Check", type="primary", use_container_width=True)

    if submitted:
        with st.spinner("Saving..."):
            try:
                photo_urls = []
                if photos:
                    photo_urls = drive_client.upload_photos(photos, "checks", trap_id)

                check_dt = datetime.combine(check_date, check_time)
                check_id = f"CHK-{trap_id}-{n_checks + 1}"
                finish_id = f"{trap_id}+{check_dt.strftime('%Y%m%d%H%M')}"

                row = {
                    "check_id": check_id,
                    "trap_id": trap_id,
                    "check_datetime": check_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "trap_status": status,
                    "comments": comments,
                    "image_urls": drive_client.urls_to_string(photo_urls),
                    "sampling_finish_id": finish_id,
                }
                sheets_client.append_row("trap_checks", row)

                if status == "Trap Missing":
                    sheets_client.update_cell("sampling_initiation", 0, "state", "")

                st.success(f"Check #{n_checks + 1} saved: {status}")
                st.rerun()
            except Exception as e:
                st.error(f"Save error: {e}")


# ============== TAB 3: LAB RESULT ==============

def tab_lab_result():
    st.header("Lab Result")
    st.caption("Species identification — only traps with last check 'Trap valid'")

    try:
        checks_df = sheets_client.get_trap_checks()
        inits_df = sheets_client.get_sampling_initiations(active_only=False)
        labs_df = sheets_client.get_lab_results()
    except Exception as e:
        st.error(f"Data load error: {e}")
        return

    if len(checks_df) == 0 or len(inits_df) == 0:
        st.info("Set up a trap and perform a check first.")
        return

    checked_traps = checks_df["trap_id"].unique()
    lab_done_traps = labs_df["trap_id"].unique() if len(labs_df) > 0 else []
    pending = [t for t in checked_traps if t not in lab_done_traps]

    if not pending:
        st.success("All traps have lab results entered.")
        return

    valid_pending = []
    for trap_id in pending:
        trap_checks = checks_df[checks_df["trap_id"] == trap_id].sort_values("check_datetime")
        if len(trap_checks) > 0:
            last_status = trap_checks.iloc[-1].get("trap_status", "")
            if last_status == "Trap valid":
                valid_pending.append(trap_id)

    if not valid_pending:
        st.warning("Lab entry requires the last check to be 'Trap valid'.")
        st.caption("No eligible traps yet.")
        return

    st.caption(f"{len(valid_pending)} trap(s) waiting for lab entry")

    selected_trap = st.selectbox("Select trap *", valid_pending)
    if not selected_trap:
        return

    init_row = inits_df[inits_df["trap_id"] == selected_trap]
    if len(init_row) == 0:
        st.error("Trap initiation not found")
        return
    cell_id = int(init_row.iloc[0]["cell_id"])

    st.markdown("---")

    with st.form("lab_form", clear_on_submit=True):
        st.subheader(f"Lab — {selected_trap} (cell #{cell_id})")

        col1, col2 = st.columns(2)
        with col1:
            lab_date = st.date_input("Analysis Date *", value=datetime.now().date())
        with col2:
            lab_operator = st.selectbox(
                "Lab Operator *",
                ["Gregoris", "Ceyda", "Operator1", "Operator2", "Other"],
            )

        col3, col4 = st.columns(2)
        with col3:
            lifecycle = st.selectbox(
                "Specimen Life Cycle *",
                ["Egg", "Larva", "Adult"],
            )
        with col4:
            method = st.selectbox(
                "Identification Method *",
                ["Morphological", "Molecular"],
            )

        species = st.selectbox(
            "Species *",
            ["Culex", "Aedes", "Mixed", "Other", "Negative"],
        )

        count = st.number_input("Specimen Count *", min_value=0, value=1)

        comments = st.text_area("Comments", placeholder="3 male, 9 female...")

        if lifecycle == "Adult" and method == "Molecular":
            confidence = "high"
        elif lifecycle == "Larva" and method == "Morphological":
            confidence = "medium"
        elif lifecycle == "Egg" and method == "Morphological":
            confidence = "low"
        else:
            confidence = "medium"
        st.caption(f"Auto-calculated confidence: **{confidence}**")

        st.markdown("---")
        photos = photo_uploader("lab_photos", "Specimen photo")

        submitted = st.form_submit_button("Save Lab Result", type="primary", use_container_width=True)

    if submitted:
        with st.spinner("Saving..."):
            try:
                photo_urls = []
                if photos:
                    photo_urls = drive_client.upload_photos(photos, "lab", selected_trap)

                n_labs = len(labs_df[labs_df["trap_id"] == selected_trap]) if len(labs_df) > 0 else 0

                lab_id = f"LAB-{selected_trap}-{n_labs + 1}"
                lab_id_field = f"{selected_trap}+lab{n_labs + 1}"

                row = {
                    "lab_id": lab_id,
                    "trap_id": selected_trap,
                    "sampling_lab_id": lab_id_field,
                    "cell_id": cell_id,
                    "lab_date": lab_date.strftime("%Y-%m-%d"),
                    "lab_operator": lab_operator,
                    "specimen_lifecycle": lifecycle,
                    "identification_method": method,
                    "species": species,
                    "count": int(count),
                    "lab_confidence": confidence,
                    "comments": comments,
                    "image_urls": drive_client.urls_to_string(photo_urls),
                }
                sheets_client.append_row("lab_results", row)

                st.success(f"Lab result saved: {species} ({count} specimens, confidence={confidence})")
                st.balloons()
                st.rerun()
            except Exception as e:
                st.error(f"Save error: {e}")


# ============== MAIN ==============

def main():
    st.title("Data Entry")

    tab1, tab2, tab3 = st.tabs([
        "Sampling Init",
        "Trap Check",
        "Lab Result",
    ])

    with tab1:
        tab_sampling_initiation()
    with tab2:
        tab_trap_check()
    with tab3:
        tab_lab_result()


if __name__ == "__main__":
    main()
