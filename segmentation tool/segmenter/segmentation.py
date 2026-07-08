from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np
from PIL import Image

@dataclass(frozen=True)
class CandidateMask:
    name_hint: str
    mask: np.ndarray
    confidence: float
    method: str
    presence_status: str = "detected"

def make_object_mask(image: Image.Image) -> np.ndarray:
    """Segment rendered artifact from a white or transparent background."""
    rgba = image.convert("RGBA")
    arr = np.array(rgba)
    alpha = arr[:, :, 3]

    if alpha.min() < 250:
        mask = (alpha > 10).astype(np.uint8) * 255
    else:
        rgb = arr[:, :, :3]
        dist_from_white = np.linalg.norm(255 - rgb.astype(np.int16), axis=2)
        mask = (dist_from_white > 22).astype(np.uint8) * 255
        if np.count_nonzero(mask) < 0.005 * mask.size:
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n > 1:
        largest = int(stats[1:, cv2.CC_STAT_AREA].argmax()) + 1
        mask = (labels == largest).astype(np.uint8) * 255
    return mask

def edge_mask(object_mask: np.ndarray, thickness: int = 8) -> np.ndarray:
    kernel = np.ones((max(1, thickness), max(1, thickness)), np.uint8)
    eroded = cv2.erode(object_mask, kernel, iterations=1)
    return cv2.subtract(object_mask, eroded)

def band_mask(object_mask: np.ndarray, y0_norm: float, y1_norm: float) -> np.ndarray:
    ys, _ = np.where(object_mask > 0)
    out = np.zeros_like(object_mask)
    if len(ys) == 0:
        return out
    min_y, max_y = int(ys.min()), int(ys.max())
    height = max(1, max_y - min_y + 1)
    y0 = max(min_y, min(int(min_y + y0_norm * height), max_y))
    y1 = max(y0 + 1, min(int(min_y + y1_norm * height), max_y + 1))
    out[y0:y1, :] = object_mask[y0:y1, :]
    return out

def center_band_mask(object_mask: np.ndarray, y0_norm: float, y1_norm: float, x_margin_norm: float = 0.20) -> np.ndarray:
    ys, xs = np.where(object_mask > 0)
    out = band_mask(object_mask, y0_norm, y1_norm)
    if len(xs) == 0:
        return out
    min_x, max_x = int(xs.min()), int(xs.max())
    width = max(1, max_x - min_x + 1)
    x0 = int(min_x + x_margin_norm * width)
    x1 = int(max_x - x_margin_norm * width)
    mask2 = np.zeros_like(out)
    mask2[:, max(min_x, x0):min(max_x + 1, x1)] = out[:, max(min_x, x0):min(max_x + 1, x1)]
    return mask2

def side_band_mask(object_mask: np.ndarray, y0_norm: float, y1_norm: float, side: str) -> np.ndarray:
    _, xs = np.where(object_mask > 0)
    out = band_mask(object_mask, y0_norm, y1_norm)
    if len(xs) == 0:
        return out
    min_x, max_x = int(xs.min()), int(xs.max())
    width = max(1, max_x - min_x + 1)
    if side == "left":
        x0, x1 = min_x, int(min_x + 0.33 * width)
    else:
        x0, x1 = int(max_x - 0.33 * width), max_x + 1
    mask2 = np.zeros_like(out)
    mask2[:, x0:x1] = out[:, x0:x1]
    return mask2

def geometric_mask_for_part(object_mask: np.ndarray, part: dict) -> np.ndarray:
    name = str(part["name"])
    y0, y1 = part.get("y_range", [0.0, 1.0])
    zone = str(part.get("zone", "")).casefold()
    if "edge" in zone:
        return edge_mask(object_mask, 7)
    if "side" in zone or name in {"arms", "handle", "spout"}:
        return cv2.bitwise_or(side_band_mask(object_mask, y0, y1, "left"), side_band_mask(object_mask, y0, y1, "right"))
    if "center" in zone or name in {"face", "torso", "legs", "tang", "socket"}:
        margin = 0.28 if name == "face" else 0.18
        return center_band_mask(object_mask, y0, y1, margin)
    return band_mask(object_mask, y0, y1)

def generate_geometric_part_masks(
    object_mask: np.ndarray,
    taxonomy_parts: list[dict],
    selected_part_names: set[str] | None = None,
    force_all_parts: bool = False,
) -> tuple[list[CandidateMask], list[dict]]:
    """Generate candidate part masks.

    Important behavior:
    - Taxonomy parts are possible labels, not mandatory labels.
    - If selected_part_names is supplied, only those visible/expected parts are segmented.
    - If force_all_parts=True, all taxonomy parts are segmented for debugging.
    - Otherwise, only primary_fallback parts are emitted. This avoids fabricating rim/neck/base/etc.
      on fragments where the geometric engine has no reliable semantic evidence.
    """
    candidates: list[CandidateMask] = []
    absent_or_not_requested: list[dict] = []
    object_area = max(1, int(np.count_nonzero(object_mask)))

    normalized_selection = {p.casefold() for p in selected_part_names or set() if p.strip()}

    for part in taxonomy_parts:
        name = str(part["name"])
        name_key = name.casefold()
        primary = bool(part.get("primary_fallback", False))

        if force_all_parts:
            should_attempt = True
            status = "forced_debug"
        elif normalized_selection:
            should_attempt = name_key in normalized_selection
            status = "user_selected" if should_attempt else "not_selected"
        else:
            should_attempt = primary
            status = "primary_fallback" if should_attempt else "not_requested_optional"

        if not should_attempt:
            absent_or_not_requested.append({
                "part_name": name,
                "presence_status": status,
                "reason": "Taxonomy part is possible for this class but was not requested or selected.",
            })
            continue

        mask = geometric_mask_for_part(object_mask, part)
        area = int(np.count_nonzero(mask))
        area_ratio = area / object_area

        if area < 20 or area_ratio < 0.002:
            confidence = 0.20
            presence_status = "attempted_no_evidence"
        else:
            # User-selected/primary fallback crops are useful, but still not semantic proof.
            base = 0.58 if status in {"user_selected", "forced_debug"} else 0.50
            confidence = min(0.85, base + area_ratio * 0.70)
            presence_status = status

        candidates.append(CandidateMask(
            name_hint=name,
            mask=mask,
            confidence=float(confidence),
            method="geometric_taxonomy_optional",
            presence_status=presence_status,
        ))

    return candidates, absent_or_not_requested

def estimate_sharpness(image_rgb: np.ndarray, mask: np.ndarray) -> float:
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return 0.0
    crop = gray[int(ys.min()):int(ys.max()) + 1, int(xs.min()):int(xs.max()) + 1]
    return float(cv2.Laplacian(crop, cv2.CV_64F).var()) if crop.size else 0.0
