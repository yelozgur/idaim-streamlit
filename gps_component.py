"""gps_component — Basit ve çalışan GPS.

v36 SADELEŞTIRME: GPS alındığında ekranda büyük bir bilgi kutusu göster,
kullanıcı Manuel input'a yazsın veya kopyalasın. Harita refresh yok.

Neden: postMessage, location.replace, query param — hepsi CSP/sandboxing
tarafından bloklandı. Manuel input yeterli, haritayı en sona bıraktık.
"""
import streamlit as st


def gps_button(label: str = "📍 Konumumu Al", key: str = "default", height: int = 130):
    """GPS bilgilendirme placeholder (basit, CSP-safe)."""
    if not _HAS_JS_EVAL:
        # streamlit-js-eval yüklüyse gerçek GPS butonu göster (cache'li çalışır)
        st.info("👇 Butona bas → tarayıcı konum izni soracak → 'Konum alındı' mesajı çıkacak. "
                "Sonra sayfayı yenile ve Manuel input'a yaz.")
    else:
        st.info("👇 Aşağıdaki 'Konumumu Al' butonuna bas → izin ver → Manuel input'a yaz.")


try:
    from streamlit_js_eval import get_geolocation as _sj_get_geolocation
    _HAS_JS_EVAL = True
except ImportError:
    _HAS_JS_EVAL = False


def get_gps() -> tuple[float, float, int] | None:
    """streamlit-js-eval ile GPS al. Başarısız olursa None döner.

    Kullanıcı None dönerse Manuel input'a yazabilir.
    """
    if not _HAS_JS_EVAL:
        return None
    try:
        # Sabit key — aynı component, cache'li çalışır
        result = _sj_get_geolocation(component_key="gps_v36_key")
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


# ============== Geriye dönük uyumluluk ==============
def get_gps_from_query():
    return None


def get_gps_from_postmessage():
    return None


def clear_gps_query():
    pass


def clear_gps_payload():
    pass


def render_gps_fallback_button():
    """Yedek bilgilendirme."""
    st.info("💡 Manuel olarak Lat/Lon gir veya GPS butonuna bas (varsa).")
