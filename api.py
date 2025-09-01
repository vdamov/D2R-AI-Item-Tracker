"""Vision API functionality for D2R AI Item Tracker."""

import base64
import json
import time
from io import BytesIO
from typing import Tuple

import cv2
import numpy as np
import requests
from PIL import Image

from config import SYSTEM_PROMPT, USER_PROMPT
from utils import rate_limit_wait


def encode_image_to_data_uri(img_bgr: np.ndarray) -> str:
    """Convert BGR image to base64 data URI."""
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    buf = BytesIO()
    pil_img.save(buf, format="PNG")
    b64_str = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64_str}"


def call_vision_api(
    img_bgr: np.ndarray,
    endpoint: str,
    model: str,
    api_key: str,
    max_retries: int,
    retry_delay: int,
    request_timeout: int,
    min_gap: float,
    jitter_s: float,
    last_ts_holder: dict,
) -> Tuple[str, dict]:
    """Call vision API to extract text from image."""
    rate_limit_wait(last_ts_holder, min_gap, jitter_s)
    if not api_key:
        raise ValueError("API key is missing.")

    data_uri = encode_image_to_data_uri(img_bgr)
    payload = {
        "model": model,
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
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    for attempt in range(max_retries):
        try:
            r = requests.post(
                endpoint,
                headers=headers,
                data=json.dumps(payload),
                timeout=request_timeout,
            )
            r.raise_for_status()
            obj = r.json()
            text = obj["choices"][0]["message"]["content"]
            usage = obj.get("usage", {})
            return (text or "").strip(), usage
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(retry_delay * (attempt + 1))
        except (KeyError, IndexError) as e:
            # Surface raw response in GUI log helps debugging
            raise RuntimeError(f"Bad API response format: {e}")
    return "", {}
