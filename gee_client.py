"""gee_client.py — Google Earth Engine REST API ile feature extraction.

Tek bir hücre için (5, 12) feature array çeker:
  - 5 dinamik feature × 12 ay
  - LST (MODIS), NDVI (MODIS), Humidity (ERA5), Precip (CHIRPS/ERA5), WindSpeed (ERA5)

Mevcut 28_extract_gee_monthly.py ile aynı data source, sadece REST API üzerinden
(Streamlit Cloud'da earthengine-api Python package çalışmayabilir).
"""
import streamlit as st
import requests
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional
import time

from config import DYNAMIC_FEATURES, ALPHAEARTH_YEAR


# ============== AUTH ==============

def get_access_token() -> str:
    """Service account'tan OAuth2 access token al (REST API için)."""
    try:
        from google.oauth2.service_account import Credentials
        from google.auth.transport.requests import Request

        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/earthengine"],
        )
        creds.refresh(Request())
        return creds.token
    except Exception as e:
        st.error(f"❌ GEE auth hatası: {e}")
        return ""


def get_project() -> str:
    """GEE project ID (secrets.toml'dan)."""
    try:
        return st.secrets.get("gee", {}).get("project", "ee-yelozgur")
    except Exception:
        return "ee-yelozgur"


# ============== GEE QUERY ==============

def _run_ee_query(expression: str, timeout: int = 30) -> dict:
    """Bir GEE expression çalıştır, JSON sonuç döner.

    Endpoint: https://earthengine.googleapis.com/v1/{project}:value:compute
    """
    token = get_access_token()
    if not token:
        return {}

    project = get_project()
    url = f"https://earthengine.googleapis.com/v1/projects/{project}:value:compute"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    body = {"expression": expression}

    try:
        resp = requests.post(url, json=body, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return {}
        return resp.json()
    except requests.Timeout:
        st.warning(f"⏱️ GEE timeout ({timeout}s)")
        return {}
    except Exception as e:
        st.warning(f"⚠️ GEE query hatası: {e}")
        return {}


# ============== FEATURE EXTRACTION ==============

def _build_monthly_expression(feature: str, point_geom: dict, year: int) -> str:
    """Bir feature için 12 aylık aggregate expression oluştur.

    Sonuç: {result: '12 değerli liste'} döner.
    """
    if feature == "LST":
        # MODIS LST (Kelvin × 0.02 → Celsius)
        coll_filter = f"ee.ImageCollection('MODIS/061/MOD11A1').filterDate('{year}-01-01', '{year+1}-01-01').filterBounds(ee.Geometry({point_geom}))"
        scale = 0.02
        offset = -273.15  # Kelvin → Celsius
        return f"ee.ImageCollection('MODIS/061/MOD11A1').filterDate('{year}-01-01', '{year+1}-01-01').filterBounds(ee.Geometry({point_geom})).select('LST_Day_1km').map(lambda img: img.multiply(0.02).add(-273.15).set('month', ee.Date(img.get('system:time_start')).get('month'))).reduceColumns(ee.Reducer.mean().repeat(1).group(ee.Reducer.first(), groupField=1), ['month']).get('groups')"

    elif feature == "NDVI":
        return f"ee.ImageCollection('MODIS/061/MOD13Q1').filterDate('{year}-01-01', '{year+1}-01-01').filterBounds(ee.Geometry({point_geom})).select('NDVI').map(lambda img: img.multiply(0.0001).set('month', ee.Date(img.get('system:time_start')).get('month'))).reduceColumns(ee.Reducer.mean().repeat(1).group(ee.Reducer.first(), groupField=1), ['month']).get('groups')"

    elif feature == "Humidity":
        # ERA5-Land 2m dewpoint temperature
        return f"ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY').filterDate('{year}-01-01', '{year+1}-01-01').filterBounds(ee.Geometry({point_geom})).select('dewpoint_temperature_2m').map(lambda img: img.set('month', ee.Date(img.get('system:time_start')).get('month'))).reduceColumns(ee.Reducer.mean().repeat(1).group(ee.Reducer.first(), groupField=1), ['month']).get('groups')"

    elif feature == "Precip":
        # CHIRPS daily to monthly
        return f"ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY').filterDate('{year}-01-01', '{year+1}-01-01').filterBounds(ee.Geometry({point_geom})).select('precipitation').map(lambda img: img.set('month', ee.Date(img.get('system:time_start')).get('month'))).reduceColumns(ee.Reducer.sum().repeat(1).group(ee.Reducer.first(), groupField=1), ['month']).get('groups')"

    elif feature == "WindSpeed":
        # ERA5 u/v component magnitude
        return f"ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY').filterDate('{year}-01-01', '{year+1}-01-01').filterBounds(ee.Geometry({point_geom})).map(lambda img: img.select('u_component_of_wind_10m','v_component_of_wind_10m').reduce(ee.Reducer.sqrtOfSumOfSquares()).rename('wind').set('month', ee.Date(img.get('system:time_start')).get('month'))).reduceColumns(ee.Reducer.mean().repeat(1).group(ee.Reducer.first(), groupField=1), ['month']).get('groups')"

    return ""


def fetch_features_for_cell(
    cell_id: int,
    lat: float,
    lon: float,
    year: int = ALPHAEARTH_YEAR,
) -> Optional[np.ndarray]:
    """Tek hücre için (5, 12) feature array çek.

    Returns: shape (5, 12) — her satır bir feature, 12 sütun = 12 ay
    """
    point_geom = f"ee.Geometry.Point([{lon}, {lat}])"

    # Sonuç array'i initialize
    arr = np.zeros((5, 12))
    arr[:] = np.nan

    for fi, feature in enumerate(DYNAMIC_FEATURES):
        expr = _build_monthly_expression(feature, point_geom, year)
        if not expr:
            continue

        result = _run_ee_query(expr, timeout=30)
        if not result:
            continue

        # Result format: {"result": [{"month": 1, "mean": x}, ...]}
        groups = result.get("result", [])
        if not isinstance(groups, list):
            continue

        for item in groups:
            try:
                month = int(item.get("month", 0))
                value = item.get("mean")
                if value is None:
                    value = item.get("sum")
                if month >= 1 and month <= 12 and value is not None:
                    arr[fi, month - 1] = float(value)
            except (TypeError, ValueError):
                continue

    # Eğer tüm NaN ise None döndür
    if np.all(np.isnan(arr)):
        return None

    # Eksik ayları interpolate et
    for fi in range(5):
        if np.any(np.isnan(arr[fi])):
            arr[fi] = _interp_months(arr[fi])

    return arr


def _interp_months(series: np.ndarray) -> np.ndarray:
    """NaN olan ayları linear interpole et (komşu aylardan)."""
    if not np.any(np.isnan(series)):
        return series

    n = len(series)
    x = np.arange(n)
    mask = ~np.isnan(series)
    if mask.sum() < 2:
        # Yeterli veri yok, ortalama ile doldur
        series[~mask] = 0.0
        return series

    series[~mask] = np.interp(x[~mask], x[mask], series[mask])
    return series


# ============== TOPLU FEATURE EXTRACTION ==============

def fetch_features_for_cells_batch(
    cell_ids: list[int],
    latlons: dict[int, tuple[float, float]],
    year: int = ALPHAEARTH_YEAR,
    progress_callback=None,
) -> dict[int, np.ndarray]:
    """Birden fazla hücre için feature çek (rate-limited, batch).

    Returns: {cell_id: features_5x12}
    """
    results = {}
    for i, cid in enumerate(cell_ids):
        if cid not in latlons:
            continue
        lat, lon = latlons[cid]
        feat = fetch_features_for_cell(cid, lat, lon, year=year)
        if feat is not None:
            results[cid] = feat
        if progress_callback:
            progress_callback(i + 1, len(cell_ids))
        time.sleep(0.1)  # Rate limit
    return results
