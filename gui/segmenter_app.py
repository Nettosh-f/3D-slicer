from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.segmenter_tab import render as render_segmenter_tab

APP_NAME = "Archaeological Part Segmenter"
APP_VERSION = "0.2-segmenter-only"


def main() -> None:
    st.set_page_config(page_title=APP_NAME, page_icon="🏺", layout="wide")
    st.title("🏺 Archaeological Part Segmenter")
    st.caption(
        f"{APP_VERSION} — Multi-angle renderer images → part masks, crops, overlays, and ML-friendly JSON."
    )
    render_segmenter_tab()


if __name__ == "__main__":
    main()
