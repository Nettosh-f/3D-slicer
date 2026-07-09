from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.renderer_tab import render as render_renderer_tab

APP_NAME = "PLY Spherical Renderer"
APP_VERSION = "0.3-renderer-only"


def main() -> None:
    st.set_page_config(page_title=APP_NAME, page_icon="🧊", layout="wide")
    st.title("🧊 PLY Spherical Renderer")
    st.caption(f"{APP_VERSION} — Render `.ply` models into multi-angle PNGs under `output/renderer`.")
    render_renderer_tab()


if __name__ == "__main__":
    main()
