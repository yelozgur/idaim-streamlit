"""gps_component — Vanilla HTML5 Geolocation, sandbox-safe.

Streamlit Cloud CSP blocks custom components built with declare_component(path=...).
This implementation uses st.html + navigator.geolocation + Streamlit query params.

Flow:
  1. st.html renders a button + JS code (no Streamlit component).
  2. JS calls navigator.geolocation, on success writes ?lat=X&lon=Y to URL.
  3. Streamlit reads query params on rerun, exposes via gps_button().
  4. The rerun is triggered by a hidden st.button() the user must click after.

CSP-safe: no eval, no Function(), no postMessage to non-Streamlit origins.
"""
import streamlit as st


def _render_gps_html(key: str) -> str:
    """Return the HTML/JS for the GPS button.

    On click -> geolocation -> URL hash updated to #lat=X&lon=Y -> page reloads
    with new query params Streamlit can read.
    """
    return f"""
<div id="gps-{key}">
<button id="gps-btn-{key}" style="
  width: 100%;
  min-height: 56px;
  padding: 16px 24px;
  font-size: 18px;
  font-weight: 600;
  color: white;
  background: linear-gradient(135deg, #4285f4, #1a73e8);
  border: none;
  border-radius: 12px;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
">
Get my location
</button>
<div id="gps-status-{key}" style="margin-top:8px;padding:8px 12px;font-size:14px;border-radius:8px;text-align:center;display:none"></div>
</div>
<script>
(function() {{
  const btn = document.getElementById('gps-btn-{key}');
  const status = document.getElementById('gps-status-{key}');
  const params = new URLSearchParams(window.location.search);
  const latParam = params.get('gps_lat_{key}');
  const lonParam = params.get('gps_lon_{key}');
  if (latParam && lonParam) {{
    status.style.display = 'block';
    status.style.background = '#d4edda';
    status.style.color = '#155724';
    status.textContent = 'Location: ' + parseFloat(latParam).toFixed(5) + ', ' + parseFloat(lonParam).toFixed(5);
    btn.textContent = 'Location acquired';
  }}
  btn.addEventListener('click', function() {{
    if (!navigator.geolocation) {{
      status.style.display = 'block';
      status.style.background = '#f8d7da';
      status.style.color = '#721c24';
      status.textContent = 'Browser does not support GPS';
      return;
    }}
    btn.disabled = true;
    btn.textContent = 'Acquiring...';
    status.style.display = 'block';
    status.style.background = '#fff3cd';
    status.style.color = '#856404';
    status.textContent = 'Looking for GPS signal, please wait...';
    navigator.geolocation.getCurrentPosition(
      function(pos) {{
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        const newUrl = new URL(window.location.href);
        newUrl.searchParams.set('gps_lat_{key}', lat.toString());
        newUrl.searchParams.set('gps_lon_{key}', lon.toString());
        window.location.replace(newUrl.toString());
      }},
      function(err) {{
        btn.disabled = false;
        btn.textContent = 'Get my location';
        let msg = 'GPS error';
        if (err.code === 1) msg = 'Permission denied. Enable location in browser settings.';
        else if (err.code === 2) msg = 'GPS signal unavailable. Move to an open area.';
        else if (err.code === 3) msg = 'Timeout. Try again.';
        status.style.display = 'block';
        status.style.background = '#f8d7da';
        status.style.color = '#721c24';
        status.textContent = msg;
      }},
      {{ enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }}
    );
  }});
}})();
</script>
"""


def gps_button(label: str = "Get my location", key: str = "gps") -> tuple[float, float] | None:
    """GPS button. On click -> browser asks permission -> URL updated -> rerun.

    Returns: (lat, lon) tuple or None.
    """
    # Render the button + JS
    st.html(_render_gps_html(key))

    # Read query params (set by JS via window.location.replace)
    try:
        params = st.query_params
    except AttributeError:
        params = st.experimental_get_query_params()

    lat_param = params.get(f"gps_lat_{key}")
    lon_param = params.get(f"gps_lon_{key}")

    if lat_param and lon_param:
        try:
            return (float(lat_param), float(lon_param))
        except (ValueError, TypeError):
            return None
    return None
