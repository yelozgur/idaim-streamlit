"""1_📥_Veri_Girişi.py — Saha ekibinin veri girişi (3 tab, mobile-first).

Tab 1: Sampling Initiation (Trap kurulumu)
Tab 2: Trap Check (Saha kontrolü, birden fazla olabilir)
Tab 3: Lab Result (Tür tespiti)

Her tab'da:
- Konum seçimi: GPS / Harita / Manuel
- Hücre otomatik bulunur (en yakın 5km grid)
- Form → Sheets'e yazılır
- Fotoğraf opsiyonel (Drive'a yüklenir)
"""
import streamlit as st
import pandas as pd
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import sheets_client
import drive_client
import mobile_styles
import utils
from gps_component import gps_button, get_gps_from_query, clear_gps_query


# ============== PAGE SETUP ==============

st.set_page_config(page_title="Veri Girişi", page_icon="📥", layout="wide")
mobile_styles.inject_mobile_css()

# Auth check
if not st.session_state.get("authenticated", False):
    st.warning("🔐 Giriş yapın")
    st.stop()


# ============== HELPERS ==============

def find_nearest_cell(cells_df: pd.DataFrame, lat: float, lon: float) -> tuple[int, float]:
    """En yakın hücreyi bul (haversine mesafesi, ~5km grid)."""
    if len(cells_df) == 0:
        return None, float("inf")
    # Basit euclidean (küçük alanlar için yeterli, Cyprus ~300km)
    cells_df = cells_df.copy()
    cells_df["dist"] = ((cells_df["lat"] - lat) ** 2 + (cells_df["lon"] - lon) ** 2) ** 0.5
    nearest = cells_df.loc[cells_df["dist"].idxmin()]
    return int(nearest["cell_id"]), float(nearest["dist"])


def render_location_picker(label: str, key_prefix: str) -> tuple[float, float, int] | None:
    """Konum seçici: 3 yöntem (GPS / Harita / Manuel).

    Akış:
    1. Kullanıcı yöntem seçer
    2. Konum belirlenir
    3. En yakın hücre otomatik bulunur + mesafe gösterilir
    4. (Opsiyonel) Yakındaki trap/lab'lar haritada gösterilir

    Returns:
        (lat, lon, cell_id) veya None
    """
    import plotly.graph_objects as go
    st.markdown(f"### 📍 {label}")

    # Yöntem seçimi (segmented, daha kompakt)
    method = st.segmented_control(
        "Yöntem",
        ["📡 GPS", "🗺️ Harita", "⌨️ Manuel"],
        selection_mode="single",
        default="📡 GPS",
        key=f"{key_prefix}_method",
    ) or "📡 GPS"

    coords = None

    # ============ YÖNTEM 1: GPS ============
    if method == "📡 GPS":
        # HTML5 Geolocation butonu
        gps_button(label="📍 Konumumu Al", key=f"{key_prefix}_gps")

        # Query params'ten koordinat oku
        gps_coords = get_gps_from_query()
        if gps_coords:
            lat, lon = gps_coords
            coords = (lat, lon)
            clear_gps_query()
        else:
            st.caption("👆 Butona tıklayıp konum izni verin")

    # ============ YÖNTEM 2: HARİTADAN TIKLA ============
    elif method == "🗺️ Harita":
        try:
            cells = utils.load_static_cells()
        except Exception as e:
            st.error(f"Hücreler yüklenemedi: {e}")
            return None

        if len(cells) > 0:
            # 37K hücreyi Plotly ile göster, tıklama seçim için
            cells_view = cells.copy()
            cells_view["cv_color"] = cells_view["culex_proba"].apply(
                lambda p: "red" if pd.notna(p) and p >= 0.5 else "lightblue"
            )
            cells_view["hover_text"] = cells_view.apply(
                lambda r: (
                    f"Hücre #{utils.safe_cell_id(r['cell_id'])}<br>"
                    f"{r.get('district', '?')}<br>"
                    f"👆 tıklayarak seç"
                ),
                axis=1,
            )
            fig = go.Figure()
            fig.add_trace(go.Scattermap(
                lat=cells_view["lat"], lon=cells_view["lon"],
                mode="markers",
                marker=dict(size=6, color=cells_view["cv_color"].tolist(), opacity=0.5),
                text=cells_view["hover_text"], hoverinfo="text",
            ))
            fig.update_layout(
                map=dict(style="open-street-map", center=dict(lat=34.9, lon=33.2), zoom=9),
                height=400, margin=dict(t=0, b=0, l=0, r=0), showlegend=False,
            )
            event = st.plotly_chart(
                fig, use_container_width=True,
                config={"scrollZoom": True, "displayModeBar": False, "displaylogo": False},
                on_select="rerun", key=f"{key_prefix}_plotly_map",
            )
            if event and event.selection and len(event.selection.points) > 0:
                point = event.selection.points[0]
                lat = point.get("lat")
                lon = point.get("lon")
                if lat is not None and lon is not None:
                    coords = (lat, lon)

    # ============ YÖNTEM 3: MANUEL ============
    else:  # Manuel
        col1, col2 = st.columns(2)
        with col1:
            lat = st.number_input("Lat", value=34.9, format="%.5f", key=f"{key_prefix}_lat")
        with col2:
            lon = st.number_input("Lon", value=33.2, format="%.5f", key=f"{key_prefix}_lon")
        coords = (lat, lon)

    # ============ HÜCRE OTOMATİK BUL + HARİTA GÖSTER ============
    if coords:
        lat, lon = coords
        try:
            cells = utils.load_static_cells()
            cell_id, dist = find_nearest_cell(cells, lat, lon)
            if cell_id is not None:
                dist_km = dist * 111
                # Hücre bilgisi kompakt
                if dist_km < 5:
                    st.success(f"✅ Hücre **#{cell_id}** • {dist_km:.2f} km mesafe")
                else:
                    st.warning(f"⚠️ En yakın: #{cell_id} ({dist_km:.1f} km — 5km dışı)")

                # Seçili hücre + yakındaki trap/lab haritası (küçük preview)
                with st.expander("🗺️ Haritada Gör", expanded=False):
                    self_cell = cells[cells["cell_id"] == cell_id].iloc[0]
                    # Yakındaki trap'ler
                    inits = sheets_client.get_sampling_initiations(active_only=False)
                    nearby_traps = []
                    if len(inits) > 0 and "cell_id" in inits.columns:
                        nearby_traps = inits[inits["cell_id"] == cell_id]
                    # Yakındaki lab'lar
                    labs = sheets_client.get_lab_results()
                    nearby_labs = []
                    if len(labs) > 0 and "cell_id" in labs.columns:
                        nearby_labs = labs[labs["cell_id"] == cell_id]

                    fig2 = go.Figure()
                    # Hücre merkezi
                    fig2.add_trace(go.Scattermap(
                        lat=[self_cell["lat"]], lon=[self_cell["lon"]],
                        mode="markers",
                        marker=dict(size=25, color="red", symbol="star",
                                   line=dict(color="white", width=2)),
                        name=f"📍 Seçili: #{cell_id}",
                        text=f"Seçili hücre #{cell_id}",
                        hoverinfo="text",
                    ))
                    # Yakın trap'ler
                    if len(nearby_traps) > 0:
                        fig2.add_trace(go.Scattermap(
                            lat=[self_cell["lat"]] * len(nearby_traps),
                            lon=[self_cell["lon"]] * len(nearby_traps),
                            mode="markers",
                            marker=dict(size=18, color="orange", symbol="circle"),
                            name=f"🪤 Trap ({len(nearby_traps)})",
                            text=nearby_traps["trap_id"].tolist(),
                            hoverinfo="text",
                        ))
                    # Yakın lab'lar
                    if len(nearby_labs) > 0:
                        fig2.add_trace(go.Scattermap(
                            lat=[self_cell["lat"]] * len(nearby_labs),
                            lon=[self_cell["lon"]] * len(nearby_labs),
                            mode="markers",
                            marker=dict(size=20, color="purple", symbol="diamond"),
                            name=f"🧪 Lab ({len(nearby_labs)})",
                            text=[f"{r['species']} ×{r.get('count', '?')}" for _, r in nearby_labs.iterrows()],
                            hoverinfo="text",
                        ))
                    fig2.update_layout(
                        map=dict(style="open-street-map",
                                center=dict(lat=self_cell["lat"], lon=self_cell["lon"]),
                                zoom=15),
                        height=350, margin=dict(t=0, b=0, l=0, r=0),
                        showlegend=True,
                    )
                    st.plotly_chart(fig2, use_container_width=True,
                                   config={"displayModeBar": False})

                return (lat, lon, cell_id)
        except Exception as e:
            st.error(f"Hücre bulunamadı: {e}")

    return None


def photo_uploader(key: str, label: str = "📷 Fotoğraf (opsiyonel)") -> list[str]:
    """Fotoğraf yükle, Drive'a gönder, URL listesi döner."""
    files = st.file_uploader(
        label,
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key=key,
        help="Mobilde kamerayı açar",
    )
    if files:
        st.caption(f"📸 {len(files)} fotoğraf seçildi")
        cols = st.columns(min(3, len(files)))
        for i, f in enumerate(files):
            with cols[i % 3]:
                st.image(f, caption=f.name, use_container_width=True)
    return files or []


# ============== TAB 1: SAMPLING INITIATION ==============

def tab_sampling_initiation():
    st.header("🪤 Sampling Initiation")
    st.caption("Trap kurulumu — saha ekibi sahadayken")

    # Önce hücre seçtir, sonra Trap ID otomatik üret
    # Adım 1: Konum seç (hücre belirle)
    location = render_location_picker("Konum Seç (önce buraya tıkla)", key_prefix="init_loc")
    if not location:
        st.info("👆 Önce konum seç: GPS, harita veya manuel")
        st.stop()
    lat, lon, cell_id = location

    # Adım 2: Trap ID otomatik üret (cell_id + tarih + aynı hücredeki sequence)
    today_str = datetime.now().strftime("%y%m%d")  # 260611
    # Aynı hücrede bugün kaç trap var?
    try:
        existing = sheets_client.get_sampling_initiations(active_only=False)
        same_cell_today = 0
        if len(existing) > 0 and "cell_id" in existing.columns and "trap_id" in existing.columns:
            same_cell = existing[existing["cell_id"] == cell_id]
            if len(same_cell) > 0:
                # Bugünün trap'larını say
                for tid in same_cell["trap_id"]:
                    if today_str in str(tid):
                        same_cell_today += 1
        sequence = same_cell_today + 1
    except Exception:
        sequence = 1

    auto_trap_id = f"TRP-{cell_id}-{today_str}-{sequence:02d}"
    st.success(f"🪤 Otomatik Trap ID: **{auto_trap_id}** (cell {cell_id}, bugün #{sequence})")

    # Manuel override (nadir durumlar için)
    with st.expander("⚙️ Manuel Trap ID (opsiyonel)"):
        trap_id_manual = st.text_input(
            "Trap ID (boş bırakırsan otomatik kullanılır)",
            value=auto_trap_id,
        ).strip().upper()
    trap_id = trap_id_manual or auto_trap_id

    # Aynı trap_id zaten var mı?
    try:
        existing = sheets_client.get_sampling_initiations(active_only=False)
        if len(existing) > 0 and "trap_id" in existing.columns and trap_id in existing.get("trap_id", []).values:
            st.error(f"❌ {trap_id} zaten kayıtlı. Farklı bir ID girin.")
            st.stop()
    except Exception:
        pass

    st.markdown("---")

    # Form alanları
    with st.form("sampling_form", clear_on_submit=True):
        st.subheader("📋 Detaylar")

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
            placeholder="Rural, sahile 200m, durgun su...",
        )
        comments = st.text_area("Comments (opsiyonel)", placeholder="Ek notlar...")

        st.markdown("---")
        photos = photo_uploader("init_photos", "📷 Fotoğraflar")

        submitted = st.form_submit_button("🪤 Trap Kur", type="primary", use_container_width=True)

    if submitted:
        if not site_desc.strip():
            st.error("❌ Site description gerekli")
            st.stop()

        with st.spinner("Kaydediliyor..."):
            try:
                # Fotoğrafları yükle (varsa)
                photo_urls = []
                if photos:
                    photo_urls = drive_client.upload_photos(photos, "sampling", trap_id)

                # init_id otomatik
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

                st.success(f"✅ {trap_id} kuruldu (hücre #{cell_id})")
                st.balloons()
                st.session_state.pop("cells_cache", None)
                # Form temizle
                st.rerun()
            except Exception as e:
                st.error(f"❌ Kayıt hatası: {e}")


# ============== TAB 2: TRAP CHECK ==============

def tab_trap_check():
    st.header("🔍 Trap Check")
    st.caption("Saha kontrolü — trap valid mi? Birden fazla check olabilir")

    try:
        inits = sheets_client.get_sampling_initiations(active_only=True)
    except Exception as e:
        st.error(f"Veri yüklenemedi: {e}")
        return

    if len(inits) == 0:
        st.info("Aktif trap yok. Önce Sampling Initiation yapın.")
        return

    # Trap seç
    trap_options = inits[["trap_id", "cell_id", "operator"]].fillna("").astype(str)
    trap_options["label"] = trap_options.apply(
        lambda r: f"{r['trap_id']} (cell #{r['cell_id']}, {r['operator']})", axis=1
    )

    selected_label = st.selectbox(
        "Trap seç *",
        trap_options["label"].tolist(),
    )
    if not selected_label:
        return

    selected = trap_options[trap_options["label"] == selected_label].iloc[0]
    trap_id = selected["trap_id"]
    cell_id = int(selected["cell_id"])

    # Mevcut check sayısı
    try:
        checks = sheets_client.get_trap_checks(trap_id)
        n_checks = len(checks)
    except Exception:
        n_checks = 0

    st.caption(f"📋 Bu trap için mevcut check sayısı: {n_checks}")

    # Son check durumu
    if n_checks > 0:
        last_status = checks.iloc[-1].get("trap_status", "?")
        st.caption(f"🔄 Son check: **{last_status}** ({checks.iloc[-1].get('check_datetime', '?')})")

    st.markdown("---")

    with st.form("check_form", clear_on_submit=True):
        st.subheader(f"📍 Check #{n_checks + 1} — {trap_id}")

        col1, col2 = st.columns(2)
        with col1:
            check_date = st.date_input("Tarih *", value=datetime.now().date())
        with col2:
            check_time = st.time_input("Saat *", value=datetime.now().time())

        status = st.selectbox(
            "Trap Status *",
            ["Trap valid", "Trap Missing", "Trap Disturbed", "Battery out", "Other"],
        )

        comments = st.text_area("Comments", placeholder="Gözlem notları...")

        st.markdown("---")
        photos = photo_uploader("check_photos", "📷 Fotoğraflar")

        submitted = st.form_submit_button("💾 Check Kaydet", type="primary", use_container_width=True)

    if submitted:
        with st.spinner("Kaydediliyor..."):
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

                # Trap state güncelle (missing ise inactive yap)
                if status == "Trap Missing":
                    sheets_client.update_cell("sampling_initiation", 0, "state", "")  # placeholder
                    # Gerçek update için init sheet'inde trap_id'yi bulup state'i değiştir

                st.success(f"✅ Check #{n_checks + 1} kaydedildi: {status}")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Kayıt hatası: {e}")


# ============== TAB 3: LAB RESULT ==============

def tab_lab_result():
    st.header("🧪 Lab Result")
    st.caption("Tür tespiti — sadece son check'i 'Trap valid' olan trap'ler")

    try:
        checks_df = sheets_client.get_trap_checks()
        inits_df = sheets_client.get_sampling_initiations(active_only=False)
        labs_df = sheets_client.get_lab_results()
    except Exception as e:
        st.error(f"Veri yüklenemedi: {e}")
        return

    if len(checks_df) == 0 or len(inits_df) == 0:
        st.info("Önce trap kurulumu ve check yapın.")
        return

    # Lab girişi yapılmamış trap'leri bul
    checked_traps = checks_df["trap_id"].unique()
    lab_done_traps = labs_df["trap_id"].unique() if len(labs_df) > 0 else []
    pending = [t for t in checked_traps if t not in lab_done_traps]

    if not pending:
        st.success("🎉 Tüm trap'lerin lab sonucu girilmiş!")
        return

    # Son check'i Valid olanları filtrele
    valid_pending = []
    for trap_id in pending:
        trap_checks = checks_df[checks_df["trap_id"] == trap_id].sort_values("check_datetime")
        if len(trap_checks) > 0:
            last_status = trap_checks.iloc[-1].get("trap_status", "")
            if last_status == "Trap valid":
                valid_pending.append(trap_id)

    if not valid_pending:
        st.warning("⚠️ Lab girişi için son check 'Trap valid' olmalı.")
        st.caption("Henüz uygun trap yok.")
        return

    st.caption(f"📋 {len(valid_pending)} trap lab girişi bekliyor")

    # Trap seç
    selected_trap = st.selectbox("Trap seç *", valid_pending)

    if not selected_trap:
        return

    # Cell_id bul
    init_row = inits_df[inits_df["trap_id"] == selected_trap]
    if len(init_row) == 0:
        st.error("Trap initiation bulunamadı")
        return
    cell_id = int(init_row.iloc[0]["cell_id"])

    st.markdown("---")

    with st.form("lab_form", clear_on_submit=True):
        st.subheader(f"🧪 Lab — {selected_trap} (cell #{cell_id})")

        col1, col2 = st.columns(2)
        with col1:
            lab_date = st.date_input("Analiz Tarihi *", value=datetime.now().date())
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

        count = st.number_input("Birey Sayısı *", min_value=0, value=1)

        comments = st.text_area("Comments", placeholder="3 erkek, 9 dişi...")

        # lab_confidence otomatik hesaplanır (readonly gösterim)
        if lifecycle == "Adult" and method == "Molecular":
            confidence = "high"
        elif lifecycle == "Larva" and method == "Morphological":
            confidence = "medium"
        elif lifecycle == "Egg" and method == "Morphological":
            confidence = "low"
        else:
            confidence = "medium"
        st.caption(f"🔬 Auto-calculated confidence: **{confidence}**")

        st.markdown("---")
        photos = photo_uploader("lab_photos", "📷 Specimen fotoğrafı")

        submitted = st.form_submit_button("💾 Lab Kaydet", type="primary", use_container_width=True)

    if submitted:
        with st.spinner("Kaydediliyor..."):
            try:
                photo_urls = []
                if photos:
                    photo_urls = drive_client.upload_photos(photos, "lab", selected_trap)

                # Kaçıncı lab entry
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

                st.success(f"✅ Lab sonucu kaydedildi: {species} ({count} birey, confidence={confidence})")
                st.balloons()
                st.rerun()
            except Exception as e:
                st.error(f"❌ Kayıt hatası: {e}")


# ============== MAIN ==============

def main():
    st.title("📥 Veri Girişi")

    tab1, tab2, tab3 = st.tabs([
        "🪤 Sampling Init",
        "🔍 Trap Check",
        "🧪 Lab Result",
    ])

    with tab1:
        tab_sampling_initiation()
    with tab2:
        tab_trap_check()
    with tab3:
        tab_lab_result()


if __name__ == "__main__":
    main()
