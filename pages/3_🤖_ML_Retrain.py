"""3_🤖_ML_Retrain.py — Per-species MiniRocket training UI.

NOT (2026-06-17): Training artık Streamlit Cloud'da değil, Colab T4 GPU'da çalışıyor.
Bu sayfa sadece:
  1. Veri durumunu gösterir (Sheets'ten)
  2. Son training'in metrics.json'unu gösterir (Colab'dan indirilen)
  3. Manuel tetikleme için "Colab'da çalıştır" komutu gösterir

Haftalık otomatik training: her Pazartesi 09:00 (mavis cron: idaim-weekly-retrain)
Manuel tetikleme: terminal'de `bash retrain-weekly.sh`
"""
import streamlit as st
import pandas as pd
import json
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import mobile_styles
import utils
from utils import (
    load_cells, load_labeled_cells, load_watch_list, clear_all_caches,
    fmt_proba, fmt_count, compute_label_counts,
)


# ============== PAGE SETUP ==============

st.set_page_config(page_title="ML Retrain", page_icon="🤖", layout="wide")
mobile_styles.inject_mobile_css()
utils.require_auth()


# ============== HEADER ==============

st.title("🤖 ML Retrain")
st.caption("Training Colab T4 GPU'da haftalık çalışır (Pzt 09:00). Bu sayfa: veri durumu + son metrics.")

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


# ============== RETRAIN BİLGİSİ ==============

st.markdown("---")
st.subheader("🤖 Training Pipeline (Colab T4)")

st.info("""
**Training artık Streamlit Cloud'da değil, Colab T4 GPU'da çalışıyor.**

**Otomatik:** Her Pazartesi 09:00 (mavis cron: `idaim-weekly-retrain`)
**Manuel tetikleme:** Terminal'de `bash /Users/ozguryel/Documents/CODE/IDAIM/idaim-pipeline/retrain-weekly.sh`
""")

# Son training metrics.json
metrics_paths = [
    Path(__file__).parent.parent / "data" / "models" / "metrics.json",
    Path("/Users/ozguryel/Documents/CODE/IDAIM/idaim-pipeline/data/07_models/metrics.json"),
]
metrics = None
metrics_source = None
for p in metrics_paths:
    if p.exists():
        try:
            with open(p) as f:
                metrics = json.load(f)
            metrics_source = str(p)
            break
        except Exception as e:
            st.warning(f"⚠️ {p} okunamadı: {e}")

if metrics:
    st.markdown("##### 📈 Son Training Metrics")
    st.caption(f"Kaynak: `{metrics_source}`")

    trained_at = metrics.get("trained_at", "?")
    if trained_at != "?":
        try:
            dt = datetime.fromisoformat(trained_at)
            trained_at_human = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            trained_at_human = trained_at
    else:
        trained_at_human = "?"

    st.caption(f"🕐 Trained at: **{trained_at_human}**")

    # Per-species tablo
    species_rows = []
    for sp in metrics.get("species", []):
        cv = sp.get("cv_loocv", {})
        species_rows.append({
            "Species": sp.get("species", "?").capitalize(),
            "n_train": sp.get("n_train", 0),
            "n_positive": sp.get("n_positive", 0),
            "n_neg_pseudo": sp.get("n_negative_pseudo", 0),
            "PR-AUC": f"{cv.get('pr_auc'):.3f}" if cv.get('pr_auc') is not None else "N/A",
            "Kappa": f"{cv.get('kappa'):.3f}" if cv.get('kappa') is not None else "N/A",
            "ROC-AUC": f"{cv.get('roc_auc'):.3f}" if cv.get('roc_auc') is not None else "N/A",
            "Failed folds": cv.get('failed_folds', 0),
        })

    if species_rows:
        df = pd.DataFrame(species_rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Uyarı: 1 pozitifli training overfit olabilir
        max_pos = max(row["n_positive"] for row in species_rows) if species_rows else 0
        if max_pos < 5:
            st.warning("⚠️ Veri az (n<5 pozitif). PR-AUC yüksek görünebilir ama overfit riski var. Saha verisi arttıkça gerçekçi metrikler gelecek.")

    # Detaylı JSON
    with st.expander("🔍 Raw metrics.json"):
        st.json(metrics)
else:
    st.warning("⚠️ metrics.json bulunamadı. Training henüz çalışmamış veya model repo'ya push edilmemiş.")
    st.code("\n".join(str(p) for p in metrics_paths))


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
