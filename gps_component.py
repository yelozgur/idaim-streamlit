"""gps_component — GPS location capture (single file module, v0.5 approach).

Uses streamlit_js_eval (3rd-party package) instead of st.html + inline JS.

Why not st.html?
  st.html uses st.markdown(unsafe_allow_html=True) internally. <script>
  tags inserted via innerHTML are NOT executed by the browser (DOM rule).
  Result: button renders but click does nothing. Confirmed in v0.6 testing.

Why streamlit_js_eval?
  It uses st.components.v1.declare_component internally, which renders
  an iframe with proper script execution. The iframe calls
  navigator.geolocation, the result is sent back to Streamlit via
  Streamlit's setComponentValue mechanism. This works on Streamlit Cloud
  (sometimes blocked by CSP, but at least the call is made and the user
  sees an actionable error — unlike st.html's silent failure).

Caveat:
  First call: browser asks for permission. After "Allow", subsequent
  calls return coords. CSP sandboxing can block the iframe on Streamlit
  Cloud (raises an error in browser console) — in that case the user
  gets None back and falls back to manual lat/lon input.

Usage:
    from gps_component import gps_button
    result = gps_button(key="init_loc_gps")
    if result:
        lat, lon = result
        # use coords
"""
import streamlit as st

try:
    from streamlit_js_eval import get_geolocation
    _HAS_JS_EVAL = True
except ImportError:
    _HAS_JS_EVAL = False


def gps_button(key: str = "default", label: str = "📍 Get my location") -> tuple[float, float] | None:
    """Render GPS button via streamlit_js_eval. Returns (lat, lon) when available.

    Returns None if the package is missing, the user hasn't granted
    permission, CSP blocked the iframe, or coords are otherwise unavailable.
    """
    if not _HAS_JS_EVAL:
        st.warning("⚠️ streamlit-js-eval not installed. Add `streamlit-js-eval` to requirements.txt.")
        return None

    try:
        result = get_geolocation(component_key=f"gps_{key}")
        if not result or not isinstance(result, dict):
            # First call — user needs to click and grant permission
            st.info("👇 Click the location button, then 'Allow' in your browser. After first grant, coords come back automatically.")
            return None

        coords = result.get("coords") if isinstance(result.get("coords"), dict) else None
        if not coords:
            return None

        lat = coords.get("latitude")
        lon = coords.get("longitude")
        if lat is None or lon is None:
            return None

        return (float(lat), float(lon))
    except Exception:
        return None
