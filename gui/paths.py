from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
RENDERER_OUTPUT = ROOT / "output" / "renderer"
RENDERER_IMAGES = RENDERER_OUTPUT / "images"
SEGMENTER_OUTPUT = ROOT / "output" / "segmenter"
RENDERER_SCRIPT = ROOT / "renderer" / "ply_spherical_renderer_windows.py"
LABELS_TEMPLATE = ROOT / "renderer" / "labels_template.csv"
SEGMENTATION_TOOL = ROOT / "segmentation tool"
TAXONOMY_CONFIG = SEGMENTATION_TOOL / "configs" / "taxonomy.json"


def ensure_segmenter_import_path() -> None:
    seg_root = str(SEGMENTATION_TOOL)
    if seg_root not in sys.path:
        sys.path.insert(0, seg_root)
