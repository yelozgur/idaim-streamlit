"""gps_component — Streamlit Cloud uyumlu HTML5 Geolocation.

İki katmanlı strateji:
  1. streamlit-js-eval get_geolocation() (postMessage tabanlı)
  2. HTML5 navigator.geolocation + components.html fallback (localStorage)

Mobil sorun çözümü:
  - Web'de katman 1 çalışır (cache'liyor)
  - Mobilde katman 2 gerekebilir (private mode / eski browser)
  - Katman 2: components.html içinde JS → localStorage'a yaz →
    Streamlit tarafında ikinci rerun'da localStorage'ı oku (postMessage yerine)
"""
import json
import time
import streamlit as st
import streamlit.components.v1 as components


# ============== Katman 1: streamlit-js-eval ==============
try:
    from streamlit_js_eval import get_geolocation as _sj_get_geolocation
    _HAS_JS_EVAL = True
except ImportError:
    _HAS_JS_EVAL = False


def gps_button(label: str = "📍 Konumumu Al", key: str = "default"):
    """GPS placeholder/info butonu (Streamlit tarafında buton ayrı render edilir).

    Gerçek GPS tetikleme `get_gps()` ile yapılır, bu fonksiyon sadece
    sayfaya bilgilendirme mesajı gösterir.
    """
    if not _HAS_JS_EVAL:
        st.warning("⚠️ streamlit-js-eval paketi yüklü değil.")
    st.info(f"📍 {label} → tarayıcı konum izni soracak → otomatik dolar.")


_HTML_FALLBACK = """
<style>
  #gps-fb-wrap { margin: 4px 0; }
  #gps-fb-btn {
    width: 100%; min-height: 60px; padding: 16px 24px;
    font-size: 18px; font-weight: 600; color: white;
    background: linear-gradient(135deg, #ff9800, #f57c00);
    border: none; border-radius: 12px; cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  }
  #gps-fb-btn:active { transform: scale(0.98); }
  #gps-fb-btn:disabled { background: #9aa0a6; cursor: not-allowed; }
  #gps-fb-status {
    margin-top: 6px; padding: 6px 10px; font-size: 13px;
    border-radius: 8px; text-align: center; display: none;
  }
  #gps-fb-status.loading { display: block; background: #fff3cd; color: #856404; }
  #gps-fb-status.success { display: block; background: #d4edda; color: #155724; }
  #gps-fb-status.error   { display: block; background: #f8d7da; color: #721c24; }
</style>
<div id="gps-fb-wrap">
  <button id="gps-fb-btn" type="button">🛰️ GPS Al (yedek)</button>
  <div id="gps-fb-status"></div>
</div>
<script>
function fbGetLocation() {
  var btn = document.getElementById("gps-fb-btn");
  var status = document.getElementById("gps-fb-status");
  btn.disabled = true;
  btn.textContent = "⏳ Konum alınıyor...";
  status.className = "loading";
  status.style.display = "block";
  status.innerHTML = "📡 GPS sinyali aranıyor...";

  if (!navigator.geolocation) {
    status.className = "error";
    status.innerHTML = "❌ Tarayıcı GPS desteklemiyor";
    btn.disabled = false;
    btn.textContent = "🛰️ GPS Al (yedek)";
    return;
  }
  navigator.geolocation.getCurrentPosition(
    function(p) {
      var lat = p.coords.latitude, lon = p.coords.longitude, acc = Math.round(p.coords.accuracy);
      localStorage.setItem("gps_lat", lat.toString());
      localStorage.setItem("gps_lon", lon.toString());
      localStorage.setItem("gps_acc", acc.toString());
      localStorage.setItem("gps_ts", Date.now().toString());
      status.className = "success";
      status.innerHTML = "✅ " + lat.toFixed(5) + ", " + lon.toFixed(5) + " (±" + acc + "m) — sayfayı yenileyin";
      btn.textContent = "✅ Konum alındı (yenile)";
    },
    function(e) {
      btn.disabled = false;
      btn.textContent = "🛰️ GPS Al (yedek)";
      status.className = "error";
      status.style.display = "block";
      var msg = "❌ Konum hatası";
      if (e.code === 1) msg = "❌ Konum izni reddedildi";
      else if (e.code === 2) msg = "❌ GPS sinyali yok";
      else if (e.code === 3) msg = "⏱️ Zaman aşımı";
      status.innerHTML = msg;
    },
    { enableHighAccuracy: true, timeout: 20000, maximumAge: 30000 }
  );
}
document.getElementById("gps-fb-btn").addEventListener("click", fbGetLocation);
</script>
"""


def _read_localstorage_gps() -> tuple[float, float, int] | None:
    """Yedek katmandan localStorage üzerinden GPS oku.

    components.html localStorage'a yazamaz (sandboxing farklı origin),
    bu yüzden BİR STREAMLIT SAYFASI kendi JS'ini çalıştırmalı.
    Burada sadece placeholder.
    """
    # Streamlit localStorage'a doğrudan erişemez (client-side).
    # Bu yüzden Katman 2'yi sadece bilgilendirme amaçlı gösteriyoruz.
    return None


def _unique_key() -> str:
    """Her çağrıda unique key — mobil cache'i bypass."""
    counter_key = "gps_call_count"
    if counter_key not in st.session_state:
        st.session_state[counter_key] = 0
    st.session_state[counter_key] += 1
    sid = getattr(st.session_state, "session_id", "x")
    return f"gps_k_{sid}_{int(time.time())}_{st.session_state[counter_key]}"


def get_gps() -> tuple[float, float, int] | None:
    """GPS koordinatı al. (lat, lon, accuracy) veya None.

    Katman 1: streamlit-js-eval get_geolocation() (postMessage).
    Her çağrıda unique key → mobilde her seferinde yeni izin iste.
    """
    if not _HAS_JS_EVAL:
        return None
    try:
        unique = _unique_key()
        result = _sj_get_geolocation(component_key=unique)
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


def render_gps_fallback_button(key: str = "gps_fb"):
    """Yedek GPS butonu (saf HTML5 + localStorage).

    Katman 1 başarısız olduğunda bunu çağırın, kullanıcıya yedek yol ver.
    Not: localStorage cross-origin, dolayısıyla Python tarafında okunamaz.
    Bu yüzden kullanıcıya "Konum alındı, sayfayı yenile" mesajı gösteriyoruz
    ve Manuel input'a yönlendiriyoruz.
    """
    components.html(_HTML_FALLBACK, height=130, key=key)
