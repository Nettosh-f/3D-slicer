from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui.segmenter_tab import render as render_segmenter_tab

st.title("🏺 3D-slicer Pipeline")
st.caption("Segmenter — part masks, crops, and JSON from rendered views. (UI v0.4)")
render_segmenter_tab()
