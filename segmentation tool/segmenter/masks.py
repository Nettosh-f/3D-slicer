from __future__ import annotations
from typing import Any
import numpy as np


def bbox_from_mask(mask: np.ndarray) -> list[int]:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0 or len(ys) == 0:
        return [0, 0, 0, 0]
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return [x0, y0, x1 - x0 + 1, y1 - y0 + 1]


def area_from_mask(mask: np.ndarray) -> int:
    return int(np.count_nonzero(mask))


def encode_binary_mask_rle(mask: np.ndarray) -> dict[str, Any]:
    """COCO-like uncompressed RLE, column-major order."""
    binary = np.asfortranarray((mask > 0).astype(np.uint8))
    pixels = binary.reshape(-1, order="F")
    counts: list[int] = []
    previous = 0
    run_length = 0
    for pixel in pixels:
        if int(pixel) == previous:
            run_length += 1
        else:
            counts.append(run_length)
            run_length = 1
            previous = int(pixel)
    counts.append(run_length)
    return {"size": [int(mask.shape[0]), int(mask.shape[1])], "counts": counts, "format": "uncompressed_rle"}
