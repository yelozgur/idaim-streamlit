"""sheets_client.py — Google Sheets wrapper (framework-agnostic).

All read/write operations go through here. Uses gspread + gspread-dataframe.

Auth (v0.7+, env-based, dual-mode for Streamlit legacy + Plotly Dash):
  1. GCP_SA_JSON env var (HF Spaces / production) — JSON content as string
  2. GCP_SA_JSON_PATH env var (explicit path to JSON file)
  3. Default local path: ~/Documents/Personal Projects/ee-yelozgur-*.json
  4. SHEET_ID env var (default: '16wqnRUUPNBA_qhPMEdy4g9gCm_QKu5IxyCbJweStRCY')

Cache: module-level TTL cache replaces @st.cache_data (works in both
Streamlit and Dash). Use clear_read_cache() to invalidate after writes.
"""
import os
import json
import time
import logging
import gspread
import pandas as pd
from gspread_dataframe import set_with_dataframe, get_as_dataframe
from typing import Optional
import hashlib
from datetime import datetime

from config import SHEET_NAMES, DEFAULT_USERS

logger = logging.getLogger(__name__)

# Default credentials path (developer machine)
_DEFAULT_SA_PATH = os.path.expanduser(
    "~/Documents/Personal Projects/ee-yelozgur-aceaafb59a17.json"
)
_DEFAULT_SHEET_ID = "16wqnRUUPNBA_qhPMEdy4g9gCm_QKu5IxyCbJweStRCY"


# ============== AUTH ==============

# Module-level cache (replaces @st.cache_resource)
_gspread_client = None
_spreadsheet = None
_read_cache: dict = {}  # name -> (timestamp, df)
_users_cache: dict = {"data": None, "ts": 0.0}


def _get_creds_dict() -> dict:
    """Resolve credentials dict from env or default local path.

    Priority:
      1. GCP_SA_JSON env var (HF Spaces — JSON content)
      2. GCP_SA_JSON_PATH env var (explicit path to file)
      3. ~/Documents/Personal Projects/ee-yelozgur-*.json (local dev default)
    """
    if "GCP_SA_JSON" in os.environ:
        return json.loads(os.environ["GCP_SA_JSON"])

    if "GCP_SA_JSON_PATH" in os.environ:
        with open(os.environ["GCP_SA_JSON_PATH"]) as f:
            return json.load(f)

    if os.path.exists(_DEFAULT_SA_PATH):
        with open(_DEFAULT_SA_PATH) as f:
            return json.load(f)

    raise RuntimeError(
        "Sheets credentials not found. Set GCP_SA_JSON or GCP_SA_JSON_PATH "
        f"env var, or place credentials at {_DEFAULT_SA_PATH}"
    )


def get_gspread_client():
    """Service-account gspread client (cached at module level)."""
    global _gspread_client
    if _gspread_client is None:
        creds_dict = _get_creds_dict()
        _gspread_client = gspread.service_account_from_dict(creds_dict)
    return _gspread_client


def get_spreadsheet():
    """Spreadsheet object (cached at module level)."""
    global _spreadsheet
    if _spreadsheet is None:
        gc = get_gspread_client()
        sheet_id = os.environ.get("SHEET_ID", _DEFAULT_SHEET_ID)
        _spreadsheet = gc.open_by_key(sheet_id)
    return _spreadsheet


def get_worksheet(name: str):
    """Worksheet by name."""
    sh = get_spreadsheet()
    try:
        return sh.worksheet(name)
    except gspread.WorksheetNotFound:
        logger.error(f"Sheet not found: '{name}'. See SHEETS_HEADERS.md.")
        raise


# ============== READ ==============

DEFAULT_READ_TTL = 60  # seconds, Sheets API 429 protection


def read_sheet(name: str, dtype_fix: bool = True, ttl: int = DEFAULT_READ_TTL) -> pd.DataFrame:
    """Read sheet as DataFrame (TTL cache for Sheets API 429 protection).

    With dtype_fix=True, numeric columns are coerced (Sheets returns strings).

    Cache: module-level TTL cache. Use clear_read_cache() to invalidate
    after writes. Pre-v0.7 this used @st.cache_data(ttl=60).
    """
    now = time.time()
    if name in _read_cache:
        ts, df = _read_cache[name]
        if now - ts < ttl:
            return df

    ws = get_worksheet(name)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    df = df.dropna(how="all")

    if dtype_fix and len(df) > 0:
        df = _fix_dtypes(df, name)

    _read_cache[name] = (now, df)
    return df


def clear_read_cache(name: Optional[str] = None):
    """Clear read cache (call after writes). If name is None, clear all."""
    if name:
        _read_cache.pop(name, None)
    else:
        _read_cache.clear()


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
    clear_read_cache()


def append_rows(sheet_name: str, rows: list[dict]):
    """Append multiple rows (batch)."""
    if not rows:
        return
    ws = get_worksheet(sheet_name)
    headers = ws.row_values(1)
    values = [[str(r.get(h, "")) for h in headers] for r in rows]
    ws.append_rows(values, value_input_option="USER_ENTERED")
    clear_read_cache()


def update_cell(sheet_name: str, row_idx: int, col_name: str, value):
    """Update a single cell.

    Args:
        sheet_name: Sheet name.
        row_idx: 0-indexed DATA row (0=first data row, header excluded).
                 sheet_row = row_idx + 2 (1 for header offset + 1 for 1-indexed).
        col_name: Column name (must exist in header).
        value: Value to write.

    Note: v0.6 had a bug where row_idx+1 was used, causing row_idx=0 to write
    to the header row. Fixed in v0.6.1 to use row_idx+2.
    """
    ws = get_worksheet(sheet_name)
    headers = ws.row_values(1)
    if col_name not in headers:
        logger.error(f"Column '{col_name}' not found in '{sheet_name}'")
        return
    col_idx = headers.index(col_name) + 1
    sheet_row = row_idx + 2
    ws.update_cell(sheet_row, col_idx, value)
    clear_read_cache()


def update_dataframe(sheet_name: str, df: pd.DataFrame, start_row: int = 2):
    """Write DataFrame to sheet (overwrites existing data, headers preserved)."""
    ws = get_worksheet(sheet_name)
    set_with_dataframe(ws, df, row=start_row, include_column_header=False)
    clear_read_cache()


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
        logger.warning(f"Column '{col}' missing in cells sheet")
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


USERS_CACHE_TTL = 300  # seconds


def _load_users() -> dict:
    """Load users sheet, write defaults on first run (5min TTL cache)."""
    now = time.time()
    if _users_cache["data"] is not None and now - _users_cache["ts"] < USERS_CACHE_TTL:
        return _users_cache["data"]

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

    _users_cache["data"] = users
    _users_cache["ts"] = now
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
        _users_cache["data"] = None
        _users_cache["ts"] = 0.0


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
