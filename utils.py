"""Utility functions for D2R AI Item Tracker."""

import os
import re
import sys
import time
import random
from pathlib import Path
from typing import Tuple
import ctypes
import tkinter.font as tkfont

from config import BANNED_LINES


def clean_output(text: str) -> Tuple[str, str]:
    """Clean output and extract category. Returns (cleaned_text, category)"""
    out = []
    category = "MISC"  # Default category

    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.upper() in BANNED_LINES:
            continue

        # Check for category tag
        if s.startswith("[CATEGORY:") and s.endswith("]"):
            category_match = re.search(r"\[CATEGORY:\s*(\w+)\]", s.upper())
            if category_match:
                category = category_match.group(1)
            continue  # Don't include this line in output

        out.append(s)

    return "\n".join(out), category


def ensure_txt_path(
    path: str, default_dir: str, default_name: str = "output.txt"
) -> str:
    """
    Return a normalized .txt file path.
    - If `path` is a folder or empty, append default_name.
    - If parent doesn't exist, create it.
    - Always return a platform-correct path (no mixed slashes).
    """
    p = Path(path) if path else None
    if not p or p.suffix == "" and (p.is_dir() if p else True):
        # If empty OR looks like a folder, use default_dir/default_name
        base = Path(default_dir) if default_dir else Path.cwd()
        p = base / default_name
    if p.suffix == "":
        p = p.with_suffix(".txt")
    # Create parent if missing
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p.resolve())


def save_text_atomic(path: str, content: str) -> str:
    """Atomic write with normalization."""
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(content or "", encoding="utf-8", newline="\n")
    tmp.replace(p)
    return str(p.resolve())


def rate_limit_wait(last_ts_holder: dict, min_gap: float, jitter_s: float):
    """Simple thread-safe rate limiter (GUI runs single worker by default)"""
    now = time.monotonic()
    wait = (last_ts_holder["t"] + min_gap) - now
    if wait > 0:
        time.sleep(wait)
        now = time.monotonic()
    now += random.uniform(0, jitter_s)
    last_ts_holder["t"] = now


def asset_path(rel):
    """Get asset path for bundled applications."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(os.path.dirname(__file__), rel)


def load_fonts():
    """Load custom fonts on Windows."""
    import platform

    # Only register on Windows; other OSes will just use system-installed fonts
    if platform.system() != "Windows":
        return False

    FR_PRIVATE = 0x10
    fonts_added = False
    font_dir = asset_path("assets/fonts")

    fpath = os.path.join(font_dir, "ExocetLight.ttf")
    if os.path.exists(fpath):
        try:
            # Add the font privately for this process
            if ctypes.windll.gdi32.AddFontResourceExW(fpath, FR_PRIVATE, 0) > 0:
                fonts_added = True
        except Exception as e:
            print(f"Couldn't add font ExocetLight.ttf: {e}")

    if fonts_added:
        # Tell apps the font list changed
        HWND_BROADCAST = 0xFFFF
        WM_FONTCHANGE = 0x001D
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_FONTCHANGE, 0, 0, 0, 1000, None
        )

    return fonts_added