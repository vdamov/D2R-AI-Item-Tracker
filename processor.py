"""Worker thread for processing images in D2R AI Item Tracker."""

import queue
import threading
import time
from pathlib import Path
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

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

    def process_single_image(self, pth: str, min_gap: float, jitter_s: float, 
                            last_ts_holder: dict, idx: int, total: int):
        """Process a single image with rate limit handling."""
        base = Path(pth).name
        retry_count = 0
        max_429_retries = 5  # Maximum retries for rate limit errors
        
        while retry_count <= max_429_retries:
            if self.stop_flag["stop"]:
                return None, idx, True  # Stop requested
                
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
                
                self.log(f"[ok] {base} ({len(cleaned)} chars, {category})")
                if usage:
                    pt = usage.get("prompt_tokens", "?")
                    ct = usage.get("completion_tokens", "?")
                    tt = usage.get("total_tokens", "?")
                    self.log(
                        f"    ↳ tokens: prompt={pt}, completion={ct}, total={tt}"
                    )
                
                return full_output, idx, False  # Success, no stop
                
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check if it's a rate limit error (429)
                if "429" in error_msg or "rate" in error_msg or "too many" in error_msg:
                    retry_count += 1
                    if retry_count <= max_429_retries:
                        # Exponential backoff for rate limit errors
                        wait_time = min(60, 5 * (2 ** (retry_count - 1)))
                        self.log(f"[rate limit] {base} -> Waiting {wait_time}s before retry {retry_count}/{max_429_retries}")
                        time.sleep(wait_time)
                        continue
                    else:
                        self.log(f"[FATAL] {base} -> Max rate limit retries exceeded. Stopping process.")
                        return None, idx, True  # Rate limit failure - stop everything
                else:
                    # For non-rate-limit errors, don't retry
                    self.log(f"[err] {base} -> {e}")
                    return "", idx, False  # Regular error, continue with empty output

    def run(self):
        """Main processing loop with parallel workers."""
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

            # Get worker count from params
            max_workers = int(self.p.get("MAX_WORKERS", 1))
            max_workers = max(1, min(10, max_workers))  # Limit between 1 and 10
            
            self.log(f"[info] Starting with {max_workers} worker(s)")
            
            min_gap = 60.0 / max(1, int(self.p["RATE_LIMIT_RPM"]) / max_workers)
            jitter_s = int(self.p["RATE_JITTER_MS"]) / 1000.0
            
            # Use a single shared timestamp holder for rate limiting across workers
            last_ts_holder = {"t": 0.0}
            lock = threading.Lock()
            
            # Thread-safe timestamp holder
            def safe_ts_holder():
                with lock:
                    return last_ts_holder
            
            outputs = [None] * len(paths)  # Pre-allocate to maintain order
            total = len(paths)
            completed_count = 0
            should_stop = False
            
            if max_workers == 1:
                # Single worker mode - process sequentially
                for idx, pth in enumerate(paths):
                    if self.stop_flag["stop"] or should_stop:
                        self.log("[x] Stopped by user or rate limit failure.")
                        break
                    
                    result, _, stop = self.process_single_image(
                        pth, min_gap, jitter_s, last_ts_holder, idx, total
                    )
                    
                    if stop:
                        should_stop = True
                        break
                        
                    outputs[idx] = result if result is not None else ""
                    completed_count += 1
                    self.progress_cb(completed_count, total)
            else:
                # Multi-worker mode with ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # Submit all tasks
                    futures = {
                        executor.submit(
                            self.process_single_image, 
                            pth, min_gap, jitter_s, safe_ts_holder(), idx, total
                        ): idx 
                        for idx, pth in enumerate(paths)
                    }
                    
                    # Process completed tasks
                    for future in as_completed(futures):
                        if self.stop_flag["stop"] or should_stop:
                            # Cancel remaining futures
                            for f in futures:
                                f.cancel()
                            self.log("[x] Stopped by user or rate limit failure.")
                            break
                        
                        idx = futures[future]
                        try:
                            result, _, stop = future.result()
                            if stop:
                                should_stop = True
                                # Cancel remaining futures
                                for f in futures:
                                    if f != future:
                                        f.cancel()
                                break
                                
                            outputs[idx] = result if result is not None else ""
                            completed_count += 1
                            self.progress_cb(completed_count, total)
                        except Exception as e:
                            self.log(f"[err] Worker error: {e}")
                            outputs[idx] = ""
                            completed_count += 1
                            self.progress_cb(completed_count, total)

            # Filter out None values and empty outputs before joining
            valid_outputs = [output for output in outputs if output and output.strip()]
            content = "\n---\n".join(valid_outputs)

            self.done_cb(content)

        except Exception as e:
            self.log(f"[fatal] {e}")
            self.done_cb("")