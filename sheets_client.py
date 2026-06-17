"""sheets_client.py — Google Sheets wrapper.

All read/write operations go through here. Uses gspread + gspread-dataframe.

Service account auth: JSON key from streamlit secrets.
"""
import gspread
import pandas as pd
import streamlit as st
from gspread_dataframe import set_with_dataframe, get_as_dataframe
from typing import Optional
import hashlib
from datetime import datetime

from config import SHEET_NAMES, DEFAULT_USERS


# ============== AUTH ==============

@st.cache_resource
def get_gspread_client():
    """Service-account gspread client (cached)."""
    try:
        creds_dict = st.secrets["gcp_service_account"]
        gc = gspread.service_account_from_dict(creds_dict)
        return gc
    except Exception as e:
        st.error(f"Google auth failed: {e}")
        st.stop()


@st.cache_resource
def get_spreadsheet():
    """Spreadsheet object (cached)."""
    gc = get_gspread_client()
    sheet_id = st.secrets["spreadsheet"]["id"]
    return gc.open_by_key(sheet_id)


def get_worksheet(name: str):
    """Worksheet by name."""
    sh = get_spreadsheet()
    try:
        return sh.worksheet(name)
    except gspread.WorksheetNotFound:
        st.error(f"Sheet not found: '{name}'. See SHEETS_HEADERS.md.")
        st.stop()


# ============== READ ==============

def read_sheet(name: str, dtype_fix: bool = True) -> pd.DataFrame:
    """Read sheet as DataFrame.

    With dtype_fix=True, numeric columns are coerced (Sheets returns strings).
    """
    ws = get_worksheet(name)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    df = df.dropna(how="all")

    if dtype_fix and len(df) > 0:
        df = _fix_dtypes(df, name)
    return df


def _fix_dtypes(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """Fix dtypes per sheet."""
    if sheet_name == "cells":
        if "cell_id" in df.columns:
            df["cell_id"] = pd.to_numeric(df["cell_id"], errors="coerce").astype("Int64")
        for c in ["lon", "lat", "culex_proba", "aedes_proba"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

    elif sheet_name == "sampling_initiation":
        if "cell_id" in df.columns:
            df["cell_id"] = pd.to_numeric(df["cell_id"], errors="coerce").astype("Int64")

    elif sheet_name == "lab_results":
        if "cell_id" in df.columns:
            df["cell_id"] = pd.to_numeric(df["cell_id"], errors="coerce").astype("Int64")
        if "count" in df.columns:
            df["count"] = pd.to_numeric(df["count"], errors="coerce").astype("Int64")

    elif sheet_name == "watch_list":
        if "cell_id" in df.columns:
            df["cell_id"] = pd.to_numeric(df["cell_id"], errors="coerce").astype("Int64")
        if "proba" in df.columns:
            df["proba"] = pd.to_numeric(df["proba"], errors="coerce")
        if "threshold_used" in df.columns:
            df["threshold_used"] = pd.to_numeric(df["threshold_used"], errors="coerce")
        if "visited" in df.columns:
            df["visited"] = df["visited"].astype(str).str.lower().isin(["true", "1", "yes"])

    elif sheet_name == "users":
        pass

    return df


# ============== WRITE ==============

def append_row(sheet_name: str, row: dict):
    """Append a single row. Dict keys must match sheet headers."""
    ws = get_worksheet(sheet_name)
    headers = ws.row_values(1)
    row_values = [str(row.get(h, "")) for h in headers]
    ws.append_row(row_values, value_input_option="USER_ENTERED")
    read_sheet.clear()


def append_rows(sheet_name: str, rows: list[dict]):
    """Append multiple rows (batch)."""
    if not rows:
        return
    ws = get_worksheet(sheet_name)
    headers = ws.row_values(1)
    values = [[str(r.get(h, "")) for h in headers] for r in rows]
    ws.append_rows(values, value_input_option="USER_ENTERED")
    read_sheet.clear()


def update_cell(sheet_name: str, row_idx: int, col_name: str, value):
    """Update a single cell (1-indexed row)."""
    ws = get_worksheet(sheet_name)
    headers = ws.row_values(1)
    col_idx = headers.index(col_name) + 1
    ws.update_cell(row_idx + 1, col_idx, value)
    read_sheet.clear()


def update_dataframe(sheet_name: str, df: pd.DataFrame, start_row: int = 2):
    """Write DataFrame to sheet (overwrites existing data, headers preserved)."""
    ws = get_worksheet(sheet_name)
    set_with_dataframe(ws, df, row=start_row, include_column_header=False)
    read_sheet.clear()


# ============== SPECIFIC HELPERS ==============

def get_cells() -> pd.DataFrame:
    """All cells + ML output."""
    return read_sheet("cells")


def get_sampling_initiations(active_only: bool = True) -> pd.DataFrame:
    """Sampling initiation records."""
    df = read_sheet("sampling_initiation")
    if active_only and "state" in df.columns and len(df) > 0:
        df = df[df["state"] == "active"]
    return df


def get_trap_checks(trap_id: Optional[str] = None) -> pd.DataFrame:
    """Trap checks (optional trap filter)."""
    df = read_sheet("trap_checks")
    if trap_id and "trap_id" in df.columns and len(df) > 0:
        df = df[df["trap_id"] == trap_id]
    return df


def get_lab_results(cell_id: Optional[int] = None) -> pd.DataFrame:
    """Lab results (optional cell filter)."""
    df = read_sheet("lab_results")
    if cell_id and "cell_id" in df.columns and len(df) > 0:
        df = df[df["cell_id"] == cell_id]
    return df


def get_watch_list(species: Optional[str] = None) -> pd.DataFrame:
    """Watch list (ML recommendations)."""
    df = read_sheet("watch_list")
    if species and "species" in df.columns and len(df) > 0:
        df = df[df["species"] == species]
    return df


def update_cells_proba(species: str, proba_array: list[float]):
    """Update all cells' probability (species='culex' or 'aedes')."""
    df = get_cells()
    if len(df) == 0:
        return
    col = f"{species}_proba"
    if col not in df.columns:
        st.warning(f"Column '{col}' missing in cells sheet")
        return
    df[col] = proba_array[:len(df)]
    df["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    df["confidence_tier"] = df[col].apply(_proba_to_tier)
    update_dataframe("cells", df)


def _proba_to_tier(p: float) -> str:
    if pd.isna(p):
        return "unknown"
    if p >= 0.7:
        return "high"
    if p >= 0.4:
        return "medium"
    if p >= 0.2:
        return "low"
    return "unknown"


# ============== AUTH ==============

def hash_password(password: str) -> str:
    """SHA256 hash (no salt — POC only)."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_user(username: str, password: str) -> Optional[str]:
    """Verify user, return role. None = failure."""
    users = _load_users()
    if username not in users:
        return None
    stored_hash, role = users[username]
    if stored_hash == hash_password(password):
        return role
    return None


@st.cache_data(ttl=300)
def _load_users() -> dict:
    """Load users sheet, write defaults on first run."""
    try:
        df = read_sheet("users", dtype_fix=False)
    except Exception:
        df = pd.DataFrame()

    users = {}
    if len(df) > 0 and "username" in df.columns:
        for _, row in df.iterrows():
            u = str(row["username"])
            h = str(row["password_hash"])
            r = str(row.get("role", "viewer"))
            users[u] = (h, r)
    else:
        rows = []
        for u, (pw, role) in DEFAULT_USERS.items():
            rows.append({
                "username": u,
                "password_hash": hash_password(pw),
                "role": role,
                "last_login": "",
            })
        if rows:
            append_rows("users", rows)
        users = {u: (hash_password(pw), role) for u, (pw, role) in DEFAULT_USERS.items()}

    return users


def update_last_login(username: str):
    """Update last login time."""
    df = read_sheet("users", dtype_fix=False)
    if len(df) == 0:
        return
    if "username" not in df.columns:
        return
    mask = df["username"] == username
    if mask.any():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df.loc[mask, "last_login"] = now
        update_dataframe("users", df)
        _load_users.clear()


# ============== UTIL ==============

def sheet_health_check() -> dict:
    """Check all sheets exist."""
    gc = get_gspread_client()
    sh = get_spreadsheet()
    status = {}
    for key, name in SHEET_NAMES.items():
        try:
            ws = sh.worksheet(name)
            n_rows = len(ws.get_all_values())
            status[key] = {"exists": True, "rows": n_rows}
        except gspread.WorksheetNotFound:
            status[key] = {"exists": False, "rows": 0}
    return status
