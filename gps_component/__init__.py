"""gps_component — Vanilla HTML5 Geolocation, sandbox-safe.

Streamlit Cloud CSP blocks custom components built with declare_component(path=...).
This uses st.html + navigator.geolocation + parent.location.replace (CSP-safe per
Streamlit Cloud memory v27/v36).

Flow:
  1. st.html renders a button + JS code (no Streamlit component).
  2. JS calls navigator.geolocation, on success calls parent.location.replace
     to navigate the Streamlit page to ?gps_lat_X=...&gps_lon_X=...
  3. Streamlit reads query params on rerun, exposes via gps_button().

CSP-safe: no eval, no Function(), no postMessage to non-Streamlit origins.
parent.location.replace is the only way to push URL changes to Streamlit when
iframe sandboxing blocks window.location.replace.
"""
import streamlit as st


def _render_gps_html(key: str) -> str:
    """Return the HTML/JS for the GPS button."""
    return f"""
<div id="gps-wrap-{key}">
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
  -webkit-tap-highlight-color: transparent;
">
Get my location
</button>
<div id="gps-status-{key}" style="margin-top:8px;padding:8px 12px;font-size:14px;border-radius:8px;text-align:center;display:none"></div>
</div>
<script>
(function() {{
  const btn = document.getElementById('gps-btn-{key}');
  const status = document.getElementById('gps-status-{key}');
  if (!btn) {{ return; }}

  // Existing query params
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
        // Update URL via parent.location.replace (CSP-safe, works through iframe sandboxing)
        const newSearch = new URLSearchParams(window.location.search);
        newSearch.set('gps_lat_{key}', lat.toString());
        newSearch.set('gps_lon_{key}', lon.toString());
        const newUrl = window.location.pathname + '?' + newSearch.toString() + window.location.hash;
        try {{
          window.parent.location.replace(newUrl);
        }} catch (e) {{
          try {{
            window.location.replace(newUrl);
          }} catch (e2) {{
            status.textContent = 'Could not update location. Please copy the URL or refresh manually.';
          }}
        }}
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
    st.html(_render_gps_html(key))

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
