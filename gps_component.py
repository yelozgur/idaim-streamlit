"""gps_component — Streamlit Cloud uyumlu HTML5 Geolocation.

JS tarafı:
  - Butona tıklayınca navigator.geolocation.getCurrentPosition()
  - Konum alındı → URL'e ?gps_lat=...&gps_lon=... ekle
  - window.location.href ile sayfayı yenile (Streamlit rerun tetikler)
  - 1.5s spinner göster ki kullanıcı "Yükleniyor..." görsün

Streamlit tarafı:
  - get_gps_from_query() → URL'den koordinatı oku
  - session_state'e yaz → harita pin belirir
  - clear_gps_query() ile URL temizle
"""
import streamlit as st
import streamlit.components.v1 as components


_HTML_TEMPLATE = """
<style>
  #gps-wrap {{
    margin: 4px 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  #gps-btn {{
    width: 100%;
    min-height: 60px;
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
  #gps-btn:disabled {{
    background: #9aa0a6;
    cursor: not-allowed;
  }}
  #gps-status {{
    margin-top: 6px;
    padding: 6px 10px;
    font-size: 13px;
    border-radius: 8px;
    text-align: center;
    display: none;
  }}
  #gps-status.loading {{
    display: block;
    background: #fff3cd;
    color: #856404;
  }}
  #gps-status.success {{
    display: block;
    background: #d4edda;
    color: #155724;
  }}
  #gps-status.error {{
    display: block;
    background: #f8d7da;
    color: #721c24;
  }}
  .acc-badge {{
    display: inline-block;
    margin-left: 4px;
    padding: 2px 6px;
    font-size: 10px;
    background: rgba(255,255,255,0.3);
    border-radius: 8px;
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
        // URL'e yaz + 1.5s sonra reload (Streamlit rerun tetikle)
        const url = new URL(window.location.href);
        url.searchParams.set("gps_lat", lat.toString());
        url.searchParams.set("gps_lon", lon.toString());
        url.searchParams.set("gps_acc", acc.toString());
        btn.textContent = "⏳ Yükleniyor...";
        btn.disabled = true;
        setTimeout(function() {{
          // location.assign ile — history'e yazmaz
          window.location.assign(url.toString());
        }}, 1500);
      }},
      function(err) {{
        btn.textContent = "📍 Konumumu Al";
        btn.disabled = false;
        let msg = "❌ Konum hatası";
        if (err.code === 1) msg = "❌ Konum izni reddedildi. Tarayıcı ayarlarından izin verin.";
        else if (err.code === 2) msg = "❌ GPS sinyali yok. Açık alana çıkıp tekrar deneyin.";
        else if (err.code === 3) msg = "⏱️ Zaman aşımı. Tekrar deneyin.";
        show("error", msg);
      }},
      {{ enableHighAccuracy: true, timeout: 20000, maximumAge: 30000 }}
    );
  }});
}})();
</script>
"""


def gps_button(label: str = "📍 Konumumu Al", key: str = "default"):
    """HTML5 Geolocation butonu. Tıklayınca URL'e konum yazıp sayfa yenilenir."""
    components.html(_HTML_TEMPLATE.format(label=label), height=130)


def get_gps_from_query() -> tuple[float, float] | None:
    """URL query parameters'tan GPS koordinatı al."""
    try:
        lat = st.query_params.get("gps_lat")
        lon = st.query_params.get("gps_lon")
        if lat and lon:
            return (float(lat), float(lon))
    except Exception:
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
    """URL'den GPS query parametrelerini temizle."""
    try:
        if "gps_lat" in st.query_params:
            del st.query_params["gps_lat"]
        if "gps_lon" in st.query_params:
            del st.query_params["gps_lon"]
        if "gps_acc" in st.query_params:
            del st.query_params["gps_acc"]
    except Exception:
        pass
