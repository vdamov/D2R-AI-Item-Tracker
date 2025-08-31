import base64
from io import BytesIO
import os
import sys
import glob
import json
import time as _time
from PIL import Image
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np
import requests
from tqdm import tqdm

import threading
import random
import time as _t

from dotenv import load_dotenv

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    _TK_OK = True
except Exception:
    _TK_OK = False

load_dotenv()

# --- Configuration ---
OPENAI_ENDPOINT = os.getenv(
    "VISION_ENDPOINT", "https://api.openai.com/v1/chat/completions"
)
OPENAI_MODEL = os.getenv("VISION_MODEL", "gpt-4o")
API_KEY = os.getenv("VISION_API_KEY")

# --- Rate limit config (env overrides) ---
RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", 30))  # e.g., ~30 RPM
RATE_JITTER_MS = int(os.getenv("RATE_JITTER_MS", 200))  # random jitter to avoid bursts

SYSTEM_PROMPT = (
    "You are an OCR-style vision assistant. Read ONLY the item tooltip text in the image. "
    "Return the text as it appears, preserving line breaks, without extra commentary. "
    "Do NOT include the bottom control-hint lines such as 'Shift + Left Click to Unequip' or "
    "'Ctrl + Left Click to Move'. "
    "If the item is part of a set, do NOT include the list of other set items "
    "that always appears at the very bottom (e.g., 'NAJ'S ANCIENT VESTIGE, TAL RASHA'S WRAPPINGS ...'). "
    "Only return the actual stats and description of the currently hovered item."
)
USER_PROMPT = "Extract the exact text content from this item tooltip. Only output the text, no explanations."

# Retry & Network Policy
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", 10))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 120))

# Concurrency
MAX_WORKERS = int(os.getenv("MAX_WORKERS", 1))

_min_gap = 60.0 / max(1, RATE_LIMIT_RPM)  # seconds between requests
_last_ts = 0.0
_rl_lock = threading.Lock()


# =========================
# Vision API Communication
# =========================
def call_vision_api(img_bgr: np.ndarray) -> str:
    """Sends the screenshot to the Vision LLM and returns the text."""
    rate_limit_wait()
    if not API_KEY:
        raise ValueError(
            "API key is not set. Please set VISION_API_KEY in your .env file."
        )
    data_uri = encode_image_to_data_uri(img_bgr)
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
        "temperature": 0.0,
        "max_tokens": 1024,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(
                OPENAI_ENDPOINT,
                headers=headers,
                data=json.dumps(payload),
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            obj = r.json()
            text = obj["choices"][0]["message"]["content"]
            return (text or "").strip()
        except requests.exceptions.RequestException as e:
            print(
                f"\nNetwork error on attempt {attempt + 1}/{MAX_RETRIES}: {e}",
                file=sys.stderr,
            )
            if attempt == MAX_RETRIES - 1:
                raise
            _time.sleep(RETRY_DELAY * (attempt + 1))
        except (KeyError, IndexError) as e:
            print(
                f"Error parsing API response: {e}. Response: {r.text}", file=sys.stderr
            )
            raise
    return ""


def rate_limit_wait():
    """Sleep to respect RPM across threads; add small jitter."""
    global _last_ts
    with _rl_lock:
        now = _t.monotonic()
        wait = (_last_ts + _min_gap) - now
        if wait > 0:
            _t.sleep(wait)
            now = _t.monotonic()
        # add tiny jitter so multiple workers don't align
        now += random.uniform(0, RATE_JITTER_MS / 1000.0)
        _last_ts = now


def encode_image_to_data_uri(img_bgr: np.ndarray) -> str:
    """Encodes a CV2 image to a base64 data URI."""
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    buf = BytesIO()
    pil_img.save(buf, format="PNG")
    b64_str = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64_str}"


def clean_output(text: str) -> str:
    """Removes common UI hint lines from the OCR output."""
    banned = {
        "SHIFT + LEFT CLICK TO UNEQUIP",
        "CTRL + LEFT CLICK TO MOVE",
        "SHIFT + LEFT CLICK TO EQUIP",
        "HOLD SHIFT TO COMPARE",
        "LEFT CLICK TO CAST",
    }
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.upper() in banned:
            continue
        lines.append(s)
    return "\n".join(lines)


# =========================
# Main Logic
# =========================
def process_image(path: str) -> Tuple[str, str]:
    """Loads and extracts text from a single image."""
    try:
        img_full = cv2.imread(path)
        if img_full is None:
            raise RuntimeError("Cannot read image file")

        raw_text = call_vision_api(img_full)
        cleaned_text = clean_output(raw_text)
        return os.path.basename(path), cleaned_text
    except Exception as e:
        return os.path.basename(path), f"ERROR: {e}"


def batch_process_folder(folder: str, exts=(".png", ".jpg", ".jpeg")) -> str:
    """Processes all images in a folder concurrently."""
    paths: List[str] = []
    for ext in exts:
        paths.extend(glob.glob(os.path.join(folder, f"*{ext}")))
    paths.sort()

    if not paths:
        print(f"No images found in folder: {folder}")
        return ""

    results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_path = {executor.submit(process_image, path): path for path in paths}
        pbar = tqdm(
            as_completed(future_to_path), total=len(paths), desc="Processing images"
        )
        for future in pbar:
            path = future_to_path[future]
            try:
                basename, text = future.result()
                results[path] = text
                if "ERROR:" in text:
                    pbar.write(f"\n[err] {basename} -> {text}")
                else:
                    pbar.write(f"\n[ok] {basename} ({len(text)} chars)")
            except Exception as e:
                basename = os.path.basename(path)
                results[path] = f"FATAL ERROR: {e}"
                pbar.write(f"\n[fatal] {basename} -> {e}")

    outputs = [results[p] for p in paths]
    return "\n---\n".join(outputs)


def _pick_folder_gui() -> str:
    """Open a folder picker (for EXE double-click)."""
    if not _TK_OK:
        return ""
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo("D2R AI Item Tracker", "Select your D2R Screenshots folder")
    folder = filedialog.askdirectory(title="Select Screenshots Folder")
    root.destroy()
    return folder or ""


if __name__ == "__main__":
    # CLI path or GUI picker for .exe users
    if len(sys.argv) >= 2:
        folder_path = sys.argv[1]
    else:
        folder_path = _pick_folder_gui()
        if not folder_path:
            print(
                "Usage: python d2r_tooltip_vision_client.py <folder_with_images> [output.txt]"
            )
            sys.exit(1)

    concatenated_result = batch_process_folder(folder_path)

    if len(sys.argv) >= 3:
        out_path = sys.argv[2]
    else:
        out_path = os.path.join(folder_path, "output.txt")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(concatenated_result)
    print(f"\n✅ Saved to: {out_path}")
