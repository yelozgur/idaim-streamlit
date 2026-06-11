"""mobile_styles.py — Mobile-first CSS (sayfalara inject edilir).

Streamlit'in default tema mobil için optimize değil. Bu CSS ile:
- Tek kolun layout
- Büyük butonlar (min 48dp dokunma alanı)
- Sabit alt action bar
- Büyük font (16px+)
- Form elemanları parmak-dostu
"""
import streamlit as st


def inject_mobile_css():
    """<style> tag'i inject et. Her sayfanın başında çağır."""
    css = """
    <style>
    /* === Genel === */
    .main .block-container {
        padding-top: 1rem;
        padding-bottom: 5rem;  /* sabit alt bar için yer */
        max-width: 100%;
    }

    /* === Başlıklar === */
    h1 { font-size: 1.6rem !important; }
    h2 { font-size: 1.3rem !important; }
    h3 { font-size: 1.1rem !important; }

    /* === Butonlar — büyük ve dokunmatik dostu === */
    .stButton > button {
        min-height: 48px;
        font-size: 16px !important;
        font-weight: 600 !important;
        border-radius: 12px !important;
        padding: 12px 20px !important;
        -webkit-tap-highlight-color: transparent;
    }

    /* Primary buton (mavi) — ekstra vurgu */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1a73e8, #4285f4) !important;
        color: white !important;
        border: none !important;
        box-shadow: 0 2px 8px rgba(26,115,232,0.3) !important;
    }
    .stButton > button[kind="primary"]:active {
        transform: scale(0.98);
    }

    /* === Form elemanları === */
    .stTextInput input,
    .stTextArea textarea,
    .stNumberInput input,
    .stDateInput input,
    .stTimeInput input {
        min-height: 48px !important;
        font-size: 16px !important;  /* iOS zoom engeli */
        border-radius: 8px !important;
    }

    .stSelectbox [data-baseweb="select"] {
        min-height: 48px !important;
    }

    /* === File uploader — kamera için === */
    [data-testid="stFileUploaderDropzone"] {
        min-height: 100px;
        border: 2px dashed #4285f4;
        border-radius: 12px;
        padding: 16px;
    }

    /* === Tabs — alt sekme stili === */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        overflow-x: auto;
        scrollbar-width: none;
    }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
        display: none;
    }
    .stTabs [data-baseweb="tab"] {
        min-height: 48px;
        padding: 8px 16px;
        font-size: 14px;
        font-weight: 600;
        white-space: nowrap;
    }

    /* === Metric kartları === */
    [data-testid="stMetric"] {
        background: #f8f9fa;
        padding: 12px;
        border-radius: 12px;
        border: 1px solid #e8eaed;
    }
    [data-testid="stMetricLabel"] {
        font-size: 12px !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
    }

    /* === Alert / Info === */
    .stAlert {
        border-radius: 12px;
        padding: 12px 16px;
    }

    /* === Form submit butonu === */
    .stFormSubmitButton > button {
        min-height: 56px !important;
        font-size: 17px !important;
    }

    /* === Geniş kolon gizle (mobil) === */
    @media (max-width: 768px) {
        [data-testid="column"]:not(:first-child) {
            margin-top: 12px;
        }
    }

    /* === Sabit alt bar (isteğe bağlı) === */
    .fixed-bottom-action {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        padding: 12px 16px;
        background: white;
        border-top: 1px solid #e8eaed;
        box-shadow: 0 -2px 8px rgba(0,0,0,0.08);
        z-index: 999;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
