"""3_🤖_ML_Retrain.py — Per-species MiniRocket training UI.

Kullanıcı:
1. Tür seçer (Culex / Aedes)
2. Threshold stratejisi (per-district / global / custom)
3. Retrain butonu → Sheets'ten data → train → predict_all → watch_list yaz
4. Sonuçları görür (LOOCV metrikleri, per-district threshold'lar, watch list)
"""
import streamlit as st
import pandas as pd
import json
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import mobile_styles
import utils
from utils import (
    load_merged_cells as load_cells,
    load_labeled_cells, load_watch_list, clear_all_caches,
    fmt_proba, fmt_count, compute_label_counts,
)
import ml_pipeline
import sheets_client


# ============== PAGE SETUP ==============

st.set_page_config(page_title="ML Retrain", page_icon="🤖", layout="wide")
mobile_styles.inject_mobile_css()
utils.require_auth()


# ============== HEADER ==============

st.title("🤖 ML Retrain")
st.caption("Per-species MiniRocket eğitimi + 642 hücre predict + per-district threshold")

# ============== VERİ DURUMU ==============

st.subheader("📊 Veri Durumu")
label_counts = compute_label_counts()
watch_df = load_watch_list()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Toplam Lab", label_counts["total"])
col2.metric("Culex pozitif", label_counts["culex_pos"])
col3.metric("Culex negatif", label_counts["culex_neg"])
col4.metric("Aedes pozitif", label_counts["aedes_pos"])

st.caption(f"ℹ️ Aedes: skip (0 örnek) | Culex: {label_counts['culex_pos']} pozitif ile eğitilebilir")
st.markdown("---")


# ============== TÜR SEÇİMİ ==============

st.subheader("1️⃣ Tür Seç")
species_choice = st.radio(
    "Hangi tür için eğit?",
    ["culex", "aedes"],
    horizontal=True,
    format_func=lambda s: s.capitalize(),
)

# Veri yeterli mi?
n_pos = label_counts[f"{species_choice}_pos"]
min_req = config.MIN_SAMPLES[species_choice]
if n_pos < min_req:
    st.warning(f"⚠️ {species_choice.capitalize()} için yetersiz veri: {n_pos} pozitif (min {min_req}).")
    st.info(f"💡 Saha ekibi {min_req - n_pos} yeni lab sonucu girerse eğitilebilir.")
    if n_pos == 0:
        st.stop()


# ============== THRESHOLD STRATEJİSİ ==============

st.subheader("2️⃣ Threshold Stratejisi")

strategy = st.radio(
    "Yaklaşım",
    ["per_district", "global", "custom"],
    horizontal=True,
    format_func=lambda s: {
        "per_district": "🎯 Per-district tuned (öneri)",
        "global": "🌐 Global (0.10)",
        "custom": "⚙️ Custom",
    }[s],
    help="""
    **Per-district:** Her district için ayrı threshold (Kappa max)
    **Global:** Tüm Cyprus için tek threshold 0.10
    **Custom:** Slider ile manuel threshold
    """,
)

custom_threshold = 0.10
if strategy == "custom":
    custom_threshold = st.slider(
        "Custom threshold",
        min_value=0.05, max_value=0.95,
        value=0.10, step=0.05,
        help="Bu threshold üzerindeki olasılıklı hücreler watch list'e girer",
    )
    st.caption(f"Seçili: **{custom_threshold:.2f}**")
elif strategy == "global":
    st.caption("Global threshold: **0.10**")
else:
    st.caption("Per-district threshold tuning (her district için ayrı, Kappa max)")


# ============== RETRAIN ==============

st.markdown("---")
st.subheader("3️⃣ Çalıştır")

if st.button("▶ Retrain & Predict 642 Hücre", type="primary", use_container_width=True):
    with st.spinner("🚀 Pipeline başlıyor..."):
        try:
            result = ml_pipeline.run_species_pipeline(
                species=species_choice,
                strategy=strategy,
                custom_threshold=custom_threshold,
            )
        except Exception as e:
            st.error(f"❌ Pipeline hatası: {e}")
            import traceback
            st.code(traceback.format_exc())
            st.stop()

    st.session_state["last_ml_result"] = result
    st.session_state["last_ml_species"] = species_choice
    st.rerun()


# ============== SONUÇ ==============

if "last_ml_result" in st.session_state:
    result = st.session_state["last_ml_result"]
    species = st.session_state.get("last_ml_species", "?")

    st.markdown("---")
    st.subheader("📊 Sonuç")

    if result["status"] == "skip":
        st.warning(f"⏭️ Skip: {result.get('reason', '—')}")
    elif result["status"] == "error":
        st.error(f"❌ Hata: {result.get('reason', '—')}")
    else:
        st.success(f"✅ {species.capitalize()} pipeline tamamlandı")

        # Metrics row
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Training (n)", result["n_train"])
        m2.metric("Pozitif", result["n_positive"])
        m3.metric("Negatif", result["n_negative"])
        m4.metric("Predict edilen", result["n_predicted"])
        m5.metric("Watch list", result["watch_list_size"])

        # Validation metrics
        st.markdown("##### 📈 Validation (LOOCV)")
        val = result.get("val_metrics", {})
        v1, v2, v3 = st.columns(3)
        v1.metric("PR-AUC", f"{val.get('pr_auc', 0):.3f}" if val.get('pr_auc') is not None else "N/A")
        v2.metric("Kappa", f"{val.get('kappa', 0):.3f}" if val.get('kappa') is not None else "N/A")
        v3.metric("ROC-AUC", f"{val.get('roc_auc', 0):.3f}" if val.get('roc_auc') is not None else "N/A")

        # Per-district thresholds
        thresholds = result.get("thresholds", {})
        if thresholds:
            st.markdown("##### 🎯 Per-District Threshold Tuning")
            threshold_df = pd.DataFrame([
                {
                    "District": d,
                    "Best Threshold": f"{info['threshold']:.2f}",
                    "Kappa (tuned)": f"{info['kappa']:.3f}",
                }
                for d, info in thresholds.items()
            ])
            st.dataframe(threshold_df, use_container_width=True, hide_index=True)
        else:
            st.caption(f"Strategy: **{result.get('strategy', '?')}**, global threshold: **{custom_threshold:.2f}**")

        # Watch list preview
        st.markdown("##### 👀 Yeni Watch List")
        new_watch = load_watch_list()
        if len(new_watch) > 0:
            new_watch = new_watch[new_watch["species"] == species]
            st.caption(f"📊 {len(new_watch)} hücre watch'ta")

            display_df = new_watch[["cell_id", "district", "proba", "threshold_used"]].head(20).copy()
            display_df["proba"] = display_df["proba"].apply(fmt_proba)
            display_df["threshold_used"] = display_df["threshold_used"].apply(fmt_proba)
            display_df.columns = ["Cell", "District", "Proba", "Threshold"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            if len(new_watch) > 20:
                st.caption(f"+ {len(new_watch) - 20} hücre daha (Dashboard'da)")
        else:
            st.info("Watch list boş.")


# ============== MEVCUT WATCH LIST ==============

st.markdown("---")
st.subheader("📋 Mevcut Watch List")
st.caption("Sheets'te mevcut watch list (son retrain'den)")

if len(watch_df) > 0:
    tabs = st.tabs(["Culex", "Aedes"])
    for tab, sp in zip(tabs, ["culex", "aedes"]):
        with tab:
            sub = watch_df[watch_df["species"] == sp].sort_values("proba", ascending=False)
            if len(sub) == 0:
                st.info(f"{sp} için watch list boş")
            else:
                st.caption(f"Toplam: {len(sub)} hücre")

                # District summary
                dsummary = sub.groupby("district").agg(
                    count=("cell_id", "count"),
                    avg_proba=("proba", "mean"),
                ).reset_index()
                dsummary["avg_proba"] = dsummary["avg_proba"].apply(fmt_proba)
                st.dataframe(dsummary, use_container_width=True, hide_index=True)

                # Top 10
                display = sub[["cell_id", "district", "proba", "threshold_used", "visited"]].head(10).copy()
                display["proba"] = display["proba"].apply(fmt_proba)
                display["threshold_used"] = display["threshold_used"].apply(fmt_proba)
                display["visited"] = display["visited"].map({True: "✅", False: "⏳"})
                display.columns = ["Cell", "District", "Proba", "Threshold", "Ziyaret"]
                st.dataframe(display, use_container_width=True, hide_index=True)
else:
    st.info("Watch list boş. Yukarıdaki butonla ilk retrain'i başlatın.")


# Footer
st.markdown("---")
st.caption("""
💡 **İpucu:** Her yeni lab sonucundan sonra retrain yap → watch list güncellenir →
saha ekibi yeni önerileri görür → yeni trap kurulur → döngü tekrarlanır.
""")
