#!/usr/bin/env python3
"""Robust project launcher for the PLY renderer.

This file is called by render_model.bat. It resolves model names inside
models/, handles paths with spaces, and forwards remaining named options to
ply_spherical_renderer_windows.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
DEFAULT_OUTPUT = ROOT / "output" / "renderer"
RENDERER = ROOT / "renderer" / "ply_spherical_renderer_windows.py"
LAUNCHER_VERSION = "2.3"


def print_help() -> None:
    print(
        r"""
3D-slicer PLY Renderer Launcher v2.3
====================================

Usage:
  render_model.bat <model_or_folder> [output_folder] [renderer arguments...]

The model_or_folder argument may be:
  - a filename inside models\, such as "statue.ply"
  - a folder inside models\, such as "figurines"
  - a direct relative or absolute path

If output_folder is omitted, output\renderer\ is used.

Important renderer arguments:
  -phi N                  Azimuth step in degrees around the model. Default: 2
  -theta N                Polar-angle step in degrees from top to bottom. Default: 2
  --classification NAME   Apply one classification to all models in this run
  --class-from-parent      Use each model's parent-folder name as its classification
  --labels-csv FILE        Load classifications from a CSV file
  --width N --height N     Output PNG dimensions. Default: 512 x 512
  --renderer-backend NAME  auto, visualizer, or offscreen. Default: auto
  --overwrite              Re-render PNG files that already exist
  --dry-run                Preview planned work without rendering

Examples:
  render_model.bat "HAD16_279_2916 FIGURINE.ply" output\renderer -phi 20 -theta 20
  render_model.bat "HAD16_279_2916 FIGURINE.ply" output\renderer --classification figurine
  render_model.bat figurines output\renderer --class-from-parent -phi 10 -theta 10
  render_model.bat "C:\data\model.ply" "C:\data\renders" -phi 5 -theta 5

For the full renderer CLI reference:
  venv\Scripts\python.exe renderer\ply_spherical_renderer_windows.py --help
""".strip()
    )


def resolve_input(raw: str) -> Path:
    supplied = Path(raw).expanduser()
    candidates: list[Path] = []

    if supplied.is_absolute():
        candidates.append(supplied)
    else:
        candidates.extend((Path.cwd() / supplied, ROOT / supplied, MODELS_DIR / supplied))

    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(str(candidate)))
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate.resolve()

    attempted = "\n".join(f"  {candidate}" for candidate in candidates)
    raise FileNotFoundError(f"Could not find input. Tried:\n{attempted}")


def resolve_output(raw: str | None) -> Path:
    if raw is None:
        output = DEFAULT_OUTPUT
    else:
        supplied = Path(raw).expanduser()
        output = supplied if supplied.is_absolute() else ROOT / supplied

    output.mkdir(parents=True, exist_ok=True)
    return output.resolve()


def remove_accidental_duplicate_input(extra_args: list[str]) -> list[str]:
    """Preserve known option values and discard accidental free positional tokens."""
    options_with_one_value = {
        "-phi", "--phi-step", "-theta", "--theta-step", "--width", "--height",
        "--fov", "--margin", "--point-size", "--classification", "--labels-csv",
        "--progress-every", "--renderer-backend",
    }
    options_with_four_values = {"--background", "--base-color"}
    flag_options = {
        "--class-from-parent", "--no-recursive", "--overwrite", "--hash-source",
        "--headless-cpu", "--dry-run", "--version", "-h", "--help",
    }

    cleaned: list[str] = []
    index = 0
    while index < len(extra_args):
        token = extra_args[index]

        if token in options_with_one_value:
            cleaned.append(token)
            if index + 1 < len(extra_args):
                cleaned.append(extra_args[index + 1])
            index += 2
            continue

        if token in options_with_four_values:
            cleaned.append(token)
            cleaned.extend(extra_args[index + 1:index + 5])
            index += 5
            continue

        if token in flag_options or token.startswith("-"):
            cleaned.append(token)
            index += 1
            continue

        print(f'Warning: ignored unexpected extra positional argument after input/output: "{token}"')
        index += 1

    return cleaned


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0].casefold() in {"-h", "--help", "/?"}:
        print_help()
        return 0

    raw_input = argv[0]
    remaining = argv[1:]

    output_arg: str | None = None
    if remaining and not remaining[0].startswith("-"):
        output_arg = remaining[0]
        remaining = remaining[1:]

    try:
        input_path = resolve_input(raw_input)
        output_path = resolve_output(output_arg)
    except (FileNotFoundError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if not RENDERER.is_file():
        print(f"Error: renderer script is missing: {RENDERER}", file=sys.stderr)
        return 2

    extra_args = remove_accidental_duplicate_input(remaining)

    command = [
        sys.executable,
        str(RENDERER),
        str(input_path),
        str(output_path),
        *extra_args,
    ]

    print(f"\nLauncher version: {LAUNCHER_VERSION}")
    print(f'Input:  "{input_path}"')
    print(f'Output: "{output_path}"')
    if extra_args:
        print("Extra arguments:", subprocess.list2cmdline(extra_args))
    print("Exact renderer command:")
    print("  " + subprocess.list2cmdline(command))
    print()

    try:
        completed = subprocess.run(command, check=False)
    except OSError as exc:
        print(f"Failed to start renderer: {exc}", file=sys.stderr)
        return 2

    if completed.returncode == 0:
        print("\nDone.")
    else:
        print(f"\nRenderer finished with errors. Exit code: {completed.returncode}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
