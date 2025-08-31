import os
import sys
import glob
import base64
import json
import time
from typing import List

import cv2
import numpy as np
import requests
from PIL import Image
from io import BytesIO

from dotenv import load_dotenv

load_dotenv()

OPENAI_ENDPOINT = os.getenv(
    "VISION_ENDPOINT", "https://api.groq.com/openai/v1/chat/completions"
)
# OpenAI-compatible model name (as exposed by your server)
OPENAI_MODEL = os.getenv(
    "VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
)  # e.g., "llava", "moondream", "florence"
# Optional API key (if your server requires it)
API_KEY = os.getenv("VISION_API_KEY", "gsk_123")

# Prompt to steer the vision model
SYSTEM_PROMPT = (
    "You are an OCR-style vision assistant. Read ONLY the item tooltip text in the image. "
    "Return the text as it appears, preserving line breaks, without extra commentary. "
    "Do NOT include the bottom control-hint lines such as 'Shift + Left Click to Unequip' or "
    "'Ctrl + Left Click to Move'. "
    "If the item is part of a set, do NOT include the list of other set items "
    "that always appears at the very bottom (e.g., 'NAI'S ANCIENT VESTIGE ...'). "
    "Only return the actual stats and description of the currently hovered item."
)
USER_PROMPT = "Extract the exact text content from this item tooltip. Only output the text, no explanations."

# Retry policy
MAX_RETRIES = 3
RETRY_DELAY = 10  # seconds


# =========================
# Utilities
# =========================
def load_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise RuntimeError(f"Cannot read image: {path}")
    return img


def encode_png_bytes(img_bgr: np.ndarray) -> bytes:
    # Convert BGR to RGB for PIL
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    buf = BytesIO()
    pil_img.save(buf, format="PNG")
    return buf.getvalue()


def to_data_uri_png(img_bgr: np.ndarray) -> str:
    b = encode_png_bytes(img_bgr)
    return "data:image/png;base64," + base64.b64encode(b).decode("ascii")


# =========================
# OpenAI-compatible adapter
# =========================
def call_openai_vision(img_bgr: np.ndarray) -> str:
    data_uri = to_data_uri_png(img_bgr)
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
    }
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(
                OPENAI_ENDPOINT, headers=headers, data=json.dumps(payload), timeout=120
            )
            r.raise_for_status()
            obj = r.json()
            # OpenAI-compatible response
            text = obj["choices"][0]["message"]["content"]
            return (text or "").strip()
        except Exception as e:
            if attempt == MAX_RETRIES:
                return f""  # keep batch running
            time.sleep(RETRY_DELAY)
    return ""


def clean_output(text: str) -> str:
    banned = [
        "SHIFT + LEFT CLICK TO UNEQUIP",
        "CTRL + LEFT CLICK TO MOVE",
        "SHIFT + LEFT CLICK TO EQUIP",
        "HOLD SHIFT TO COMPARE"
    ]
    lines = [ln for ln in text.splitlines() if ln.strip().upper() not in banned]
    return "\n".join(lines).strip()


# =========================
# Router
# =========================
def vision_extract(img_bgr: np.ndarray) -> str:
    raw_text = call_openai_vision(img_bgr)
    cleaned = clean_output(raw_text)
    return cleaned


# =========================
# Batch
# =========================
def process_folder(folder: str, exts=(".png", ".jpg", ".jpeg")) -> str:
    paths: List[str] = []
    for ext in exts:
        paths.extend(glob.glob(os.path.join(folder, f"*{ext}")))
    paths.sort()
    outputs: List[str] = []
    for p in paths:
        try:
            img = load_image(p)
            text = vision_extract(img)
            outputs.append(text.strip())
            print(f"[ok] {os.path.basename(p)} ({len(text)} chars)")
        except Exception as e:
            print(f"[err] {os.path.basename(p)} -> {e}")
            outputs.append("")
    return "\n---\n".join(outputs)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python d2r_tooltip_vision_client.py <folder_with_images> [output.txt]"
        )
        sys.exit(1)
    folder = sys.argv[1]
    result = process_folder(folder)
    if len(sys.argv) >= 3:
        out_path = sys.argv[2]
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Saved to: {out_path}")
    else:
        print("\n===== CONCATENATED OUTPUT =====\n")
        print(result)
