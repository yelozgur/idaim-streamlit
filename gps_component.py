"""gps_component — Streamlit Cloud uyumlu HTML5 Geolocation (form GET submit).

JS tarafı:
  - Butona tıklayınca navigator.geolocation.getCurrentPosition()
  - Koordinat gelince GIZLI bir HTML <form>'a yazar
  - Form action="" method="GET" → aynı sayfaya ?gps_lat=... gönderir
  - Browser native navigation → sayfa yenilenir, Streamlit query_params okur
  - location.assign/redirect YOK (sandbox sorunları yok)

Streamlit tarafı:
  - get_gps_from_query() → session_state günceller
  - st.rerun() → harita pin belirir
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
  /* Form: minimal, neredeyse görünmez */
  #gps-form {{
    margin-top: 8px;
    padding: 0;
    border: 0;
  }}
  #gps-form input[type=hidden] {{
    display: none;
  }}
</style>
<div id="gps-wrap">
  <button id="gps-btn" type="button">{label}</button>
  <div id="gps-status"></div>
  <form id="gps-form" method="GET" action="">
    <input type="hidden" id="gps-lat" name="gps_lat" value="" />
    <input type="hidden" id="gps-lon" name="gps_lon" value="" />
    <button type="submit" id="gps-submit" style="display:none">Submit</button>
  </form>
</div>
<script>
(function() {{
  const btn = document.getElementById("gps-btn");
  const status = document.getElementById("gps-status");
  const form = document.getElementById("gps-form");
  const latInput = document.getElementById("gps-lat");
  const lonInput = document.getElementById("gps-lon");
  const submitBtn = document.getElementById("gps-submit");

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
        show("success", "✅ " + lat.toFixed(5) + ", " + lon.toFixed(5) + " " + badge + " — yükleniyor...");
        btn.textContent = "⏳ Yükleniyor...";
        btn.disabled = true;

        // Hidden input'a yaz
        latInput.value = lat.toString();
        lonInput.value = lon.toString();

        // 800ms sonra form submit (browser native navigation, sandbox-safe)
        setTimeout(function() {{
          // Form action="" → aynı sayfaya GET, ?gps_lat=... eklenir
          // submit() programmatic, sandboxing block etmez (form action)
          form.submit();
        }}, 800);
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
    """HTML5 Geolocation butonu. Form GET submit ile ?gps_lat=... yazar."""
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
    """URL'den GPS query parametrelerini temizle (rerun sonrası)."""
    try:
        if "gps_lat" in st.query_params:
            del st.query_params["gps_lat"]
        if "gps_lon" in st.query_params:
            del st.query_params["gps_lon"]
        if "gps_acc" in st.query_params:
            del st.query_params["gps_acc"]
    except Exception:
        pass
