"""Split module: SystemConfig."""
import streamlit as st
from core.branding import PRODUCT_NAME

class SystemConfig:
    """Global application configuration.

    Holds the display title, version, and static UI styling. The renderer is
    deliberately grayscale ("Pure-Gray") to keep the researcher focused on
    medical image content rather than decorative color.
    """

    TITLE = f"{PRODUCT_NAME} (Research / Education Tool)"
    VERSION = "1.0.1"

    @staticmethod
    def apply_style():
        """تطبيق واجهة عرض رمادية (Pure-Gray) لمنع تشتت الباحث الطبي."""
        st.markdown("""
            <style>
                .main { background-color: #050505; color: #b0b0b0; }
                img, canvas { filter: grayscale(100%); border: 1px solid #333; image-rendering: pixelated; }
                .diag-box { 
                    padding: 20px; border-left: 4px solid #444; 
                    background: #0a0a0a; color: #00ff00; 
                    font-family: 'Courier New', monospace; margin-bottom: 10px;
                }
                [data-testid="stSidebar"] { background-color: #050505; border-right: 1px solid #222; }
                h1, h2, h3 { color: #ffffff; font-weight: 300; }
            </style>
        """, unsafe_allow_html=True)


# --- [LAYER 2: ANALYTICAL INTERFACES] ---
