"""config.py — Streamlit app için sabitler ve path'ler.

Sheets ID ve sayfa adları burada. Sheet adlarını birebir aynı kullan
(SHEETS_HEADERS.md ile uyumlu).
"""
from pathlib import Path

# ============== Sheets Yapısı ==============
# Streamlit secrets'tan okunur, yoksa default
SPREADSHEET_ID = "BURAYA_SHEET_ID"  # secrets.toml'dan gelecek

SHEET_NAMES = {
    "cells": "cells",
    "sampling_initiation": "sampling_initiation",
    "trap_checks": "trap_checks",
    "lab_results": "lab_results",
    "watch_list": "watch_list",
    "features_cache": "features_cache",
    "users": "users",
}

# ============== Google Drive (fotoğraflar için) ==============
DRIVE_ROOT_FOLDER = "IDAIM-Cyprus-Photos"  # Drive'da bu klasör oluşmalı
DRIVE_SUBFOLDERS = {
    "sampling_initiation": "sampling",
    "trap_checks": "checks",
    "lab_results": "lab",
}

# ============== District'ler (Cyprus) ==============
DISTRICTS = ["Keryneia", "Nicosia", "Famagusta", "Larnaca", "Limassol", "Paphos"]

# ============== ML Sabitleri ==============
DYNAMIC_FEATURES = ["LST", "NDVI", "Humidity", "Precip", "WindSpeed"]
ALPHAEARTH_YEAR = 2024
MINIROCKET_INPUT_SHAPE = (5, 12)  # 5 features × 12 months

# Threshold stratejileri
THRESHOLD_STRATEGIES = {
    "global": 0.10,
    "per_district": None,  # ablation_hybrid.json'dan yüklenecek
    "custom_default": 0.10,
}

# Per-species minimum sample
MIN_SAMPLES = {
    "culex": 5,
    "aedes": 1,
}

# ============== UI ==============
APP_TITLE = "IDAIM Cyprus — Vector Surveillance"
APP_ICON = "🦟"

# ============== Auth (basit şifre) ==============
DEFAULT_USERS = {
    # username: (password_plain, role) — ilk açılışta hash'lenir
    "admin": ("idaim2026", "admin"),
    "field": ("field2026", "field"),
    "lab": ("lab2026", "lab"),
}

# ============== Cache ==============
CACHE_TTL_DAYS = 30  # features_cache 30 gün sonra tazele
