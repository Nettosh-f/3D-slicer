from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import numpy as np
from PIL import Image, ImageDraw
from .masks import bbox_from_mask

PALETTE = [(230,25,75),(60,180,75),(255,225,25),(0,130,200),(245,130,48),(145,30,180),(70,240,240),(240,50,230),(210,245,60)]


def ensure_dirs(output_dir: Path) -> dict[str, Path]:
    paths = {"annotated": output_dir/"annotated", "clean": output_dir/"clean_visual", "crops": output_dir/"part_crops", "json": output_dir/"json", "logs": output_dir/"logs"}
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


def apply_overlay(image: Image.Image, parts: list[dict[str, Any]], show_confidence: bool) -> Image.Image:
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0,0,0,0))
    for i, part in enumerate(parts):
        color = PALETTE[i % len(PALETTE)]
        mask = part["_mask"]
        rgba = np.zeros((mask.shape[0], mask.shape[1], 4), dtype=np.uint8)
        rgba[mask > 0] = (*color, 90)
        overlay = Image.alpha_composite(overlay, Image.fromarray(rgba, mode="RGBA"))
        d = ImageDraw.Draw(overlay)
        x, y, w, h = part["bbox_xywh"]
        d.rectangle([x, y, x+w, y+h], outline=(*color,230), width=2)
        label = part["part_name"] + (f" {part['confidence']:.2f}" if show_confidence else "")
        d.text((x+3, max(0, y-14)), label, fill=(*color,255))
    result = Image.alpha_composite(base, overlay)
    panel_w = min(360, max(220, int(result.width*0.38)))
    panel_h = 24 + len(parts)*20
    legend = Image.new("RGBA", (panel_w, panel_h), (255,255,255,215))
    d = ImageDraw.Draw(legend)
    d.text((8,4), "Parts", fill=(0,0,0,255))
    for i, part in enumerate(parts):
        color = PALETTE[i % len(PALETTE)]
        y = 24 + i*20
        text = part["part_name"] + (f" {part['confidence']:.2f}" if show_confidence else "")
        d.rectangle([8,y,20,y+12], fill=(*color,220))
        d.text((26,y-2), text, fill=(0,0,0,255))
    result.alpha_composite(legend, (8,8))
    return result.convert("RGB")


def crop_and_pad(image: Image.Image, mask: np.ndarray, target_size: int) -> Image.Image:
    arr = np.array(image.convert("RGB"))
    x, y, w, h = bbox_from_mask(mask)
    if w <= 0 or h <= 0:
        return Image.new("RGB", (target_size,target_size), (255,255,255))
    crop = arr[y:y+h, x:x+w].copy()
    crop_mask = mask[y:y+h, x:x+w] > 0
    crop[~crop_mask] = [255,255,255]
    pil_crop = Image.fromarray(crop)
    pil_crop.thumbnail((target_size,target_size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (target_size,target_size), (255,255,255))
    canvas.paste(pil_crop, ((target_size-pil_crop.width)//2, (target_size-pil_crop.height)//2))
    return canvas


def save_image_outputs(image: Image.Image, image_stem: str, parts: list[dict[str, Any]], output_paths: dict[str, Path], crop_size: int, annotated: bool, clean: bool, crops: bool):
    annotated_path = None
    clean_path = None
    crop_refs: dict[int,str] = {}
    if annotated:
        p = output_paths["annotated"] / f"{image_stem}__annotated.png"
        apply_overlay(image, parts, True).save(p)
        annotated_path = str(p)
    if clean:
        p = output_paths["clean"] / f"{image_stem}__clean.png"
        apply_overlay(image, parts, False).save(p)
        clean_path = str(p)
    if crops:
        for idx, part in enumerate(parts):
            safe_part = part["part_name"].replace("/","_").replace(" ","_")
            p = output_paths["crops"] / safe_part / f"{image_stem}__{safe_part}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            crop_and_pad(image, part["_mask"], crop_size).save(p)
            crop_refs[idx] = str(p)
    return annotated_path, clean_path, crop_refs


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
