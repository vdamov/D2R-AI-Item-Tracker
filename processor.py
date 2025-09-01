"""Worker thread for processing images in D2R AI Item Tracker."""

import queue
import threading
from pathlib import Path
from typing import List

import cv2

from api import call_vision_api
from utils import clean_output


class Processor(threading.Thread):
    """Worker thread for processing screenshot images."""

    def __init__(
        self, params: dict, log_q: queue.Queue, progress_cb, done_cb, stop_flag
    ):
        super().__init__(daemon=True)
        self.p = params
        self.log_q = log_q
        self.progress_cb = progress_cb
        self.done_cb = done_cb
        self.stop_flag = stop_flag

    def log(self, msg):
        """Add message to log queue."""
        self.log_q.put(msg)

    def run(self):
        """Main processing loop."""
        try:
            folder = Path(self.p["folder"])
            exts = (".png", ".jpg", ".jpeg")
            paths: List[str] = []
            for ext in exts:
                paths.extend([str(p) for p in folder.glob(f"*{ext}")])
            paths.sort()

            if not paths:
                self.log("[!] No images found in folder.")
                self.done_cb("")
                return

            min_gap = 60.0 / max(1, int(self.p["RATE_LIMIT_RPM"]))
            jitter_s = int(self.p["RATE_JITTER_MS"]) / 1000.0
            last_ts_holder = {"t": 0.0}

            outputs = []
            total = len(paths)
            for idx, pth in enumerate(paths, 1):
                if self.stop_flag["stop"]:
                    self.log("[x] Stopped by user.")
                    break

                base = Path(pth).name
                try:
                    img = cv2.imread(pth)
                    if img is None:
                        raise RuntimeError("Cannot read image")

                    raw, usage = call_vision_api(
                        img,
                        self.p["VISION_ENDPOINT"],
                        self.p["VISION_MODEL"],
                        self.p["VISION_API_KEY"],
                        int(self.p["MAX_RETRIES"]),
                        int(self.p["RETRY_DELAY"]),
                        int(self.p["REQUEST_TIMEOUT"]),
                        min_gap,
                        jitter_s,
                        last_ts_holder,
                    )
                    cleaned, category = clean_output(raw)
                    # Include category in the output for the Item List tab to parse later
                    full_output = (
                        f"{cleaned}\n[CATEGORY: {category}]" if cleaned else ""
                    )
                    outputs.append(full_output)
                    self.log(f"[ok] {base} ({len(cleaned)} chars, {category})")
                    if usage:
                        pt = usage.get("prompt_tokens", "?")
                        ct = usage.get("completion_tokens", "?")
                        tt = usage.get("total_tokens", "?")
                        self.log(
                            f"    ↳ tokens: prompt={pt}, completion={ct}, total={tt}"
                        )
                except Exception as e:
                    outputs.append("")  # Add empty string to maintain order
                    self.log(f"[err] {base} -> {e}")

                self.progress_cb(idx, total)

            # Filter out empty outputs before joining
            valid_outputs = [output for output in outputs if output.strip()]
            content = "\n---\n".join(valid_outputs)
            self.done_cb(content)
        except Exception as e:
            self.log(f"[fatal] {e}")
            self.done_cb("")
