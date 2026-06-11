"""gps_component — Streamlit Cloud uyumlu, sadece yardımcı.

Not: İlk versiyonda custom HTML5 Geolocation component vardı ama
Streamlit Cloud'da path resolution sorunu çıkardı. Şimdilik GPS
özelliği client-side basit JS ile sağlanıyor, Streamlit rerun'unda
query parameter veya session_state üzerinden değer alınır.
"""
import streamlit as st
import streamlit.components.v1 as components


_HTML_TEMPLATE = """
<style>
  #gps-wrap {{
    margin: 8px 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  #gps-btn {{
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
  }}
  #gps-btn:active {{ transform: scale(0.98); }}
  #gps-btn:disabled {{ background: #9aa0a6; cursor: not-allowed; }}
  #gps-status {{
    margin-top: 8px;
    padding: 8px 12px;
    font-size: 14px;
    border-radius: 8px;
    text-align: center;
    display: none;
  }}
  #gps-status.loading {{ display: block; background: #fff3cd; color: #856404; }}
  #gps-status.success {{ display: block; background: #d4edda; color: #155724; }}
  #gps-status.error   {{ display: block; background: #f8d7da; color: #721c24; }}
  .acc-badge {{
    display: inline-block;
    margin-left: 6px;
    padding: 2px 8px;
    font-size: 11px;
    background: rgba(255,255,255,0.3);
    border-radius: 10px;
  }}
</style>
<div id="gps-wrap">
  <button id="gps-btn" type="button">{label}</button>
  <div id="gps-status"></div>
</div>
<script>
(function() {{
  const btn = document.getElementById("gps-btn");
  const status = document.getElementById("gps-status");
  function show(cls, msg) {{
    status.className = cls;
    status.innerHTML = msg;
  }}
  btn.addEventListener("click", function() {{
    if (!navigator.geolocation) {{
      show("error", "❌ Tarayıcı GPS desteklemiyor");
      return;
    }}
    btn.disabled = true;
    btn.textContent = "⏳ Konum alınıyor...";
    show("loading", "📡 GPS sinyali aranıyor...");
    navigator.geolocation.getCurrentPosition(
      function(pos) {{
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        const acc = Math.round(pos.coords.accuracy);
        const badge = acc < 50 ? '<span class="acc-badge">✅ Yüksek</span>'
                  : acc < 200 ? '<span class="acc-badge">🟢 Orta</span>'
                  : '<span class="acc-badge">🟡 Düşük</span>';
        show("success", "✅ " + lat.toFixed(5) + ", " + lon.toFixed(5) + " " + badge);
        btn.textContent = "✅ Konum Alındı";
        btn.disabled = false;
        // Session state yerine URL query (Streamlit rerun sonrası okunur)
        const url = new URL(window.location);
        url.searchParams.set("gps_lat", lat);
        url.searchParams.set("gps_lon", lon);
        url.searchParams.set("gps_acc", acc);
        // Form submit simülasyonu (form varsa) veya session storage
        try {{
          sessionStorage.setItem("gps_lat", lat);
          sessionStorage.setItem("gps_lon", lon);
          sessionStorage.setItem("gps_acc", acc);
        }} catch(e) {{}}
      }},
      function(err) {{
        btn.textContent = "📍 Konumumu Al";
        btn.disabled = false;
        let msg = "❌ Konum hatası";
        if (err.code === 1) msg = "❌ Konum izni reddedildi (tarayıcı ayarlarından izin verin)";
        else if (err.code === 2) msg = "❌ GPS sinyali yok (açık alana çıkın)";
        else if (err.code === 3) msg = "⏱️ Zaman aşımı (tekrar deneyin)";
        show("error", msg);
      }},
      {{ enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }}
    );
  }});
}})();
</script>
"""


def gps_button(label: str = "📍 Konumumu Al", key: str = "default"):
    """HTML5 Geolocation butonu gösterir. Konum alındıktan sonra
    kullanıcının formu doldurup submit etmesi gerekir (session storage
    üzerinden değer korunur)."""
    components.html(_HTML_TEMPLATE.format(label=label), height=130)


def get_gps_from_query() -> tuple[float, float] | None:
    """URL query parameters'ten GPS koordinatı al (Streamlit rerun sonrası).

    Returns:
        (lat, lon) tuple veya None
    """
    try:
        lat = st.query_params.get("gps_lat")
        lon = st.query_params.get("gps_lon")
        if lat and lon:
            return (float(lat), float(lon))
    except Exception:
        # Eski Streamlit API
        try:
            params = st.experimental_get_query_params()
            lat = params.get("gps_lat", [None])[0]
            lon = params.get("gps_lon", [None])[0]
            if lat and lon:
                return (float(lat), float(lon))
        except Exception:
            pass
    return None


def clear_gps_query():
    """Query parameters'ten GPS değerlerini temizle."""
    try:
        if "gps_lat" in st.query_params:
            del st.query_params["gps_lat"]
        if "gps_lon" in st.query_params:
            del st.query_params["gps_lon"]
        if "gps_acc" in st.query_params:
            del st.query_params["gps_acc"]
    except Exception:
        pass
