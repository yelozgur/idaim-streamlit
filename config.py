"""config.py — Streamlit app constants and paths.

Sheet names live here. Sheet names must match SHEETS_HEADERS.md exactly.
"""
from pathlib import Path

# ============== Sheets ==============
SPREADSHEET_ID = "SET_VIA_STREAMLIT_SECRETS"  # secrets.toml

SHEET_NAMES = {
    "cells": "cells",
    "sampling_initiation": "sampling_initiation",
    "trap_checks": "trap_checks",
    "lab_results": "lab_results",
    "watch_list": "watch_list",
    "features_cache": "features_cache",
    "users": "users",
}

# ============== Google Drive (photos) ==============
DRIVE_ROOT_FOLDER = "IDAIM-Cyprus-Photos"
DRIVE_SUBFOLDERS = {
    "sampling_initiation": "sampling",
    "trap_checks": "checks",
    "lab_results": "lab",
}

# ============== Districts (Cyprus) ==============
DISTRICTS = ["Keryneia", "Nicosia", "Famagusta", "Larnaca", "Limassol", "Paphos"]

# ============== ML Constants ==============
DYNAMIC_FEATURES = ["LST", "NDVI", "Humidity", "Precip", "WindSpeed"]
ALPHAEARTH_YEAR = 2024

# Threshold strategies
THRESHOLD_STRATEGIES = {
    "global": 0.10,
    "per_district": None,
    "custom_default": 0.10,
}

# Per-species minimum sample for training
MIN_SAMPLES = {
    "culex": 5,
    "aedes": 1,
}

# ============== UI ==============
APP_TITLE = "IDAIM Cyprus — Vector Surveillance"
APP_ICON = "🦟"

# ============== Auth (default users) ==============
# username: (password_plain, role)
DEFAULT_USERS = {
    "admin": ("idaim2026", "admin"),
    "field": ("field2026", "field"),
    "lab": ("lab2026", "lab"),
}

# ============== Cache ==============
CACHE_TTL_DAYS = 30
