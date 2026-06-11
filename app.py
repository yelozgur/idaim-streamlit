"""app.py — IDAIM Streamlit landing page.

4 sayfa:
  1. 📥 Veri Girişi (Sampling Initiation / Trap Check / Lab Result)
  2. 🗺️ Dashboard (Folium harita + watch list)
  3. 🤖 ML Retrain (per-species, per-district threshold)
  4. 📊 Raporlar (validation metrics)

Auth: basit şifre (Sheets'te users sheet).
"""
import streamlit as st
from datetime import datetime

import config
import sheets_client


# ============== PAGE CONFIG ==============

st.set_page_config(
    page_title=config.APP_TITLE,
    page_icon=config.APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============== AUTH ==============

def login_page():
    """Basit şifre girişi."""
    st.title(f"{config.APP_ICON} {config.APP_TITLE}")
    st.markdown("**Kıbrıs Sivrisinek Vektör İzleme Sistemi** | UNDP-CH")
    st.markdown("---")

    with st.form("login_form"):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader("🔐 Giriş")
            username = st.text_input("Kullanıcı adı")
            password = st.text_input("Şifre", type="password")
            submit = st.form_submit_button("Giriş Yap", use_container_width=True)

    if submit:
        role = sheets_client.verify_user(username, password)
        if role:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.session_state["role"] = role
            sheets_client.update_last_login(username)
            st.success(f"✅ Hoş geldin, {username} (rol: {role})")
            st.rerun()
        else:
            st.error("❌ Kullanıcı adı veya şifre yanlış")

    with st.expander("ℹ️ İlk kez mi giriyorsun?"):
        st.markdown("""
        **Default kullanıcılar (ilk açılışta `users` sheet'ine yazılır):**
        | Kullanıcı | Şifre | Rol |
        |---|---|---|
        | `admin` | `idaim2026` | Admin (her şey) |
        | `field` | `field2026` | Saha ekibi (trap kur/kapat) |
        | `lab` | `lab2026` | Lab teknisyeni (lab sonuç) |

        **Önemli:** İlk girişten sonra şifreleri değiştirin!
        """)


def logout_button():
    """Sidebar'da çıkış butonu."""
    with st.sidebar:
        st.markdown("---")
        st.markdown(f"**👤 {st.session_state.get('username', '?')}** ({st.session_state.get('role', '?')})")
        if st.button("🚪 Çıkış Yap", use_container_width=True):
            for k in ["authenticated", "username", "role"]:
                st.session_state.pop(k, None)
            st.rerun()


# ============== MAIN APP ==============

def main():
    # Auth check
    if not st.session_state.get("authenticated", False):
        login_page()
        return

    logout_button()

    # Sidebar — sheets health
    with st.sidebar:
        st.title(f"{config.APP_ICON} IDAIM Cyprus")
        st.caption(f"v0.5.0 | {datetime.now().strftime('%Y-%m-%d')}")

        with st.expander("📊 Sheets Durumu", expanded=False):
            try:
                status = sheets_client.sheet_health_check()
                for key, info in status.items():
                    icon = "✅" if info["exists"] else "❌"
                    st.caption(f"{icon} **{key}**: {info['rows']} satır")
            except Exception as e:
                st.error(f"Health check hata: {e}")

    # Landing
    st.title(f"{config.APP_ICON} {config.APP_TITLE}")
    st.markdown(f"""
    **Müşteri:** UNDP Cyprus (UNDP-CH)
    **Amaç:** Kıbrıs'ta sivrisinek üreme alanlarını remote sensing + ML ile haritalama
    **ML modeli:** MiniRocket (5 GEE dynamic × 12 months)
    **Veri:** Google Sheets (gerçek zamanlı)
    """)

    st.markdown("---")

    # Hızlı istatistikler
    st.subheader("📊 Hızlı Bakış")
    try:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            cells = sheets_client.get_cells()
            st.metric("🗺️ Toplam Hücre", len(cells))

        with col2:
            inits = sheets_client.get_sampling_initiations(active_only=False)
            st.metric("🪤 Trap Kurulmuş", len(inits))

        with col3:
            lab = sheets_client.get_lab_results()
            st.metric("🧪 Lab Sonucu", len(lab))

        with col4:
            watch = sheets_client.get_watch_list()
            st.metric("👀 Watch List", len(watch))

    except Exception as e:
        st.error(f"Veri yüklenemedi: {e}")

    st.markdown("---")

    # Navigasyon
    st.subheader("🧭 Navigasyon")
    st.markdown("""
    Sol menüden sayfa seçin veya aşağıdaki kartlardan birini tıklayın:

    | Sayfa | Ne Yapar |
    |---|---|
    | 📥 **Veri Girişi** | Trap kurulumu, saha kontrolü, lab sonucu |
    | 🗺️ **Dashboard** | 642 hücre harita, watch list, trap durumu |
    | 🤖 **ML Retrain** | Per-species model eğit + tüm hücreleri predict et |
    | 📊 **Raporlar** | Validation metrikleri, per-district Kappa, trend |
    """)

    st.info("""
    💡 **İlk kez mi kullanıyorsun?**
    1. `SHEETS_HEADERS.md`'i oku, 7 sheet'i oluştur
    2. Streamlit Cloud → Settings → Secrets'e gcp_service_account + spreadsheet id ekle
    3. `cells` sheet'ine 642 hücrenin koordinatlarını yükle (mevcut GeoPackage'tan export)
    4. Sol menüden **Veri Girişi** → ilk trap'ı kur
    5. **ML Retrain** → Culex modeli eğit, watch list oluştur
    6. **Dashboard** → haritadan takip et
    7. **Raporlar** → metrikleri gör
    """)


if __name__ == "__main__":
    main()
