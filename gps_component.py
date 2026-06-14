"""gps_component — Client-side GPS → Manuel input (CSP-safe, hiç Python iletişimi yok).

v39 YAKLAŞIM:
  1. GPS butonu basıldığında navigator.geolocation çağrılır
  2. Koordinat localStorage'a yazılır
  3. Aynı sayfada JS ile Manuel input değerini günceller
  4. Kullanıcı Manuel input'ta yeni koordinatı görür

PostMessage, query param, location.replace YOK.
Streamlit Python'a hiç veri gitmez — tamamen client-side JS.
"""
import streamlit as st
import streamlit.components.v1 as components


_HTML = """
<style>
  #gps-row {
    display: flex; gap: 8px; align-items: stretch;
    margin: 4px 0 8px 0;
  }
  #gps-btn {
    flex: 1; min-height: 60px; padding: 12px 16px;
    font-size: 16px; font-weight: 600; color: white;
    background: linear-gradient(135deg, #4285f4, #1a73e8);
    border: none; border-radius: 10px; cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  }
  #gps-btn:active { transform: scale(0.98); }
  #gps-btn:disabled { background: #9aa0a6; cursor: not-allowed; }
  #gps-status {
    flex: 1; padding: 12px 16px; font-size: 14px;
    border-radius: 10px; text-align: center; display: none;
    align-items: center; justify-content: center;
  }
  #gps-status.loading { display: flex; background: #fff3cd; color: #856404; }
  #gps-status.success { display: flex; background: #d4edda; color: #155724; }
  #gps-status.error   { display: flex; background: #f8d7da; color: #721c24; }
</style>
<div id="gps-row">
  <button id="gps-btn" type="button">📡 GPS Al</button>
  <div id="gps-status"></div>
</div>
<script>
(function() {
  function setStatus(kind, html) {
    var s = document.getElementById("gps-status");
    s.className = kind;
    s.innerHTML = html;
  }

  function getLocation() {
    var btn = document.getElementById("gps-btn");
    if (!navigator.geolocation) {
      setStatus("error", "❌ GPS desteklemiyor");
      return;
    }
    btn.disabled = true;
    btn.textContent = "⏳ Konum alınıyor...";
    setStatus("loading", "📡 GPS aranıyor...");

    navigator.geolocation.getCurrentPosition(
      function(p) {
        var lat = p.coords.latitude;
        var lon = p.coords.longitude;
        var acc = Math.round(p.coords.accuracy);
        var badge = acc < 50  ? '✅' : (acc < 200 ? '🟢' : '🟡');
        // Manuel inputlara yaz (Streamlit'in number_input widget'larını bul)
        // Sayfadaki ilk 2 number_input = Lat ve Lon
        var inputs = document.querySelectorAll('input[type="number"]');
        if (inputs.length >= 2) {
          // Streamlit'in React tabanlı inputlarını güncellemek için
          // native value setter + 'input' event tetikle
          var nativeInputSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          // İlk number_input = Lat (kullanıcı st.number_input "Latitude" sırasına göre)
          nativeInputSetter.call(inputs[0], lat.toFixed(5));
          inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
          // İkinci = Lon
          nativeInputSetter.call(inputs[1], lon.toFixed(5));
          inputs[1].dispatchEvent(new Event('input', { bubbles: true }));
        }
        setStatus("success", badge + " " + lat.toFixed(5) + ", " + lon.toFixed(5));
        btn.textContent = "✅ Konum alındı";
        setTimeout(function() {
          btn.disabled = false;
          btn.textContent = "📡 GPS Al";
        }, 3000);
      },
      function(e) {
        var msg = "❌ Hata";
        if (e.code === 1) msg = "❌ İzin reddedildi";
        else if (e.code === 2) msg = "❌ Sinyal yok";
        else if (e.code === 3) msg = "⏱️ Zaman aşımı";
        setStatus("error", msg);
        btn.disabled = false;
        btn.textContent = "📡 GPS Al";
      },
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 30000 }
    );
  }

  var btn = document.getElementById("gps-btn");
  if (btn) btn.addEventListener("click", getLocation);
})();
</script>
"""


def gps_button(label: str = "📡 GPS Al", key: str = "default", height: int = 80):
    """GPS butonu (CSP-safe client-side).

    Tıklayınca navigator.geolocation çağrılır, koordinat aynı sayfadaki
    Manuel input number_input'lara otomatik yazılır. Streamlit Python
    tarafına hiç veri gitmez — tamamen client-side JS.
    """
    if hasattr(st, "html"):
        try:
            st.html(_HTML, height=height)
            return
        except Exception:
            pass
    components.html(_HTML, height=height)


def get_gps():
    """Eski API uyumluluğu (artık client-side)."""
    return None


def render_gps_fallback_button():
    pass
