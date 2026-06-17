"""app.py — IDAIM Streamlit landing page.

Pages (visible to all authenticated users):
  1. Data Entry (Sampling Initiation / Trap Check / Lab Result)
  2. Dashboard (map + watch list)
  3. Reports (charts + statistics)

Admin-only page:
  4. Admin (training metrics, Sheets health, user management)

Auth: username + password (users sheet).
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
    """Username + password login."""
    st.title(f"{config.APP_ICON} {config.APP_TITLE}")
    st.markdown("**Cyprus Mosquito Vector Surveillance System** | UNDP-CH")
    st.markdown("---")

    with st.form("login_form"):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.subheader("Sign In")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Sign In", use_container_width=True)

    if submit:
        role = sheets_client.verify_user(username, password)
        if role:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.session_state["role"] = role
            sheets_client.update_last_login(username)
            st.success(f"Welcome, {username} (role: {role})")
            st.rerun()
        else:
            st.error("Invalid username or password")

    with st.expander("First time here?"):
        st.markdown("""
        **Default users (auto-created on first run in the `users` sheet):**

        | Username | Password | Role |
        |---|---|---|
        | `admin` | `idaim2026` | Admin (sees everything) |
        | `field` | `field2026` | Field team (trap setup) |
        | `lab` | `lab2026` | Lab technician (lab results) |

        **Important:** Change passwords after first login.
        """)


def logout_button():
    """Logout button in the sidebar."""
    with st.sidebar:
        st.markdown("---")
        st.markdown(f"**{st.session_state.get('username', '?')}** ({st.session_state.get('role', '?')})")
        if st.button("Sign Out", use_container_width=True):
            for k in ["authenticated", "username", "role"]:
                st.session_state.pop(k, None)
            st.rerun()


# ============== MAIN APP ==============

def main():
    if not st.session_state.get("authenticated", False):
        login_page()
        return

    logout_button()

    # Sidebar header
    with st.sidebar:
        st.title(f"{config.APP_ICON} IDAIM Cyprus")
        st.caption(f"v0.6.0 | {datetime.now().strftime('%Y-%m-%d')}")

        with st.expander("Sheets Status", expanded=False):
            try:
                status = sheets_client.sheet_health_check()
                for key, info in status.items():
                    icon = "OK" if info["exists"] else "MISSING"
                    st.caption(f"{icon} **{key}**: {info['rows']} rows")
            except Exception as e:
                st.error(f"Health check error: {e}")

    # Landing
    st.title(f"{config.APP_ICON} {config.APP_TITLE}")
    st.markdown("**Cyprus mosquito vector surveillance** | UNDP-CH")
    st.markdown("---")

    # Quick stats
    st.subheader("Overview")
    try:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            cells = sheets_client.get_cells()
            st.metric("Grid Cells", len(cells))

        with col2:
            inits = sheets_client.get_sampling_initiations(active_only=False)
            st.metric("Traps Installed", len(inits))

        with col3:
            lab = sheets_client.get_lab_results()
            st.metric("Lab Results", len(lab))

        with col4:
            watch = sheets_client.get_watch_list()
            st.metric("Watch List", len(watch))

    except Exception as e:
        st.error(f"Data load error: {e}")

    st.markdown("---")

    # Navigation
    role = st.session_state.get("role", "")
    is_admin = role == "admin"

    st.subheader("Navigation")
    if is_admin:
        st.markdown("""
        Use the left menu or jump to a page:

        | Page | Purpose |
        |---|---|
        | **Data Entry** | Trap setup, field checks, lab results |
        | **Dashboard** | Map, watch list, trap status |
        | **Reports** | Validation metrics, district stats, trends |
        | **Admin** | Training metrics, Sheets health, user management (admin only) |
        """)
    else:
        st.markdown("""
        Use the left menu or jump to a page:

        | Page | Purpose |
        |---|---|
        | **Data Entry** | Trap setup, field checks, lab results |
        | **Dashboard** | Map, watch list, trap status |
        | **Reports** | Charts and statistics |
        """)


if __name__ == "__main__":
    main()
