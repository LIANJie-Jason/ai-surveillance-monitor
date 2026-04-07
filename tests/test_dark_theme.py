# tests/test_dark_theme.py
import re
from pathlib import Path
from unittest.mock import patch

import pytest


_CSS_PATH = Path(__file__).resolve().parent.parent / "dashboard" / "styles" / "dark_theme.css"


def test_dark_theme_css_file_exists():
    """The dark_theme.css file must exist."""
    assert _CSS_PATH.is_file()


def test_dark_theme_css_not_empty():
    """CSS file should contain meaningful content."""
    text = _CSS_PATH.read_text(encoding="utf-8")
    assert len(text) > 500


def test_dark_theme_css_has_core_selectors():
    """CSS must contain the expected core selectors for command-center theme."""
    text = _CSS_PATH.read_text(encoding="utf-8")
    for selector in [".stApp", ".article-card", ".confidence-high", ".confidence-medium",
                     ".category-tag", ".country-btn", ".news-feed", ".live-stream-container",
                     ".stDataFrame"]:
        assert selector in text, f"Missing selector: {selector}"


def test_dark_theme_css_has_form_input_selectors():
    """CSS must style text inputs, textarea, progress bar, and spinner."""
    text = _CSS_PATH.read_text(encoding="utf-8")
    for selector in ['data-baseweb="input"', 'data-baseweb="textarea"',
                     "stProgressBar", "stSpinner"]:
        assert selector in text, f"Missing form input selector: {selector}"


def test_dark_theme_css_has_dataframe_cell_colors():
    """DataFrame cells must have explicit text and background colors."""
    text = _CSS_PATH.read_text(encoding="utf-8")
    assert "stDataFrameResizable" in text, "Missing DataFrame cell color overrides"


def test_dark_theme_css_uses_correct_palette():
    """CSS should use the design-specified color palette (all 8 accent colors)."""
    text = _CSS_PATH.read_text(encoding="utf-8")
    for color in ["#0d1117", "#161b22", "#30363d", "#e6edf3", "#8b949e",
                   "#f85149", "#d29922", "#3fb950", "#58a6ff"]:
        assert color in text, f"Missing color: {color}"


def test_dark_theme_css_stapp_uses_important():
    """.stApp background-color must use !important for cascade resilience."""
    text = _CSS_PATH.read_text(encoding="utf-8")
    assert "background-color: #0d1117 !important" in text


def test_load_dark_theme_injects_css():
    """load_dark_theme() should call st.markdown with CSS content."""
    with patch("dashboard.styles.st") as mock_st:
        from dashboard.styles import load_dark_theme
        load_dark_theme()
        mock_st.markdown.assert_called_once()
        call_args = mock_st.markdown.call_args
        html = call_args[0][0]
        assert "<style>" in html
        assert "#0d1117" in html
        assert call_args[1]["unsafe_allow_html"] is True


def test_load_dark_theme_missing_file_does_not_crash():
    """If dark_theme.css is missing, load_dark_theme should silently skip."""
    with patch("dashboard.styles._STYLES_DIR", Path("/nonexistent")):
        with patch("dashboard.styles.st") as mock_st:
            from dashboard.styles import load_dark_theme
            load_dark_theme()  # should not raise
            mock_st.markdown.assert_not_called()


def test_load_dark_theme_rejects_style_escape(tmp_path: Path):
    """CSS containing </style> should raise ValueError (injection guard)."""
    bad_css = "body { color: red; } </style><script>alert(1)</script>"
    bad_file = tmp_path / "dark_theme.css"
    bad_file.write_text(bad_css, encoding="utf-8")
    with patch("dashboard.styles._STYLES_DIR", tmp_path):
        with patch("dashboard.styles.st"):
            from dashboard.styles import load_dark_theme
            with pytest.raises(ValueError, match="</style>"):
                load_dark_theme()


@pytest.mark.parametrize("payload", [
    "</ style>",           # space after slash
    "</style >",           # space before close
    "< / style >",        # spaces everywhere
    "</STYLE>",            # uppercase
    "</ Style>",           # mixed case with space
    "</style/>",           # self-closing slash
    "</style />",          # self-closing with space
    "</style x>",          # trailing attribute
    "</style x=y>",        # trailing attribute with value
])
def test_load_dark_theme_rejects_style_escape_variants(tmp_path: Path, payload: str):
    """Whitespace variants of </style> must also be rejected."""
    bad_css = f"body {{ color: red; }} {payload}<script>alert(1)</script>"
    bad_file = tmp_path / "dark_theme.css"
    bad_file.write_text(bad_css, encoding="utf-8")
    with patch("dashboard.styles._STYLES_DIR", tmp_path):
        with patch("dashboard.styles.st"):
            from dashboard.styles import load_dark_theme
            with pytest.raises(ValueError, match="</style>"):
                load_dark_theme()


def test_dark_theme_css_no_style_close_tag():
    """The CSS file itself must not contain any </style> variant."""
    text = _CSS_PATH.read_text(encoding="utf-8")
    from dashboard.styles import _STYLE_CLOSE_RE
    assert not _STYLE_CLOSE_RE.search(text), "CSS file contains a </style> variant"


def test_dark_theme_css_no_syntax_errors():
    """Basic check: no unmatched braces in CSS."""
    text = _CSS_PATH.read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    assert text.count("{") == text.count("}"), "Unmatched braces in CSS"
