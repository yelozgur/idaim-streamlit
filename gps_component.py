"""gps_component — Streamlit Cloud uyumlu HTML5 Geolocation (CSP-safe).

streamlit-js-eval CSP'ye takılıyor ('unsafe-eval' yasak).
Saf HTML5 navigator.geolocation + st.html + postMessage kullanıyoruz.
postMessage Streamlit'in kendi mesajlaşma protokolü (CSP'ye takılmaz).
"""
import json
import time
import streamlit as st
import streamlit.components.v1 as components


# ============== St.html + Components HTML (CSP-safe) ==============
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
(function() {
  // CSP-safe: eval/Function() kullanmaz
  function sendToStreamlit(data) {
    // Streamlit setComponentValue protokolü (postMessage)
    window.parent.postMessage(
      { isStreamlitMessage: true, type: "streamlit:setComponentValue",
        value: data, key: "gps_payload" },
      "*"
    );
  }

  function getLocation() {
    var btn = document.getElementById("gps-btn");
    var status = document.getElementById("gps-status");
    if (!navigator.geolocation) {
      status.className = "error";
      status.style.display = "block";
      status.innerHTML = "❌ Tarayıcı GPS desteklemiyor";
      return;
    }
    btn.disabled = true;
    btn.textContent = "⏳ Konum alınıyor...";
    status.className = "loading";
    status.style.display = "block";
    status.innerHTML = "📡 GPS sinyali aranıyor...";

    navigator.geolocation.getCurrentPosition(
      function(p) {
        var lat = p.coords.latitude, lon = p.coords.longitude, acc = Math.round(p.coords.accuracy);
        var badge = acc < 50  ? '<span class="acc-badge">✅ Yüksek</span>'
                  : acc < 200 ? '<span class="acc-badge">🟢 Orta</span>'
                              : '<span class="acc-badge">🟡 Düşük</span>';
        status.className = "success";
        status.innerHTML = "✅ " + lat.toFixed(5) + ", " + lon.toFixed(5) + " " + badge;
        btn.textContent = "✅ Konum alındı";
        // Streamlit'e gönder
        sendToStreamlit({ lat: lat, lon: lon, acc: acc, ts: Date.now() });
      },
      function(e) {
        var btn2 = document.getElementById("gps-btn");
        btn2.disabled = false;
        btn2.textContent = "📍 Konumumu Al";
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

  var btn = document.getElementById("gps-btn");
  if (btn) btn.addEventListener("click", getLocation);
})();
</script>
"""


def gps_button(label: str = "📍 Konumumu Al", key: str = "default", height: int = 130):
    """GPS butonu. CSP-safe: postMessage ile Streamlit'e veri gönderir.

    Streamlit tarafında `st.components.v1.html` veya yeni `st.html` kullanılır.
    """
    if hasattr(st, "html"):
        try:
            st.html(_HTML, height=height)
            return
        except Exception:
            pass
    # Fallback
    components.html(_HTML, height=height)


# ============== GPS Koordinat Okuma (postMessage) ==============

def get_gps_from_postmessage() -> tuple[float, float, int] | None:
    """Sayfa render edildiğinde browser'dan gelen postMessage'ı kontrol et.

    Streamlit, custom component'ten gelen value'yu `st.session_state["gps_payload"]`
    içine yazar (Streamlit >= 1.32). Biz burada onu okuyoruz.
    """
    try:
        payload = st.session_state.get("gps_payload")
        if not payload or not isinstance(payload, dict):
            return None
        lat = payload.get("lat")
        lon = payload.get("lon")
        acc = payload.get("acc", 0)
        if lat is None or lon is None:
            return None
        return float(lat), float(lon), int(acc or 0)
    except Exception:
        return None


def clear_gps_payload():
    """GPS payload'ı temizle (tek seferlik işlem)."""
    try:
        if "gps_payload" in st.session_state:
            del st.session_state["gps_payload"]
    except Exception:
        pass


# ============== Eski API (backward compat) ==============

def gps_button_legacy(label: str = "📍 Konumumu Al", key: str = "default"):
    """Eski API uyumluluğu için placeholder."""
    pass


# Alias: eski çağrılar için
get_gps = get_gps_from_postmessage


def render_gps_fallback_button():
    """Yedek GPS bilgilendirmesi (artık gerek yok, ana buton CSP-safe)."""
    pass
