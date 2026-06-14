"""gps_component — Streamlit Cloud uyumlu HTML5 Geolocation.

streamlit-js-eval paketi kullanır (sandboxing-safe, production-ready).
İç yapı: get_geolocation() → window.parent.postMessage → Streamlit backend
"""
import streamlit as st

try:
    from streamlit_js_eval import get_geolocation
    _HAS_JS_EVAL = True
except ImportError:
    _HAS_JS_EVAL = False


def gps_button(label: str = "📍 Konumumu Al", key: str = "default"):
    """GPS butonu. Basıldığında browser konum izni ister.

    Not: streamlit-js-eval'in get_geolocation()'u doğrudan çalışır,
    biz sadece label gösterimi için burada info veriyoruz.
    """
    if not _HAS_JS_EVAL:
        st.warning("⚠️ streamlit-js-eval paketi yüklü değil. `pip install streamlit-js-eval` gerekli.")
    # Kullanıcıya ne yapacağını söyle
    st.info("📍 Aşağıdaki butona bas → tarayıcı konum izni soracak → otomatik dolar.")


def get_gps() -> tuple[float, float, int] | None:
    """GPS koordinatı al. (lat, lon, accuracy) veya None.

    İlk çağrıldığında browser konum izni dialog'u gösterir.
    Sonraki çağrılarda cached değer döner (key değişmediği sürece).
    """
    if not _HAS_JS_EVAL:
        return None
    try:
        result = get_geolocation(component_key="gps_unique_key_42")
        # result: dict {'coords': {'latitude': ..., 'longitude': ..., 'accuracy': ...}}
        # veya None (henüz alınmadıysa / reddedildiyse)
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
    except Exception as e:
        return None
