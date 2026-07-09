from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_NAME = "3D-slicer Pipeline"


def main() -> None:
    st.set_page_config(page_title=APP_NAME, page_icon="🏺", layout="wide")

    pages = [
        st.Page(
            "renderer_page.py",
            title="Renderer",
            icon="🧊",
            default=True,
        ),
        st.Page(
            "segmenter_page.py",
            title="Segmenter",
            icon="🏺",
        ),
    ]
    st.navigation(pages, position="top").run()


if __name__ == "__main__":
    main()
