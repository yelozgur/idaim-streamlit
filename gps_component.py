"""gps_component — Streamlit Cloud uyumlu HTML5 Geolocation (JS → input → Streamlit).

JS tarafı:
  - Butona tıklayınca navigator.geolocation.getCurrentPosition()
  - Koordinat gelince, Streamlit'in Manuel Lat/Lon input'una yazar
  - Native 'change' event dispatch eder → Streamlit otomatik rerun
  - location.assign/redirect YOK, sandbox sorunları YOK

Streamlit tarafı:
  - Manuel number_input zaten render ediyor, on_change doğal rerun
  - JS input.value = lat + dispatchEvent(new Event('change'))

Avantaj: GPS ve Manuel AYNI INPUT'u paylaşıyor, tek source of truth.
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
  // Streamlit input key'leri buraya yazılır (Streamlit tarafında render edilir)
  const LAT_INPUT_ID = "{lat_id}";
  const LON_INPUT_ID = "{lon_id}";

  function show(cls, msg) {{
    status.className = cls;
    status.innerHTML = msg;
  }}

  function findInput(id) {{
    // Streamlit input'unun gerçek DOM id'si: "st-key-<key>" veya <key>
    // Önce exact id dene, sonra key-based selector
    let el = document.getElementById(id);
    if (el) return el;
    // Streamlit input selector
    el = document.querySelector(`input[aria-labelledby*="${{id}}"]`);
    if (el) return el;
    // Son çare: tüm input'ları dene, label'a göre eşle
    return null;
  }}

  function setInputValue(el, value) {{
    // React/Streamlit input'larını güncellemek için native setter kullan
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value'
    ).set;
    nativeInputValueSetter.call(el, value);
    // Birden çok event tetikle (Streamlit hangisini dinliyor bilinmez)
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    el.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}));
    el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
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
        show("success", "✅ " + lat.toFixed(5) + ", " + lon.toFixed(5) + " " + badge + " — uygulanıyor...");
        btn.textContent = "✅ Konum Alındı";
        btn.disabled = true;  // bir daha basmasın

        // Streamlit Manuel input'larına yaz
        const latEl = findInput(LAT_INPUT_ID);
        const lonEl = findInput(LON_INPUT_ID);
        if (latEl && lonEl) {{
          setInputValue(latEl, lat.toString());
          setInputValue(lonEl, lon.toString());
          // Streamlit change event'i yakalayıp rerun yapar
        }} else {{
          show("error", "❌ Manuel input bulunamadı (LAT_INPUT_ID=" + LAT_INPUT_ID + ")");
          btn.disabled = false;
          btn.textContent = "📍 Konumumu Al";
        }}
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


def gps_button(label: str = "📍 Konumumu Al", key: str = "default",
              lat_input_key: str = "default_lat", lon_input_key: str = "default_lon"):
    """HTML5 Geolocation butonu. JS, Manuel input'lara koordinat yazıp change event tetikler.

    Args:
        label: Buton metni
        key: Benzersiz key
        lat_input_key: Manuel Lat input'unun Streamlit key'i (DOM ID)
        lon_input_key: Manuel Lon input'unun Streamlit key'i
    """
    # Streamlit input key'leri DOM ID olarak kullanılır (veya "st-key-..." prefix)
    # En güvenli: st.text_input key = "my_lat" → DOM'da input#my_lat olur
    html = _HTML_TEMPLATE.format(
        label=label,
        lat_id=lat_input_key,
        lon_id=lon_input_key,
    )
    components.html(html, height=140)


def get_gps_from_query() -> tuple[float, float] | None:
    """URL query parameters'tan GPS koordinatı al (artık kullanılmıyor, manuel callback tercih)."""
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
    """URL'den GPS query parametrelerini temizle (backward compat)."""
    try:
        if "gps_lat" in st.query_params:
            del st.query_params["gps_lat"]
        if "gps_lon" in st.query_params:
            del st.query_params["gps_lon"]
        if "gps_acc" in st.query_params:
            del st.query_params["gps_acc"]
    except Exception:
        pass
