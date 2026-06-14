"""gps_component — streamlit-js-eval ile (v27 sürümü, çalışıyordu).

CSP: streamlit-js-eval 'Function' kullanıyor ama sabit key + tarayıcı cache'li
izin ile çalışıyor. Unique key her basışta yeni component oluşturuyor
ve Function'ı tetikliyordu → v34'te CSP'ye takıldı.

v40: SABIT key (v27 pattern) — Function sadece bir kez çağrılıyor.
"""
import streamlit as st

try:
    from streamlit_js_eval import get_geolocation
    _HAS_JS_EVAL = True
except ImportError:
    _HAS_JS_EVAL = False


def gps_button(label: str = "📡 GPS Al", key: str = "default", height: int = 130):
    """GPS placeholder butonu (info)."""
    if not _HAS_JS_EVAL:
        st.warning("⚠️ streamlit-js-eval paketi yüklü değil.")
    st.caption("👇 Aşağıdaki 'Konumumu Al' butonuna bas → tarayıcı konum izni soracak → otomatik dolar.")


def get_gps():
    """streamlit-js-eval ile GPS al. Sabit key — bir kez init, cache'li çalışır.

    v27'de bu pattern çalıştı: 35.22124, 33.37500 → hücre #28412, 0.18 km.
    """
    if not _HAS_JS_EVAL:
        return None
    try:
        # SABİT key — v27'nin çalışan pattern'i
        result = get_geolocation(component_key="gps_fixed_key_v40")
        if not result or not isinstance(result, dict):
            return None
        coords = result.get("coords")
        if not coords or not isinstance(coords, dict):
            return None
        lat = coords.get("latitude")
        lon = coords.get("longitude")
        acc = coords.get("accuracy", 0)
        if lat is None or lon is None:
            return None
        return float(lat), float(lon), int(acc or 0)
    except Exception:
        return None


def render_gps_fallback_button():
    pass
