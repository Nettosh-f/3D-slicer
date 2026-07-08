from __future__ import annotations
import re
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def safe_name(value: str, fallback: str = "unnamed") -> str:
    value = value.strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("._-")
    return value or fallback


def list_images(folder: Path) -> list[Path]:
    folder = Path(folder).expanduser().resolve()
    return sorted(
        [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda p: p.name.casefold(),
    )


def infer_angle_metadata(filename: str) -> dict[str, int | None]:
    out: dict[str, int | None] = {"phi": None, "theta": None, "elevation": None}
    patterns = {
        "phi": r"(?:^|[_-])phi[_-](-?\d+)",
        "theta": r"(?:^|[_-])theta[_-](-?\d+)",
        "elevation": r"(?:^|[_-])el(?:evation)?[_-](-?\d+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, filename, flags=re.IGNORECASE)
        if match:
            out[key] = int(match.group(1))
    return out
