#!/usr/bin/env python3
"""Robust Windows launcher for the PLY renderer starter kit."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
DEFAULT_OUTPUT = ROOT / "output"
RENDERER = ROOT / "renderer" / "ply_spherical_renderer_windows.py"
LAUNCHER_VERSION = "2.2"


def print_help() -> None:
    print(
        r"""
PLY Renderer Starter Kit Launcher v2.2
======================================

Usage:
  render_model_v2.bat <model_or_folder> [output_folder] [renderer arguments...]

Examples:
  render_model_v2.bat "HAD16_279_2916 FIGURINE.ply" output -phi 20 -theta 20
  render_model_v2.bat "HAD16_279_2916 FIGURINE.ply" output --classification figurine
  render_model_v2.bat figurines output --class-from-parent -phi 10 -theta 10

Important arguments:
  -phi N                  Azimuth step in degrees. Default: 2
  -theta N                Polar-angle step in degrees. Default: 2
  --classification NAME   Apply one classification to all models
  --class-from-parent      Use each model's parent folder as its class
  --labels-csv FILE        Load classifications from a CSV file
  --width N --height N     Output image dimensions. Default: 512 x 512
  --overwrite              Re-render images that already exist
  --dry-run                Preview planned work without rendering
""".strip()
    )


def resolve_input(raw: str) -> Path:
    supplied = Path(raw).expanduser()
    candidates = []

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


def same_model_token(token: str, raw_input: str, input_path: Path) -> bool:
    """Recognize an accidentally repeated input argument without touching option values."""
    if token.startswith("-"):
        return False

    normalized_token = os.path.normcase(token.strip().strip('"').replace("/", os.sep))
    forms = {
        os.path.normcase(raw_input.strip().strip('"').replace("/", os.sep)),
        os.path.normcase(input_path.name),
        os.path.normcase(input_path.stem),
        os.path.normcase(str(input_path)),
    }
    return normalized_token in forms


def remove_accidental_duplicate_input(extra_args: list[str], raw_input: str, input_path: Path) -> list[str]:
    """
    Preserve recognized option values and discard unexpected positional tokens.

    Once the launcher has consumed the input and optional output directory, the
    renderer accepts only named options. A remaining free positional token is
    therefore always accidental, commonly caused by an older Windows wrapper.
    """
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

        print(f'Warning: ignored unexpected extra positional argument: "{token}"')
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

    extra_args = remove_accidental_duplicate_input(remaining, raw_input, input_path)

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
