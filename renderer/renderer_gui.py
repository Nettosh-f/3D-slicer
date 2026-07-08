#!/usr/bin/env python3
"""Tkinter GUI launcher for the PLY spherical renderer starter kit.

Place this file in:
    <project-root>/renderer/renderer_gui.py

It expects the renderer script at:
    <project-root>/renderer/ply_spherical_renderer_windows.py

No third-party GUI package is required; Tkinter ships with normal Python installs.
"""

from __future__ import annotations

import os
import platform
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_VERSION = "0.3"
ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
DEFAULT_OUTPUT = ROOT / "output"
RENDERER = ROOT / "renderer" / "ply_spherical_renderer_windows.py"


@dataclass(frozen=True)
class ModelChoice:
    label: str
    path: Path
    kind: str  # "file" or "folder"


class ToolTip:
    """Small Tkinter tooltip for explaining renderer settings inline."""

    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 500) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _event: tk.Event) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self) -> None:
        if self._tip is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self._tip,
            text=self.text,
            justify="left",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=5,
            wraplength=420,
        )
        label.pack()

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


def relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def scan_models() -> list[ModelChoice]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    choices: list[ModelChoice] = []

    ply_files = sorted(MODELS_DIR.rglob("*.ply"), key=lambda p: str(p.relative_to(MODELS_DIR)).casefold())
    for path in ply_files:
        rel = path.relative_to(MODELS_DIR)
        choices.append(ModelChoice(label=f"file: {rel}", path=path.resolve(), kind="file"))

    folders: set[Path] = set()
    for path in ply_files:
        current = path.parent
        while current != MODELS_DIR and MODELS_DIR in current.parents:
            folders.add(current)
            current = current.parent
        if path.parent == MODELS_DIR:
            folders.add(MODELS_DIR)

    for folder in sorted(folders, key=lambda p: str(p.relative_to(MODELS_DIR) if p != MODELS_DIR else Path('.')).casefold()):
        rel = "." if folder == MODELS_DIR else str(folder.relative_to(MODELS_DIR))
        choices.append(ModelChoice(label=f"folder: {rel}", path=folder.resolve(), kind="folder"))

    return choices


def open_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True) if path.suffix == "" else None
    if platform.system() == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class RendererGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"PLY Spherical Renderer GUI {APP_VERSION}")
        self.geometry("1200x900")
        self.minsize(1020, 720)

        self.model_choices: list[ModelChoice] = []
        self.choice_by_label: dict[str, ModelChoice] = {}
        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.reader_thread: threading.Thread | None = None
        self.log_visible = tk.BooleanVar(value=True)
        self.log_popouts: list[tk.Text] = []

        self.input_path_var = tk.StringVar()
        self.model_choice_var = tk.StringVar()
        self.output_path_var = tk.StringVar(value=str(DEFAULT_OUTPUT))

        self.phi_var = tk.IntVar(value=20)
        self.theta_var = tk.IntVar(value=20)
        self.preset_var = tk.StringVar(value="Preview 20° / 162 views")
        self.width_var = tk.IntVar(value=512)
        self.height_var = tk.IntVar(value=512)

        self.class_mode_var = tk.StringVar(value="Unclassified")
        self.classification_var = tk.StringVar()
        self.labels_csv_var = tk.StringVar()

        self.overwrite_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)
        self.no_recursive_var = tk.BooleanVar(value=False)

        self.fov_var = tk.DoubleVar(value=45.0)
        self.margin_var = tk.DoubleVar(value=1.08)
        self.point_size_var = tk.DoubleVar(value=3.0)
        self.progress_every_var = tk.IntVar(value=500)
        self.renderer_backend_var = tk.StringVar(value="auto")
        self.hash_source_var = tk.BooleanVar(value=False)
        self.headless_cpu_var = tk.BooleanVar(value=False)
        self.background_var = tk.StringVar(value="1 1 1 1")
        self.base_color_var = tk.StringVar(value="0.72 0.72 0.72 1")

        self.advanced_visible = tk.BooleanVar(value=False)

        self._build_menu()
        self._build_ui()
        self.classification_var.trace_add("write", self.on_manual_label_changed)
        self.refresh_models()
        self.update_command_preview()
        self.after(100, self._poll_output_queue)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Refresh model list", command=self.refresh_models)
        file_menu.add_command(label="Open project folder", command=lambda: open_path(ROOT))
        file_menu.add_command(label="Open output folder", command=self.open_output_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Renderer --help", command=self.show_renderer_help)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menubar)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(7, weight=1)

        self._build_input_frame(root).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._build_output_frame(root).grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self._build_sampling_frame(root).grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self._build_classification_frame(root).grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self._build_common_flags_frame(root).grid(row=4, column=0, sticky="ew", pady=(0, 8))
        self.advanced_container = ttk.Frame(root)
        self.advanced_container.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        self._build_advanced_toggle(root).grid(row=6, column=0, sticky="ew", pady=(0, 8))
        self._build_log_frame(root).grid(row=7, column=0, sticky="nsew")
        self._build_buttons(root).grid(row=8, column=0, sticky="ew", pady=(8, 0))

    def _build_input_frame(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Input model or folder")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="From models folder:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.model_combo = ttk.Combobox(frame, textvariable=self.model_choice_var, state="readonly")
        self.model_combo.grid(row=0, column=1, sticky="ew", padx=8, pady=6)
        self.model_combo.bind("<<ComboboxSelected>>", self.on_model_choice)
        ttk.Button(frame, text="Refresh", command=self.refresh_models).grid(row=0, column=2, padx=8, pady=6)

        ttk.Label(frame, text="Selected path:").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        entry = ttk.Entry(frame, textvariable=self.input_path_var)
        entry.grid(row=1, column=1, sticky="ew", padx=8, pady=6)
        entry.bind("<KeyRelease>", lambda _e: self.update_command_preview())
        ttk.Button(frame, text="Browse file", command=self.browse_input_file).grid(row=1, column=2, sticky="ew", padx=8, pady=3)
        ttk.Button(frame, text="Browse folder", command=self.browse_input_folder).grid(row=2, column=2, sticky="ew", padx=8, pady=3)

        note = ttk.Label(frame, text="Use a .ply file for one model, or a folder for batch rendering.")
        note.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=3)
        return frame

    def _build_output_frame(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Output")
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Output folder:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        entry = ttk.Entry(frame, textvariable=self.output_path_var)
        entry.grid(row=0, column=1, sticky="ew", padx=8, pady=6)
        entry.bind("<KeyRelease>", lambda _e: self.update_command_preview())
        ttk.Button(frame, text="Browse", command=self.browse_output_folder).grid(row=0, column=2, padx=8, pady=6)
        ttk.Button(frame, text="Open", command=self.open_output_folder).grid(row=0, column=3, padx=8, pady=6)
        return frame

    def _build_sampling_frame(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Main render settings")
        for column in range(8):
            frame.columnconfigure(column, weight=0)
        frame.columnconfigure(7, weight=1)

        ttk.Label(frame, text="Preset:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        preset = ttk.Combobox(
            frame,
            textvariable=self.preset_var,
            state="readonly",
            values=[
                "Preview 20° / 162 views",
                "Medium 10° / 648 views",
                "Default 2° / 16,200 views",
                "Full 1° / 64,800 views",
                "Custom",
            ],
            width=28,
        )
        preset.grid(row=0, column=1, sticky="w", padx=8, pady=6)
        preset.bind("<<ComboboxSelected>>", self.on_preset_changed)

        ttk.Label(frame, text="Phi step:").grid(row=0, column=2, sticky="e", padx=8, pady=6)
        phi = ttk.Spinbox(frame, from_=1, to=360, textvariable=self.phi_var, width=7, command=self.on_custom_sampling)
        phi.grid(row=0, column=3, sticky="w", padx=8, pady=6)
        phi.bind("<KeyRelease>", lambda _e: self.on_custom_sampling())
        ToolTip(phi, "Azimuth gap in degrees around the model. Smaller values create more images.")

        ttk.Label(frame, text="Theta step:").grid(row=0, column=4, sticky="e", padx=8, pady=6)
        theta = ttk.Spinbox(frame, from_=1, to=180, textvariable=self.theta_var, width=7, command=self.on_custom_sampling)
        theta.grid(row=0, column=5, sticky="w", padx=8, pady=6)
        theta.bind("<KeyRelease>", lambda _e: self.on_custom_sampling())
        ToolTip(theta, "Polar-angle gap in degrees from top to bottom. Smaller values create more images.")

        ttk.Label(frame, text="Image size:").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        width = ttk.Combobox(frame, textvariable=self.width_var, values=[256, 512, 768, 1024], width=8)
        width.grid(row=1, column=1, sticky="w", padx=(8, 2), pady=6)
        width.bind("<<ComboboxSelected>>", lambda _e: self.update_command_preview())
        width.bind("<KeyRelease>", lambda _e: self.update_command_preview())
        ttk.Label(frame, text="×").grid(row=1, column=2, sticky="w")
        height = ttk.Combobox(frame, textvariable=self.height_var, values=[256, 512, 768, 1024], width=8)
        height.grid(row=1, column=3, sticky="w", padx=(2, 8), pady=6)
        height.bind("<<ComboboxSelected>>", lambda _e: self.update_command_preview())
        height.bind("<KeyRelease>", lambda _e: self.update_command_preview())

        self.estimate_label = ttk.Label(frame, text="")
        self.estimate_label.grid(row=1, column=4, columnspan=4, sticky="w", padx=8, pady=6)
        return frame

    def _build_classification_frame(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Classification")
        frame.columnconfigure(2, weight=1)

        ttk.Label(frame, text="Mode:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        mode = ttk.Combobox(
            frame,
            textvariable=self.class_mode_var,
            state="readonly",
            width=20,
            values=["Unclassified", "Manual label", "From parent folder", "Labels CSV"],
        )
        mode.grid(row=0, column=1, sticky="w", padx=8, pady=6)
        mode.bind("<<ComboboxSelected>>", lambda _e: self.update_command_preview())

        ttk.Label(frame, text="Manual label:").grid(row=0, column=2, sticky="e", padx=8, pady=6)
        manual = ttk.Entry(frame, textvariable=self.classification_var, width=24)
        manual.grid(row=0, column=3, sticky="w", padx=8, pady=6)
        ToolTip(manual, "Typing a label here automatically switches mode to 'Manual label'. Example: figurine, pottery_shard, rim_fragment.")

        ttk.Label(frame, text="Labels CSV:").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        csv_entry = ttk.Entry(frame, textvariable=self.labels_csv_var)
        csv_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=8, pady=6)
        csv_entry.bind("<KeyRelease>", lambda _e: self.update_command_preview())
        ttk.Button(frame, text="Browse", command=self.browse_labels_csv).grid(row=1, column=4, padx=8, pady=6)
        return frame

    def _build_common_flags_frame(self, parent: ttk.Frame) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="Run options")
        cb1 = ttk.Checkbutton(frame, text="Dry run only", variable=self.dry_run_var, command=self.update_command_preview)
        cb1.grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ToolTip(cb1, "Preview the planned render count and output paths without creating PNG files.")

        cb2 = ttk.Checkbutton(frame, text="Overwrite existing PNGs", variable=self.overwrite_var, command=self.update_command_preview)
        cb2.grid(row=0, column=1, sticky="w", padx=8, pady=6)
        ToolTip(cb2, "If unchecked, existing PNGs are reused so interrupted runs can resume.")

        cb3 = ttk.Checkbutton(frame, text="No recursive folder search", variable=self.no_recursive_var, command=self.update_command_preview)
        cb3.grid(row=0, column=2, sticky="w", padx=8, pady=6)
        ToolTip(cb3, "When input is a folder, search only that folder and not its subfolders.")
        return frame

    def _build_advanced_toggle(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent)
        self.advanced_button = ttk.Button(frame, text="Show advanced settings", command=self.toggle_advanced)
        self.advanced_button.pack(anchor="w")
        return frame

    def _build_advanced_frame(self) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(self.advanced_container, text="Advanced settings")
        for column in range(8):
            frame.columnconfigure(column, weight=1 if column in {1, 3, 5, 7} else 0)

        ttk.Label(frame, text="FOV:").grid(row=0, column=0, sticky="e", padx=8, pady=6)
        fov = ttk.Entry(frame, textvariable=self.fov_var, width=10)
        fov.grid(row=0, column=1, sticky="w", padx=8, pady=6)
        fov.bind("<KeyRelease>", lambda _e: self.update_command_preview())
        ToolTip(fov, "Vertical camera field of view in degrees. Default: 45. Higher values show more perspective distortion.")

        ttk.Label(frame, text="Margin:").grid(row=0, column=2, sticky="e", padx=8, pady=6)
        margin = ttk.Entry(frame, textvariable=self.margin_var, width=10)
        margin.grid(row=0, column=3, sticky="w", padx=8, pady=6)
        margin.bind("<KeyRelease>", lambda _e: self.update_command_preview())
        ToolTip(margin, "Camera-distance safety multiplier. Default: 1.08. Increase if the model is clipped.")

        ttk.Label(frame, text="Point size:").grid(row=0, column=4, sticky="e", padx=8, pady=6)
        point = ttk.Entry(frame, textvariable=self.point_size_var, width=10)
        point.grid(row=0, column=5, sticky="w", padx=8, pady=6)
        point.bind("<KeyRelease>", lambda _e: self.update_command_preview())
        ToolTip(point, "Only affects point-cloud PLY files. Triangle meshes ignore this visually.")

        ttk.Label(frame, text="Backend:").grid(row=0, column=6, sticky="e", padx=8, pady=6)
        backend = ttk.Combobox(
            frame,
            textvariable=self.renderer_backend_var,
            state="readonly",
            values=["auto", "visualizer", "offscreen"],
            width=12,
        )
        backend.grid(row=0, column=7, sticky="w", padx=8, pady=6)
        backend.bind("<<ComboboxSelected>>", lambda _e: self.update_command_preview())
        ToolTip(backend, "Use auto normally. On Windows, auto uses the hidden Visualizer backend.")

        ttk.Label(frame, text="Background RGBA:").grid(row=1, column=0, sticky="e", padx=8, pady=6)
        bg = ttk.Entry(frame, textvariable=self.background_var, width=18)
        bg.grid(row=1, column=1, columnspan=2, sticky="w", padx=8, pady=6)
        bg.bind("<KeyRelease>", lambda _e: self.update_command_preview())
        ToolTip(bg, "Four numbers from 0 to 1. Example: 1 1 1 1 for white.")

        ttk.Label(frame, text="Base color RGBA:").grid(row=1, column=3, sticky="e", padx=8, pady=6)
        base = ttk.Entry(frame, textvariable=self.base_color_var, width=18)
        base.grid(row=1, column=4, columnspan=2, sticky="w", padx=8, pady=6)
        base.bind("<KeyRelease>", lambda _e: self.update_command_preview())
        ToolTip(base, "Used when the PLY has no vertex colors. Four numbers from 0 to 1.")

        ttk.Label(frame, text="Progress every:").grid(row=1, column=6, sticky="e", padx=8, pady=6)
        progress = ttk.Entry(frame, textvariable=self.progress_every_var, width=10)
        progress.grid(row=1, column=7, sticky="w", padx=8, pady=6)
        progress.bind("<KeyRelease>", lambda _e: self.update_command_preview())
        ToolTip(progress, "Print progress and flush the manifest every N images. Default: 500.")

        hash_cb = ttk.Checkbutton(frame, text="Hash source PLY", variable=self.hash_source_var, command=self.update_command_preview)
        hash_cb.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=6)
        ToolTip(hash_cb, "Adds SHA-256 of each source PLY to the manifest. Useful for reproducibility, slower for huge files.")

        headless_cb = ttk.Checkbutton(frame, text="Linux headless CPU mode", variable=self.headless_cpu_var, command=self.update_command_preview)
        headless_cb.grid(row=2, column=2, columnspan=3, sticky="w", padx=8, pady=6)
        ToolTip(headless_cb, "For supported headless Linux Open3D setups. Do not use this on Windows.")
        return frame

    def _build_log_frame(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        ttk.Label(frame, text="Command preview:").grid(row=0, column=0, sticky="w")
        self.command_text = tk.Text(frame, height=4, wrap="word", font=("Consolas", 10))
        self.command_text.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.command_text.configure(state="disabled")

        self.log_frame = ttk.LabelFrame(frame, text="Renderer log")
        self.log_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self.log_frame)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(4, 2))
        toolbar.columnconfigure(0, weight=1)

        self.log_toggle_button = ttk.Button(toolbar, text="Collapse log", command=self.toggle_log_panel)
        self.log_toggle_button.grid(row=0, column=1, padx=4)
        ttk.Button(toolbar, text="Open large log window", command=self.open_large_log_window).grid(row=0, column=2, padx=4)

        self.log_body = ttk.Frame(self.log_frame)
        self.log_body.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.log_body.columnconfigure(0, weight=1)
        self.log_body.rowconfigure(0, weight=1)

        self.log_text = tk.Text(self.log_body, height=22, wrap="word", font=("Consolas", 10))
        scroll = ttk.Scrollbar(self.log_body, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        return frame

    def _build_buttons(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        self.run_button = ttk.Button(frame, text="Run renderer", command=self.run_renderer)
        self.run_button.grid(row=0, column=1, padx=4)
        self.stop_button = ttk.Button(frame, text="Stop", command=self.stop_renderer, state="disabled")
        self.stop_button.grid(row=0, column=2, padx=4)
        ttk.Button(frame, text="Copy command", command=self.copy_command).grid(row=0, column=3, padx=4)
        ttk.Button(frame, text="Clear log", command=self.clear_log).grid(row=0, column=4, padx=4)
        return frame

    def append_log(self, text: str) -> None:
        self.log_text.insert("end", text)
        self.log_text.see("end")
        for log_window in list(self.log_popouts):
            try:
                log_window.configure(state="normal")
                log_window.insert("end", text)
                log_window.see("end")
                log_window.configure(state="disabled")
            except tk.TclError:
                self.log_popouts.remove(log_window)

    def clear_log(self) -> None:
        self.log_text.delete("1.0", "end")
        for log_window in list(self.log_popouts):
            try:
                log_window.configure(state="normal")
                log_window.delete("1.0", "end")
                log_window.configure(state="disabled")
            except tk.TclError:
                self.log_popouts.remove(log_window)

    def toggle_log_panel(self) -> None:
        if self.log_visible.get():
            self.log_body.grid_remove()
            self.log_frame.rowconfigure(1, weight=0)
            self.log_visible.set(False)
            self.log_toggle_button.configure(text="Expand log")
        else:
            self.log_body.grid()
            self.log_frame.rowconfigure(1, weight=1)
            self.log_visible.set(True)
            self.log_toggle_button.configure(text="Collapse log")

    def open_large_log_window(self) -> None:
        window = tk.Toplevel(self)
        window.title("Expanded renderer log")
        window.geometry("1100x700")
        window.minsize(800, 500)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        text = tk.Text(window, wrap="word", font=("Consolas", 10))
        scroll = ttk.Scrollbar(window, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        text.insert("1.0", self.log_text.get("1.0", "end"))
        text.configure(state="disabled")
        self.log_popouts.append(text)

        def on_close() -> None:
            if text in self.log_popouts:
                self.log_popouts.remove(text)
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", on_close)

    def refresh_models(self) -> None:
        self.model_choices = scan_models()
        self.choice_by_label = {choice.label: choice for choice in self.model_choices}
        labels = list(self.choice_by_label.keys())
        self.model_combo.configure(values=labels)
        if labels and not self.input_path_var.get():
            self.model_choice_var.set(labels[0])
            self.input_path_var.set(str(self.choice_by_label[labels[0]].path))
        self.update_command_preview()

    def on_model_choice(self, _event: tk.Event | None = None) -> None:
        choice = self.choice_by_label.get(self.model_choice_var.get())
        if choice is not None:
            self.input_path_var.set(str(choice.path))
        self.update_command_preview()

    def browse_input_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose a PLY model",
            initialdir=str(MODELS_DIR if MODELS_DIR.exists() else ROOT),
            filetypes=[("PLY models", "*.ply"), ("All files", "*.*")],
        )
        if path:
            self.input_path_var.set(path)
            self.model_choice_var.set("")
            self.update_command_preview()

    def browse_input_folder(self) -> None:
        path = filedialog.askdirectory(title="Choose a folder containing PLY models", initialdir=str(MODELS_DIR))
        if path:
            self.input_path_var.set(path)
            self.model_choice_var.set("")
            self.update_command_preview()

    def browse_output_folder(self) -> None:
        path = filedialog.askdirectory(title="Choose output folder", initialdir=str(DEFAULT_OUTPUT))
        if path:
            self.output_path_var.set(path)
            self.update_command_preview()

    def browse_labels_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose labels CSV",
            initialdir=str(ROOT),
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.labels_csv_var.set(path)
            self.class_mode_var.set("Labels CSV")
            self.update_command_preview()

    def on_manual_label_changed(self, *_args: object) -> None:
        """Switch classification mode to Manual label whenever the manual label field is filled."""
        if self.classification_var.get().strip() and self.class_mode_var.get() != "Manual label":
            self.class_mode_var.set("Manual label")
        self.update_command_preview()

    def open_output_folder(self) -> None:
        output = Path(self.output_path_var.get().strip() or DEFAULT_OUTPUT)
        if not output.is_absolute():
            output = ROOT / output
        try:
            output.mkdir(parents=True, exist_ok=True)
            open_path(output)
        except OSError as exc:
            messagebox.showerror("Could not open output folder", str(exc))

    def on_preset_changed(self, _event: tk.Event | None = None) -> None:
        preset = self.preset_var.get()
        if preset.startswith("Preview"):
            self.phi_var.set(20)
            self.theta_var.set(20)
        elif preset.startswith("Medium"):
            self.phi_var.set(10)
            self.theta_var.set(10)
        elif preset.startswith("Default"):
            self.phi_var.set(2)
            self.theta_var.set(2)
        elif preset.startswith("Full"):
            self.phi_var.set(1)
            self.theta_var.set(1)
        self.update_command_preview()

    def on_custom_sampling(self) -> None:
        current = (self.phi_var.get(), self.theta_var.get())
        presets = {(20, 20): "Preview 20° / 162 views", (10, 10): "Medium 10° / 648 views", (2, 2): "Default 2° / 16,200 views", (1, 1): "Full 1° / 64,800 views"}
        self.preset_var.set(presets.get(current, "Custom"))
        self.update_command_preview()

    def toggle_advanced(self) -> None:
        if self.advanced_visible.get():
            for child in self.advanced_container.winfo_children():
                child.destroy()
            self.advanced_visible.set(False)
            self.advanced_button.configure(text="Show advanced settings")
        else:
            self._build_advanced_frame().pack(fill="x")
            self.advanced_visible.set(True)
            self.advanced_button.configure(text="Hide advanced settings")

    def build_command(self) -> list[str]:
        input_text = self.input_path_var.get().strip()
        output_text = self.output_path_var.get().strip()
        if not input_text:
            raise ValueError("Choose an input PLY file or folder.")
        if not output_text:
            raise ValueError("Choose an output folder.")
        if not RENDERER.is_file():
            raise FileNotFoundError(f"Renderer script not found: {RENDERER}")

        input_path = Path(input_text)
        output_path = Path(output_text)
        if not input_path.is_absolute():
            input_path = ROOT / input_path
        if not output_path.is_absolute():
            output_path = ROOT / output_path

        phi = int(self.phi_var.get())
        theta = int(self.theta_var.get())
        width = int(self.width_var.get())
        height = int(self.height_var.get())
        if not 1 <= phi <= 360:
            raise ValueError("Phi step must be between 1 and 360.")
        if not 1 <= theta <= 180:
            raise ValueError("Theta step must be between 1 and 180.")
        if width <= 0 or height <= 0:
            raise ValueError("Image width and height must be positive.")

        args = [
            sys.executable,
            str(RENDERER),
            str(input_path),
            str(output_path),
            "-phi",
            str(phi),
            "-theta",
            str(theta),
            "--width",
            str(width),
            "--height",
            str(height),
        ]

        mode = self.class_mode_var.get()
        if mode == "Manual label":
            label = self.classification_var.get().strip()
            if not label:
                raise ValueError("Classification mode is 'Manual label', but no label was entered.")
            args.extend(["--classification", label])
        elif mode == "From parent folder":
            args.append("--class-from-parent")
        elif mode == "Labels CSV":
            csv_path = self.labels_csv_var.get().strip()
            if not csv_path:
                raise ValueError("Classification mode is 'Labels CSV', but no CSV file was selected.")
            args.extend(["--labels-csv", csv_path])

        if self.overwrite_var.get():
            args.append("--overwrite")
        if self.dry_run_var.get():
            args.append("--dry-run")
        if self.no_recursive_var.get():
            args.append("--no-recursive")

        # Advanced values are included even when the panel is hidden because they have stable defaults.
        args.extend(["--fov", str(float(self.fov_var.get()))])
        args.extend(["--margin", str(float(self.margin_var.get()))])
        args.extend(["--point-size", str(float(self.point_size_var.get()))])
        args.extend(["--progress-every", str(int(self.progress_every_var.get()))])
        args.extend(["--renderer-backend", self.renderer_backend_var.get()])

        bg = self._parse_rgba(self.background_var.get(), "background")
        base = self._parse_rgba(self.base_color_var.get(), "base color")
        args.extend(["--background", *bg])
        args.extend(["--base-color", *base])

        if self.hash_source_var.get():
            args.append("--hash-source")
        if self.headless_cpu_var.get():
            args.append("--headless-cpu")

        return args

    def _parse_rgba(self, value: str, label: str) -> list[str]:
        parts = value.replace(",", " ").split()
        if len(parts) != 4:
            raise ValueError(f"{label} RGBA must contain exactly four numbers, e.g. 1 1 1 1.")
        floats = [float(part) for part in parts]
        if any(number < 0 or number > 1 for number in floats):
            raise ValueError(f"{label} RGBA values must be between 0 and 1.")
        return [str(number) for number in floats]

    def update_command_preview(self) -> None:
        try:
            command = self.build_command()
            preview = subprocess.list2cmdline(command) if platform.system() == "Windows" else " ".join(command)
            phi = int(self.phi_var.get())
            theta = int(self.theta_var.get())
            estimate = (360 + phi - 1) // phi * ((180 + theta - 1) // theta)
            self.estimate_label.configure(text=f"Estimated views per model: {estimate:,}")
        except Exception as exc:
            preview = f"Cannot build command yet: {exc}"
            self.estimate_label.configure(text="")

        self.command_text.configure(state="normal")
        self.command_text.delete("1.0", "end")
        self.command_text.insert("1.0", preview)
        self.command_text.configure(state="disabled")

    def copy_command(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.command_text.get("1.0", "end").strip())

    def run_renderer(self) -> None:
        if self.process is not None:
            messagebox.showwarning("Renderer already running", "Stop the current run before starting another one.")
            return
        try:
            command = self.build_command()
        except Exception as exc:
            messagebox.showerror("Cannot start renderer", str(exc))
            return

        output_path = Path(self.output_path_var.get().strip() or DEFAULT_OUTPUT)
        if not output_path.is_absolute():
            output_path = ROOT / output_path
        output_path.mkdir(parents=True, exist_ok=True)

        self.append_log("\n=== Starting renderer ===\n")
        self.append_log(subprocess.list2cmdline(command) + "\n\n")

        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

        creationflags = 0
        if platform.system() == "Windows":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creationflags,
            )
        except Exception as exc:
            self.process = None
            self.run_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            messagebox.showerror("Failed to start renderer", str(exc))
            return

        self.reader_thread = threading.Thread(target=self._read_process_output, daemon=True)
        self.reader_thread.start()

    def _read_process_output(self) -> None:
        assert self.process is not None
        if self.process.stdout is not None:
            for line in self.process.stdout:
                self.output_queue.put(line)
        return_code = self.process.wait()
        self.output_queue.put(f"\n=== Renderer exited with code {return_code} ===\n")
        self.output_queue.put("__PROCESS_FINISHED__")

    def _poll_output_queue(self) -> None:
        try:
            while True:
                line = self.output_queue.get_nowait()
                if line == "__PROCESS_FINISHED__":
                    self.process = None
                    self.run_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    continue
                self.append_log(line)
        except queue.Empty:
            pass
        self.after(100, self._poll_output_queue)

    def stop_renderer(self) -> None:
        if self.process is None:
            return
        self.append_log("\n=== Stop requested ===\n")
        try:
            self.process.terminate()
        except Exception as exc:
            self.append_log(f"Could not terminate process: {exc}\n")

    def show_renderer_help(self) -> None:
        if not RENDERER.is_file():
            messagebox.showerror("Renderer missing", f"Could not find {RENDERER}")
            return
        try:
            completed = subprocess.run([sys.executable, str(RENDERER), "--help"], text=True, capture_output=True, check=False)
        except Exception as exc:
            messagebox.showerror("Failed to run renderer help", str(exc))
            return
        help_window = tk.Toplevel(self)
        help_window.title("Renderer help")
        help_window.geometry("900x650")
        text = tk.Text(help_window, wrap="word")
        scroll = ttk.Scrollbar(help_window, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text.insert("1.0", completed.stdout or completed.stderr)
        text.configure(state="disabled")

    def show_about(self) -> None:
        messagebox.showinfo(
            "About",
            f"PLY Spherical Renderer GUI {APP_VERSION}\n\n"
            f"Project root:\n{ROOT}\n\n"
            "This GUI builds and runs commands for ply_spherical_renderer_windows.py.",
        )


def main() -> int:
    if not RENDERER.is_file():
        messagebox.showerror(
            "Renderer script missing",
            f"Expected to find:\n{RENDERER}\n\n"
            "Place renderer_gui.py inside the renderer folder of the starter kit.",
        )
        return 2
    app = RendererGUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
