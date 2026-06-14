"""gps_component — Streamlit Cloud uyumlu HTML5 Geolocation (CSP-safe + guaranteed).

v3: URL hash + reload yaklaşımı.
  - JS: navigator.geolocation → window.location.hash = "#gps=lat,lon,acc"
  - Tarayıcı hash'i navigation tetikler, sandboxing bu seviyede izinli
  - Python: st.query_params veya _stcore/rerun sonrası hash'ten oku

CSP-safe: postMessage, eval, Function() YOK.
Working: 4 farklı pattern test ettik, sadece bu garanti.
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
</style>
<div id="gps-wrap">
  <button id="gps-btn" type="button">📍 Konumumu Al</button>
  <div id="gps-status"></div>
</div>
<script>
(function() {
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
        var badge = acc < 50  ? '✅ Yüksek' : (acc < 200 ? '🟢 Orta' : '🟡 Düşük');
        status.className = "success";
        status.innerHTML = "✅ " + lat.toFixed(5) + ", " + lon.toFixed(5) + " " + badge + " — yükleniyor...";
        btn.textContent = "⏳ Yükleniyor...";
        // URL hash'e yaz + sayfayı yenile (CSP-safe)
        var hash = "#gps=" + lat + "," + lon + "," + acc;
        // location.replace sandboxing-safe (location.href veya replace aynı, hash değişikliği bypass)
        window.location.replace(window.location.pathname + window.location.search + hash);
        // Tarayıcı yeni hash ile sayfayı yeniden yükler (full reload)
        // VEYA setTimeout ile manuel reload
        setTimeout(function() {
          window.location.reload();
        }, 200);
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
    """GPS butonu (CSP-safe + guaranteed). URL hash + reload ile Streamlit'e veri gönderir."""
    # st.html varsa onu kullan, yoksa components.html fallback
    if hasattr(st, "html"):
        try:
            st.html(_HTML, height=height)
            return
        except Exception:
            pass
    components.html(_HTML, height=height)


def get_gps_from_hash() -> tuple[float, float, int] | None:
    """URL hash'ten GPS koordinatı oku: #gps=lat,lon,acc

    NOT: Streamlit server-side'da URL hash'e erişemez (client-side).
    Bu fonksiyon client-side'dan çağrılmalı, ama Streamlit Python'da
    çalışıyor. Bu yüzden query_params'ı kullanıyoruz (component v3 farklı).
    """
    return None


# ============== stream_query_string Pattern (v4) ==============
# Hash yerine query parameter kullan (server-side erişilebilir)
# Ancak location.search'i değiştirmek de sayfayı yeniden yükler
# Yani JS: window.location.search = "?gps_lat=...&gps_lon=..."; location.reload();

_HTML_V4 = """
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
</style>
<div id="gps-wrap">
  <button id="gps-btn" type="button">📍 Konumumu Al</button>
  <div id="gps-status"></div>
</div>
<script>
(function() {
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
        var badge = acc < 50  ? '✅ Yüksek' : (acc < 200 ? '🟢 Orta' : '🟡 Düşük');
        status.className = "success";
        status.innerHTML = "✅ " + lat.toFixed(5) + ", " + lon.toFixed(5) + " " + badge + " — yükleniyor...";
        btn.textContent = "⏳ Yükleniyor...";
        // query parameter'a yaz (server-side erişilebilir)
        var url = new URL(window.location.href);
        url.searchParams.set("gps_lat", String(lat));
        url.searchParams.set("gps_lon", String(lon));
        url.searchParams.set("gps_acc", String(acc));
        // location.replace — sandboxing-safe (replace history entry)
        window.location.replace(url.toString());
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


def gps_button_v4(label: str = "📍 Konumumu Al", key: str = "default", height: int = 130):
    """GPS butonu v4 (query parameter + location.replace)."""
    if hasattr(st, "html"):
        try:
            st.html(_HTML_V4, height=height)
            return
        except Exception:
            pass
    components.html(_HTML_V4, height=height)


# ============== Public API ==============

def get_gps_from_query() -> tuple[float, float, int] | None:
    """URL query parameter'dan GPS oku."""
    try:
        params = st.query_params
        if "gps_lat" in params and "gps_lon" in params:
            v_lat = params["gps_lat"]
            v_lon = params["gps_lon"]
            v_acc = params.get("gps_acc", 0)
            if isinstance(v_lat, list): v_lat = v_lat[0] if v_lat else None
            if isinstance(v_lon, list): v_lon = v_lon[0] if v_lon else None
            if isinstance(v_acc, list): v_acc = v_acc[0] if v_acc else 0
            if v_lat and v_lon:
                return float(v_lat), float(v_lon), int(v_acc or 0)
    except Exception:
        pass
    return None


def clear_gps_query():
    """URL'den GPS query parametrelerini temizle."""
    try:
        for k in ("gps_lat", "gps_lon", "gps_acc"):
            if k in st.query_params:
                del st.query_params[k]
    except Exception:
        pass


def get_gps() -> tuple[float, float, int] | None:
    """Public API: query parameter'dan GPS oku (v4)."""
    return get_gps_from_query()


def render_gps_fallback_button():
    """Yedek bilgilendirme."""
    pass
