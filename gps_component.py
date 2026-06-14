"""gps_component — Streamlit Cloud uyumlu HTML5 Geolocation.

Pattern:
  - Gizli st.form GET submit (action="")
  - Buton JS'i: navigator.geolocation → hidden input'lara yaz → form.submit()
  - Streamlit query_params yerine st.form_submit_button tetiklemesi

Avantaj: form.submit() tarayıcıda native, sandboxing bloklamaz.
"""
import streamlit as st
import streamlit.components.v1 as components


_HTML = """
<style>
  #gps-wrap { margin: 4px 0; font-family: -apple-system, sans-serif; }
  #gps-btn {
    width: 100%; min-height: 60px; padding: 16px 24px;
    font-size: 18px; font-weight: 600; color: white;
    background: linear-gradient(135deg, #4285f4, #1a73e8);
    border: none; border-radius: 12px; cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  }
  #gps-btn:active { transform: scale(0.98); }
  #gps-btn:disabled { background: #9aa0a6; cursor: not-allowed; }
  #gps-status {
    margin-top: 6px; padding: 6px 10px; font-size: 13px;
    border-radius: 8px; text-align: center; display: none;
  }
  #gps-status.loading { display: block; background: #fff3cd; color: #856404; }
  #gps-status.success { display: block; background: #d4edda; color: #155724; }
  #gps-status.error   { display: block; background: #f8d7da; color: #721c24; }
  .acc-badge {
    display: inline-block; margin-left: 4px; padding: 2px 6px;
    font-size: 10px; background: rgba(255,255,255,0.3); border-radius: 8px;
  }
</style>
<div id="gps-wrap">
  <button id="gps-btn" type="button">📍 Konumumu Al</button>
  <div id="gps-status"></div>
</div>
<script>
function getLocation() {
  if (!navigator.geolocation) {
    var s = document.getElementById("gps-status");
    s.className = "error"; s.style.display = "block";
    s.innerHTML = "❌ Tarayıcı GPS desteklemiyor";
    return;
  }
  var btn = document.getElementById("gps-btn");
  var status = document.getElementById("gps-status");
  btn.disabled = true;
  btn.textContent = "⏳ Konum alınıyor...";
  status.className = "loading";
  status.style.display = "block";
  status.innerHTML = "📡 GPS sinyali aranıyor...";

  navigator.geolocation.getCurrentPosition(
    function(p) {
      var lat = p.coords.latitude, lon = p.coords.longitude;
      var acc = Math.round(p.coords.accuracy);
      var badge = acc < 50  ? '<span class="acc-badge">✅ Yüksek</span>'
                : acc < 200 ? '<span class="acc-badge">🟢 Orta</span>'
                            : '<span class="acc-badge">🟡 Düşük</span>';
      status.className = "success";
      status.innerHTML = "✅ " + lat.toFixed(5) + ", " + lon.toFixed(5) + " " + badge + " — yükleniyor...";
      btn.textContent = "⏳ Yükleniyor...";
      // URL'e yaz + sayfayı yenile
      var url = new URL(window.location.href);
      url.searchParams.set("gps_lat", lat);
      url.searchParams.set("gps_lon", lon);
      url.searchParams.set("gps_acc", acc);
      window.location.href = url.toString();
    },
    function(e) {
      btn.disabled = false;
      btn.textContent = "📍 Konumumu Al";
      status.className = "error";
      status.style.display = "block";
      var msg = "❌ Konum hatası";
      if (e.code === 1) msg = "❌ Konum izni reddedildi. Tarayıcı ayarlarından izin verin.";
      else if (e.code === 2) msg = "❌ GPS sinyali yok. Açık alana çıkıp tekrar deneyin.";
      else if (e.code === 3) msg = "⏱️ Zaman aşımı. Tekrar deneyin.";
      status.innerHTML = msg;
    },
    { enableHighAccuracy: true, timeout: 20000, maximumAge: 30000 }
  );
}
document.getElementById("gps-btn").addEventListener("click", getLocation);
</script>
"""


def gps_button(label: str = "📍 Konumumu Al", key: str = "default"):
    """HTML5 Geolocation butonu. Tıklayınca URL'e konum yazıp sayfayı yeniler."""
    components.html(_HTML, height=130)


def get_gps_from_query() -> tuple[float, float] | None:
    """URL query parameters'tan GPS koordinatı al."""
    try:
        params = st.query_params
        if "gps_lat" in params and "gps_lon" in params:
            return float(params["gps_lat"]), float(params["gps_lon"])
    except Exception:
        pass
    return None


def clear_gps_query():
    """URL'den GPS query parametrelerini temizle (rerun sonrası)."""
    try:
        st.query_params.clear()
    except Exception:
        pass
