"""3_⚙️_Admin.py — Admin-only page.

Admin sees:
  - Training metrics (latest from Colab)
  - Sheets health (all 7 sheets)
  - User management (list users, change role, reset password)
  - Watch list management
  - System info (cron schedule, deploy status)
"""
import streamlit as st
import pandas as pd
import json
import hashlib
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import mobile_styles
import sheets_client
from utils import (
    load_cells, load_labeled_cells, load_watch_list,
    fmt_proba, fmt_count, compute_label_counts,
    require_admin,
)


# ============== PAGE SETUP ==============

st.set_page_config(page_title="Admin", page_icon="⚙️", layout="wide")
mobile_styles.inject_mobile_css()
require_admin()


# ============== HEADER ==============

st.title("⚙️ Admin")
st.caption("Admin-only — training metrics, Sheets health, user management")
st.markdown("---")


# ============== SECTION 1: DATA STATUS ==============

st.subheader("Data Status")
label_counts = compute_label_counts()
watch_df = load_watch_list()
cells_df = load_cells()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Lab", label_counts["total"])
col2.metric("Culex positive", label_counts["culex_pos"])
col3.metric("Cedes positive", label_counts["aedes_pos"])
col4.metric("Watch List", len(watch_df))

st.caption(f"Culex: {label_counts['culex_pos']} positives (min {config.MIN_SAMPLES['culex']} to train) | Aedes: {label_counts['aedes_pos']} (min {config.MIN_SAMPLES['aedes']})")

if label_counts["aedes_pos"] == 0:
    st.info("Aedes: skip (no samples)")
if label_counts["culex_pos"] < config.MIN_SAMPLES["culex"]:
    st.info(f"Culex: needs {config.MIN_SAMPLES['culex'] - label_counts['culex_pos']} more lab result(s) to be trainable")

st.markdown("---")


# ============== SECTION 2: TRAINING METRICS ==============

st.subheader("Training Metrics")
st.caption("Latest Colab T4 training run. Auto-updated every Sunday 21:00.")

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
            st.warning(f"{p} not readable: {e}")

if metrics:
    trained_at = metrics.get("trained_at", "?")
    if trained_at != "?":
        try:
            dt = datetime.fromisoformat(trained_at)
            trained_at_human = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            trained_at_human = trained_at
    else:
        trained_at_human = "?"

    st.caption(f"Trained at: **{trained_at_human}** | Source: `{metrics_source}`")

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

        max_pos = max(row["n_positive"] for row in species_rows) if species_rows else 0
        if max_pos < 5:
            st.warning("Low data (n<5 positives). PR-AUC may look high due to overfitting. Realistic metrics will come as field data grows.")

    with st.expander("Raw metrics.json"):
        st.json(metrics)
else:
    st.warning("metrics.json not found. Training has not run yet, or the model has not been pushed to this repo.")
    st.code("\n".join(str(p) for p in metrics_paths))

st.markdown("---")


# ============== SECTION 3: SHEETS HEALTH ==============

st.subheader("Sheets Health")

try:
    status = sheets_client.sheet_health_check()
    rows = []
    for key, info in status.items():
        rows.append({
            "Sheet": key,
            "Status": "OK" if info["exists"] else "MISSING",
            "Rows": info["rows"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
except Exception as e:
    st.error(f"Health check error: {e}")

st.markdown("---")


# ============== SECTION 4: USER MANAGEMENT ==============

st.subheader("User Management")

try:
    users_df = sheets_client.read_sheet("users", dtype_fix=False)

    if len(users_df) > 0:
        st.dataframe(users_df, use_container_width=True, hide_index=True)

        st.markdown("##### Reset Password")
        col1, col2, col3 = st.columns(3)
        with col1:
            target_user = st.selectbox("User", users_df["username"].astype(str).tolist())
        with col2:
            new_password = st.text_input("New password", type="password")
        with col3:
            st.write("")
            st.write("")
            if st.button("Reset Password", type="primary", use_container_width=True):
                if not new_password or len(new_password) < 6:
                    st.error("Password must be at least 6 characters")
                else:
                    try:
                        mask = users_df["username"].astype(str) == target_user
                        if mask.any():
                            users_df.loc[mask, "password_hash"] = hashlib.sha256(new_password.encode()).hexdigest()
                            sheets_client.update_dataframe("users", users_df)
                            sheets_client._load_users.clear()
                            st.success(f"Password reset for {target_user}")
                        else:
                            st.error("User not found")
                    except Exception as e:
                        st.error(f"Reset error: {e}")

        st.markdown("##### Add User")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            new_user = st.text_input("Username")
        with col2:
            new_pw = st.text_input("Password", type="password")
        with col3:
            new_role = st.selectbox("Role", ["admin", "field", "lab"])
        with col4:
            st.write("")
            st.write("")
            if st.button("Add User", type="primary", use_container_width=True):
                if not new_user or not new_pw:
                    st.error("Username and password required")
                elif new_user in users_df["username"].astype(str).tolist():
                    st.error("User already exists")
                else:
                    try:
                        new_row = {
                            "username": new_user,
                            "password_hash": hashlib.sha256(new_pw.encode()).hexdigest(),
                            "role": new_role,
                            "last_login": "",
                        }
                        sheets_client.append_row("users", new_row)
                        sheets_client._load_users.clear()
                        st.success(f"User {new_user} added with role {new_role}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Add error: {e}")
    else:
        st.info("No users in the users sheet")
except Exception as e:
    st.error(f"User list error: {e}")

st.markdown("---")


# ============== SECTION 5: SYSTEM INFO ==============

st.subheader("System Info")

sys_rows = [
    {"Setting": "App version", "Value": "v0.6.0"},
    {"Setting": "ML training schedule", "Value": "Every Sunday 21:00 (Asia/Nicosia)"},
    {"Setting": "ML training location", "Value": "Google Colab T4 GPU"},
    {"Setting": "ML orchestration", "Value": "mavis cron: idaim-weekly-retrain"},
    {"Setting": "GEE features refresh", "Value": "On-demand (manual) / Sunday 21:00 cron"},
    {"Setting": "Data source", "Value": "Google Sheets (UNDP-owned)"},
    {"Setting": "Default admin password", "Value": "idaim2026 (change after first login)"},
    {"Setting": "Default field password", "Value": "field2026 (change after first login)"},
    {"Setting": "Default lab password", "Value": "lab2026 (change after first login)"},
]
st.dataframe(pd.DataFrame(sys_rows), use_container_width=True, hide_index=True)
