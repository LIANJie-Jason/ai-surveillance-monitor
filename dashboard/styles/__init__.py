"""Dashboard styles — CSS loading utilities."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)

_STYLES_DIR = Path(__file__).parent

# Matches any </style...> variant: whitespace, self-closing slash, attributes, etc.
_STYLE_CLOSE_RE = re.compile(r"<\s*/\s*style\b[^>]*>", re.IGNORECASE)


def load_dark_theme() -> None:
    """Inject the dark command-center CSS into the Streamlit page.

    Gracefully skips if the CSS file is missing (app works without theme).
    Raises ValueError if the CSS contains a </style> variant (possible injection).
    """
    css_path = _STYLES_DIR / "dark_theme.css"
    try:
        css_text = css_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("dark_theme.css not found — skipping theme injection")
        return
    if _STYLE_CLOSE_RE.search(css_text):
        raise ValueError("CSS file contains </style> variant — possible injection")
    st.markdown(f"<style>{css_text}</style>", unsafe_allow_html=True)
