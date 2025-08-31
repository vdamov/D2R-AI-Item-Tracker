import base64
from io import BytesIO
import os
import sys
import json
import time
from typing import List, Dict, Tuple
import threading
import queue
import random
import re
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image
from dotenv import load_dotenv

# ---------- GUI ----------
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "D2R AI Item Tracker (GUI)"
DEFAULT_OUTPUT_NAME = "output.txt"

# Load .env if present
load_dotenv()

# -----------------------------
# Settings / defaults
# -----------------------------
DEFAULTS = {
    "VISION_ENDPOINT": os.getenv(
        "VISION_ENDPOINT", "https://api.groq.com/openai/v1/chat/completions"
    ),
    "VISION_MODEL": os.getenv(
        "VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
    ),
    "VISION_API_KEY": os.getenv("VISION_API_KEY", ""),
    "SCREENSHOTS_FOLDER": os.getenv("SCREENSHOTS_FOLDER", ""),
    "OUTPUT_FILE": os.getenv("OUTPUT_FILE", ""),
    "ITEM_LIST_FOLDER": os.getenv("ITEM_LIST_FOLDER", ""),
    "MAX_WORKERS": os.getenv("MAX_WORKERS", "1"),
    "MAX_RETRIES": os.getenv("MAX_RETRIES", "3"),
    "RETRY_DELAY": os.getenv("RETRY_DELAY", "10"),
    "REQUEST_TIMEOUT": os.getenv("REQUEST_TIMEOUT", "120"),
    "RATE_LIMIT_RPM": os.getenv("RATE_LIMIT_RPM", "30"),
    "RATE_JITTER_MS": os.getenv("RATE_JITTER_MS", "200"),
}

SYSTEM_PROMPT = (
    "You are an OCR-style vision assistant. Read ONLY the item tooltip text in the image. "
    "Return the text as it appears, preserving line breaks, without extra commentary. "
    "Do NOT include the bottom control-hint lines such as 'Shift + Left Click to Unequip' or "
    "'Ctrl + Left Click to Move'. "
    "If the item is part of a set, do NOT include the list of other set items "
    "that always appears at the very bottom (e.g., 'NAJ'S ANCIENT VESTIGE, TAL RASHA'S WRAPPINGS ...'). "
    "Only return the actual stats and description of the currently hovered item. "
    "After the item text, add these lines: "
    "[CATEGORY: X] where X is one of: WEAPON, ARMOR, CHARM, RING, AMULET, JEWEL, GEM, RUNE, MISC "
    "[COLOR: #XXXXXX] where XXXXXX is the hex color based on item quality: "
    "White/Gray items: #c7b377, Magic/Blue items: #6969ff, Rare/Yellow items: #ffff64, "
    "Unique/Gold items: #c79c1e, Set/Green items: #00ff00, "
    "Crafted/Orange items: #ff8000, Runes/Gems: #c7b377, Ethereal overlay: #c0c0c0"
)
USER_PROMPT = "Extract the exact text content from this item tooltip. Only output the text, no explanations."

BANNED_LINES = {
    "SHIFT + LEFT CLICK TO UNEQUIP",
    "CTRL + LEFT CLICK TO MOVE",
    "SHIFT + LEFT CLICK TO EQUIP",
    "HOLD SHIFT TO COMPARE",
    "LEFT CLICK TO CAST",
}

# Item quality colors (D2R style)
ITEM_COLORS = {
    "normal": "#c7b377",     # White/Gray
    "magic": "#4169e1",      # Blue
    "rare": "#ffff64",       # Yellow
    "unique": "#A59263",     # Gold
    "set": "#32cd32",        # Green
    "crafted": "#d38b04",    # Orange
    "ethereal": "#c0c0c0",   # Silver/gray overlay
    "rune": "#c7b377",       # Gray
    "gem": "#c7b377",        # Gray
}

# Item categories
ITEM_CATEGORIES = [
    "ALL",
    "WEAPON", 
    "ARMOR", 
    "CHARM", 
    "RING",
    "AMULET", 
    "JEWEL",
    "GEM", 
    "RUNE",
    "MISC"
]


# -----------------------------
# Core logic (API + OCR clean)
# -----------------------------
def encode_image_to_data_uri(img_bgr: np.ndarray) -> str:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    buf = BytesIO()
    pil_img.save(buf, format="PNG")
    b64_str = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64_str}"


def clean_output(text: str) -> Tuple[str, str, str]:
    """Clean output and extract category and color. Returns (cleaned_text, category, color)"""
    out = []
    category = "MISC"  # Default category
    color = "#c7b377"  # Default color (normal/white)
    
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.upper() in BANNED_LINES:
            continue
        
        # Check for category tag
        if s.startswith("[CATEGORY:") and s.endswith("]"):
            category_match = re.search(r'\[CATEGORY:\s*(\w+)\]', s.upper())
            if category_match:
                category = category_match.group(1)
            continue  # Don't include this line in output
        
        # Check for color tag
        if s.startswith("[COLOR:") and s.endswith("]"):
            color_match = re.search(r'\[COLOR:\s*(#[0-9A-Fa-f]{6})\]', s)
            if color_match:
                color = color_match.group(1)
            continue  # Don't include this line in output
            
        out.append(s)
    
    return "\n".join(out), category, color


def ensure_txt_path(path: str, default_dir: str, default_name: str = "output.txt") -> str:
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
    # simple thread-safe limiter (GUI runs single worker by default)
    now = time.monotonic()
    wait = (last_ts_holder["t"] + min_gap) - now
    if wait > 0:
        time.sleep(wait)
        now = time.monotonic()
    now += random.uniform(0, jitter_s)
    last_ts_holder["t"] = now


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
) -> str:
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
            return (text or "").strip()
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(retry_delay * (attempt + 1))
        except (KeyError, IndexError) as e:
            # surface raw response in GUI log helps debugging
            raise RuntimeError(f"Bad API response format: {e}")
    return ""


# -----------------------------
# Item List logic
# -----------------------------
class Item:
    def __init__(self, text: str, source_file: str, category: str = "MISC", color: str = None):
        self.text = text.strip()
        self.source_file = source_file
        self.hero_name = Path(source_file).stem
        self.category = category.upper()
        self.is_ethereal = "ETHEREAL" in self.text.upper()
        
        # These must be at the bottom since they use other properties
        self.item_quality = self._detect_item_quality()
        self.color = color if color else self._get_item_color()
    
    def _detect_item_quality(self) -> str:
        """Detect item quality/rarity from text for color coding"""
        text_upper = self.text.upper()
        
        # Runes are always gray
        if self.category == "RUNE":
            return "rune"
        
        # Gems are always gray  
        if self.category == "GEM":
            return "gem"
        
        # Check for ethereal first (affects color but not quality)
        if "ETHEREAL" in text_upper:
            # Ethereal items keep their base quality but get silver tint
            pass
            
        # Check for specific quality indicators
        if any(word in text_upper for word in ["UNIQUE", "LEGENDARY"]) or text_upper.startswith("UNIQUE"):
            return "unique"
        elif any(word in text_upper for word in ["SET ITEM", "SET:", "SET "]) or "SET" in text_upper:
            return "set"
        elif any(word in text_upper for word in ["CRAFTED", "CRAFT"]):
            return "crafted"
        elif "RARE" in text_upper or (self.category in ["WEAPON", "ARMOR"] and text_upper.count("\n") > 6):
            return "rare"
        elif any(word in text_upper for word in ["MAGIC", "MAGICAL"]) or (text_upper.count("+") > 2):
            return "magic"
        else:
            return "normal"
    
    def _get_item_color(self) -> str:
        """Get the display color for this item"""
        if self.is_ethereal:
            return ITEM_COLORS["ethereal"]
        return ITEM_COLORS.get(self.item_quality, ITEM_COLORS["normal"])


def load_items_from_folder(folder_path: str) -> List[Item]:
    """Load all items from text files in a folder"""
    items = []
    folder = Path(folder_path)
    
    if not folder.exists() or not folder.is_dir():
        return items
    
    for txt_file in folder.glob("*.txt"):
        try:
            content = txt_file.read_text(encoding="utf-8")
            item_texts = content.split("---")
            
            for item_text in item_texts:
                item_text = item_text.strip()
                if not item_text:
                    continue
                
                # Parse category and color if present (from new OCR output)
                category = "MISC"
                color = None
                
                category_match = re.search(r'\[CATEGORY:\s*(\w+)\]', item_text, re.IGNORECASE)
                if category_match:
                    category = category_match.group(1).upper()
                    # Remove category line from display text
                    item_text = re.sub(r'\[CATEGORY:\s*\w+\]', '', item_text, flags=re.IGNORECASE).strip()
                
                color_match = re.search(r'\[COLOR:\s*(#[0-9A-Fa-f]{6})\]', item_text, re.IGNORECASE)
                if color_match:
                    color = color_match.group(1)
                    # Remove color line from display text
                    item_text = re.sub(r'\[COLOR:\s*#[0-9A-Fa-f]{6}\]', '', item_text, flags=re.IGNORECASE).strip()
                
                if item_text:  # Only add if there's actual item text after cleaning
                    items.append(Item(item_text, str(txt_file), category, color))
        except Exception as e:
            print(f"Error reading {txt_file}: {e}")
    
    return items


def fuzzy_search(items: List[Item], query: str, category_filter: str = "ALL") -> List[Item]:
    """Simple fuzzy search through items with category filtering"""
    # First filter by category
    if category_filter != "ALL":
        items = [item for item in items if item.category == category_filter]
    
    if not query.strip():
        return items
    
    query = query.lower()
    results = []
    
    for item in items:
        text_lower = item.text.lower()
        hero_lower = item.hero_name.lower()
        
        # Score based on multiple factors
        score = 0
        
        # Exact matches get highest score
        if query in text_lower:
            score += 100
        if query in hero_lower:
            score += 50
            
        # Partial word matches
        for word in query.split():
            if word in text_lower:
                score += 20
            if word in hero_lower:
                score += 10
        
        if score > 0:
            results.append((score, item))
    
    # Sort by score descending
    results.sort(key=lambda x: x[0], reverse=True)
    return [item for score, item in results]


# -----------------------------
# Worker thread (process loop)
# -----------------------------
class Processor(threading.Thread):
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
        self.log_q.put(msg)

    def run(self):
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

                    raw = call_vision_api(
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
                    cleaned, category, color = clean_output(raw)
                    # Include category and color in the output for the Item List tab to parse later
                    full_output = f"{cleaned}\n[CATEGORY: {category}]\n[COLOR: {color}]" if cleaned else ""
                    outputs.append(full_output)
                    self.log(f"[ok] {base} ({len(cleaned)} chars, {category}, {color})")
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


# -----------------------------
# Item List Tab
# -----------------------------
class ItemListTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.items: List[Item] = []
        self.filtered_items: List[Item] = []
        
        self.var_items_folder = tk.StringVar(value=DEFAULTS["ITEM_LIST_FOLDER"])
        self.var_search = tk.StringVar()
        self.var_category_filter = tk.StringVar(value="ALL")
        
        self.var_search.trace("w", self._on_search_change)
        self.var_category_filter.trace("w", self._on_filter_change)
        
        self._build_ui()
    
    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}
        
        # Folder selection
        frm_folder = ttk.LabelFrame(self, text="Item List Settings")
        frm_folder.pack(fill="x", **pad)
        
        ttk.Label(frm_folder, text="Items folder:").grid(row=0, column=0, sticky="e")
        ttk.Entry(frm_folder, textvariable=self.var_items_folder, width=50).grid(
            row=0, column=1, sticky="we"
        )
        ttk.Button(frm_folder, text="Browse…", command=self._pick_items_folder).grid(
            row=0, column=2
        )
        ttk.Button(frm_folder, text="Load Items", command=self._load_items).grid(
            row=0, column=3
        )
        ttk.Button(frm_folder, text="Clear List", command=self._clear_items).grid(
            row=0, column=4
        )
        
        frm_folder.grid_columnconfigure(1, weight=1)
        
        # Search and Filter
        frm_search = ttk.Frame(self)
        frm_search.pack(fill="x", **pad)
        
        # Search section
        ttk.Label(frm_search, text="Search:").pack(side="left")
        search_entry = ttk.Entry(frm_search, textvariable=self.var_search, width=25)
        search_entry.pack(side="left", padx=(6, 20))
        
        # Filter section  
        ttk.Label(frm_search, text="Item Type:").pack(side="left")
        type_combo = ttk.Combobox(frm_search, textvariable=self.var_category_filter, 
                                 values=ITEM_CATEGORIES, state="readonly", width=12)
        type_combo.pack(side="left", padx=(6, 20))
        type_combo.set("ALL")  # Set default value
        
        # Count section
        self.lbl_count = ttk.Label(frm_search, text="No items loaded")
        self.lbl_count.pack(side="right")
        
        # Items display area with full background
        frm_items = ttk.LabelFrame(self, text="Items")
        frm_items.pack(fill="both", expand=True, **pad)
        
        # Create scrollable frame with full coverage
        self.canvas = tk.Canvas(frm_items, bg="#1a1a1a", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(frm_items, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#1a1a1a")
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Bind canvas resize to update scrollable frame width
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Bind mousewheel to canvas
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)
    
    def _on_canvas_configure(self, event):
        # Update scrollable frame width to match canvas
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def _pick_items_folder(self):
        folder = filedialog.askdirectory(title="Select Items Folder (with .txt files)")
        if folder:
            folder_path = str(Path(folder).resolve())
            self.var_items_folder.set(folder_path)
    
    def _clear_items(self):
        """Clear all loaded items and reset the display"""
        self.items = []
        self.filtered_items = []
        self.lbl_count.config(text="No items loaded")
        self._update_display()
        
        # Reset search and filter
        self.var_search.set("")
        self.var_category_filter.set("ALL")
    
    def _load_items(self):
        folder = self.var_items_folder.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showerror(APP_TITLE, "Please select a valid folder.")
            return
        
        try:
            self.items = load_items_from_folder(folder)
            self._apply_filters()
            
            # Count items by category
            category_counts = {}
            for item in self.items:
                category_counts[item.category] = category_counts.get(item.category, 0) + 1
            
            count_text = f"{len(self.items)} items loaded"
            if category_counts:
                # Sort categories for consistent display
                sorted_cats = sorted(category_counts.items())
                details = ", ".join([f"{cat}: {count}" for cat, count in sorted_cats])
                count_text += f" ({details})"
            
            self.lbl_count.config(text=count_text)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Error loading items: {e}")
        folder = self.var_items_folder.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showerror(APP_TITLE, "Please select a valid folder.")
            return
        
        try:
            self.items = load_items_from_folder(folder)
            self._apply_filters()
            
            # Count items by category
            category_counts = {}
            for item in self.items:
                category_counts[item.category] = category_counts.get(item.category, 0) + 1
            
            count_text = f"{len(self.items)} items loaded"
            if category_counts:
                # Sort categories for consistent display
                sorted_cats = sorted(category_counts.items())
                details = ", ".join([f"{cat}: {count}" for cat, count in sorted_cats])
                count_text += f" ({details})"
            
            self.lbl_count.config(text=count_text)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Error loading items: {e}")
    
    def _on_search_change(self, *args):
        self._apply_filters()
    
    def _on_filter_change(self, *args):
        self._apply_filters()
    
    def _apply_filters(self):
        """Apply both search and category filters"""
        query = self.var_search.get()
        category = self.var_category_filter.get()
        
        if query.strip() or category != "ALL":
            self.filtered_items = fuzzy_search(self.items, query, category)
        else:
            self.filtered_items = self.items[:]
        
        self._update_display()
        
        # Scroll to top when filters change
        self.canvas.yview_moveto(0)
        
        # Update counter
        if query.strip() or category != "ALL":
            filter_text = f"{len(self.filtered_items)} / {len(self.items)} items"
            if category != "ALL":
                filter_text += f" (Type: {category})"
            self.lbl_count.config(text=filter_text)
        else:
            self.lbl_count.config(text=f"{len(self.items)} items loaded")
    
    def _update_display(self):
        # Clear existing items
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        if not self.filtered_items:
            if self.items:
                msg_frame = tk.Frame(self.scrollable_frame, bg="#1a1a1a")
                msg_frame.pack(fill="both", expand=True)
                ttk.Label(msg_frame, text="No items match your search/filter.", 
                         font=("Segoe UI", 12), background="#1a1a1a", foreground="#cccccc").pack(pady=40)
            else:
                msg_frame = tk.Frame(self.scrollable_frame, bg="#1a1a1a")
                msg_frame.pack(fill="both", expand=True)
                ttk.Label(msg_frame, text="No items loaded. Click 'Load Items' to begin.", 
                         font=("Segoe UI", 12), background="#1a1a1a", foreground="#cccccc").pack(pady=40)
            return
        
        # Create main container frame
        container = tk.Frame(self.scrollable_frame, bg="#1a1a1a")
        container.pack(fill="both", expand=True, padx=8, pady=8)
        
        # Display items in a grid (3 per row)
        cols = 3
        for i, item in enumerate(self.filtered_items):
            row = i // cols
            col = i % cols
            
            # Create item tile with fixed width
            tile = tk.Frame(container, relief="solid", bd=1, bg="#2a2a2a", width=280)
            tile.grid(row=row, column=col, padx=8, pady=8, sticky="new")
            tile.grid_propagate(False)  # Maintain fixed width
            
            # Hero name header with category badge
            hero_frame = tk.Frame(tile, bg="#1e1e1e", height=30)
            hero_frame.pack(fill="x")
            hero_frame.pack_propagate(False)
            
            hero_text = f"📁 {item.hero_name}"
            if item.category != "MISC":
                hero_text += f" [{item.category}]"
            
            hero_lbl = tk.Label(hero_frame, text=hero_text, 
                               fg="#ffd700", bg="#1e1e1e", font=("Segoe UI", 9, "bold"))
            hero_lbl.pack(pady=4)
            
            # Item text with color coding and auto height
            item_text = tk.Text(tile, wrap="word", bg="#2a2a2a", fg=item.color, 
                               font=("Consolas", 9), relief="flat", borderwidth=0,
                               state="disabled", cursor="arrow")
            
            # Calculate required height for the text
            lines = item.text.count('\n') + 1
            lines += len(item.text) // 35  # Account for word wrapping (35 chars per line approx)
            height = max(6, min(25, lines + 1))  # Min 6, max 25 lines
            item_text.config(height=height)
            
            item_text.pack(padx=6, pady=(0, 6), fill="both", expand=True)
            item_text.config(state="normal")
            item_text.insert("1.0", item.text)
            item_text.config(state="disabled")
        
        # Configure grid weights for 3 equal columns
        for col in range(cols):
            container.grid_columnconfigure(col, weight=1, uniform="col")


# -----------------------------
# Item Tracker Tab  
# -----------------------------
class ItemTrackerTab(ttk.Frame):
    def __init__(self, parent, app_ref):
        super().__init__(parent)
        self.app_ref = app_ref  # Reference to main app for .env functions
        
        self.stop_flag = {"stop": False}
        self.worker: Processor = None
        self.log_q: queue.Queue[str] = queue.Queue()

        # Vars
        self.var_endpoint = tk.StringVar(value=DEFAULTS["VISION_ENDPOINT"])
        self.var_model = tk.StringVar(value=DEFAULTS["VISION_MODEL"])
        self.var_api_key = tk.StringVar(value=DEFAULTS["VISION_API_KEY"])
        self.var_folder = tk.StringVar(value=DEFAULTS["SCREENSHOTS_FOLDER"])
        self.var_output = tk.StringVar(value=DEFAULTS["OUTPUT_FILE"])
        self.var_rpm = tk.StringVar(value=DEFAULTS["RATE_LIMIT_RPM"])
        self.var_jitter = tk.StringVar(value=DEFAULTS["RATE_JITTER_MS"])
        self.var_retries = tk.StringVar(value=DEFAULTS["MAX_RETRIES"])
        self.var_retry_delay = tk.StringVar(value=DEFAULTS["RETRY_DELAY"])
        self.var_timeout = tk.StringVar(value=DEFAULTS["REQUEST_TIMEOUT"])
        self._show_key = tk.BooleanVar(value=False)

        self._build_ui()
        self.after(100, self._poll_logs)

    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        frm_top = ttk.LabelFrame(self, text="API settings")
        frm_top.pack(fill="x", **pad)

        ttk.Label(frm_top, text="Endpoint:").grid(row=0, column=0, sticky="e")
        ttk.Entry(frm_top, textvariable=self.var_endpoint, width=60).grid(
            row=0, column=1, sticky="we"
        )
        ttk.Label(frm_top, text="Model:").grid(row=1, column=0, sticky="e")
        ttk.Entry(frm_top, textvariable=self.var_model, width=60).grid(
            row=1, column=1, sticky="we"
        )

        ttk.Label(frm_top, text="API Key:").grid(row=2, column=0, sticky="e")
        self._key_entry = ttk.Entry(
            frm_top, textvariable=self.var_api_key, width=60, show="*"
        )
        self._key_entry.grid(row=2, column=1, sticky="we")
        ttk.Checkbutton(
            frm_top, text="Show", variable=self._show_key, command=self._toggle_key
        ).grid(row=2, column=2)

        frm_top.grid_columnconfigure(1, weight=1)

        frm_paths = ttk.LabelFrame(self, text="Paths")
        frm_paths.pack(fill="x", **pad)

        ttk.Label(frm_paths, text="Screenshots folder:").grid(
            row=0, column=0, sticky="e"
        )
        ttk.Entry(frm_paths, textvariable=self.var_folder, width=60).grid(
            row=0, column=1, sticky="we"
        )
        ttk.Button(frm_paths, text="Browse…", command=self._pick_folder).grid(
            row=0, column=2
        )

        ttk.Label(frm_paths, text="Output file:").grid(row=1, column=0, sticky="e")
        ttk.Entry(frm_paths, textvariable=self.var_output, width=60).grid(
            row=1, column=1, sticky="we"
        )
        ttk.Button(frm_paths, text="Save as…", command=self._pick_output).grid(
            row=1, column=2
        )

        frm_paths.grid_columnconfigure(1, weight=1)

        frm_rate = ttk.LabelFrame(self, text="Limits & retries")
        frm_rate.pack(fill="x", **pad)

        ttk.Label(frm_rate, text="Rate limit RPM:").grid(row=0, column=0, sticky="e")
        ttk.Entry(frm_rate, textvariable=self.var_rpm, width=8).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(frm_rate, text="Jitter (ms):").grid(row=0, column=2, sticky="e")
        ttk.Entry(frm_rate, textvariable=self.var_jitter, width=8).grid(
            row=0, column=3, sticky="w"
        )

        ttk.Label(frm_rate, text="Retries:").grid(row=1, column=0, sticky="e")
        ttk.Entry(frm_rate, textvariable=self.var_retries, width=8).grid(
            row=1, column=1, sticky="w"
        )
        ttk.Label(frm_rate, text="Retry delay (s):").grid(row=1, column=2, sticky="e")
        ttk.Entry(frm_rate, textvariable=self.var_retry_delay, width=8).grid(
            row=1, column=3, sticky="w"
        )
        ttk.Label(frm_rate, text="Timeout (s):").grid(row=1, column=4, sticky="e")
        ttk.Entry(frm_rate, textvariable=self.var_timeout, width=8).grid(
            row=1, column=5, sticky="w"
        )

        for i in range(0, 6):
            frm_rate.grid_columnconfigure(i, weight=1)

        frm_actions = ttk.Frame(self)
        frm_actions.pack(fill="x", **pad)
        self.btn_run = ttk.Button(frm_actions, text="Run", command=self._run)
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(
            frm_actions, text="Stop", command=self._stop, state="disabled"
        )
        self.btn_stop.pack(side="left", padx=6)
        
        # Add .env buttons back to tracker tab
        ttk.Button(frm_actions, text="Load .env", command=self.app_ref._load_env).pack(
            side="right", padx=(0, 6)
        )
        ttk.Button(frm_actions, text="Save .env", command=self.app_ref._save_env).pack(
            side="right"
        )

        frm_prog = ttk.Frame(self)
        frm_prog.pack(fill="x", **pad)
        self.prog = ttk.Progressbar(
            frm_prog, orient="horizontal", mode="determinate", maximum=100
        )
        self.prog.pack(fill="x")

        frm_log = ttk.LabelFrame(self, text="Log")
        frm_log.pack(fill="both", expand=True, **pad)
        self.txt = tk.Text(frm_log, height=16, wrap="word")
        self.txt.pack(fill="both", expand=True)
        self.txt.insert("end", "Ready.\n")

    def _toggle_key(self):
        self._key_entry.configure(show="" if self._show_key.get() else "*")

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Select D2R Screenshots Folder")
        if folder:
            folder_path = str(Path(folder).resolve())
            self.var_folder.set(folder_path)
            if not self.var_output.get():
                output_path = str(Path(folder_path) / DEFAULT_OUTPUT_NAME)
                self.var_output.set(output_path)

    def _pick_output(self):
        current_folder = self.var_folder.get() or str(Path.cwd())
        initial = self.var_output.get() or str(Path(current_folder) / DEFAULT_OUTPUT_NAME)
        
        path = filedialog.asksaveasfilename(
            title="Save output as",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=Path(initial).name if initial else DEFAULT_OUTPUT_NAME,
            initialdir=str(Path(initial).parent) if initial else current_folder,
        )
        if path:
            output_path = str(Path(path).resolve())
            self.var_output.set(output_path)

    def _validate(self) -> bool:
        if not self.var_endpoint.get().strip():
            messagebox.showerror(APP_TITLE, "Endpoint is required.")
            return False
        if not self.var_model.get().strip():
            messagebox.showerror(APP_TITLE, "Model is required.")
            return False
        if not self.var_api_key.get().strip():
            messagebox.showerror(APP_TITLE, "API key is required.")
            return False
        
        folder = self.var_folder.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showerror(APP_TITLE, "Valid screenshots folder is required.")
            return False
        
        if not self.var_output.get().strip():
            output_path = str(Path(folder) / DEFAULT_OUTPUT_NAME)
            self.var_output.set(output_path)

        # Normalize/repair the output path (handle "folder as file" cases)
        fixed = ensure_txt_path(self.var_output.get().strip(), folder, DEFAULT_OUTPUT_NAME)
        self.var_output.set(str(Path(fixed).resolve()))

        return True

    def _progress_update(self, done: int, total: int):
        """Thread-safe progress update"""
        def update():
            pct = int(done * 100 / max(1, total))
            self.prog["value"] = pct
        self.after(0, update)

    def _processing_done(self, content: str):
        """Thread-safe completion handler"""
        def finish():
            try:
                if content:  # Only save if we have content
                    out_path = ensure_txt_path(self.p["output"], self.p["folder"], DEFAULT_OUTPUT_NAME)
                    saved_to = save_text_atomic(out_path, content)
                    self.log_q.put(f"\n✅ Saved to: {saved_to}")
                else:
                    self.log_q.put("\n❌ No content to save.")
            except PermissionError as e:
                # Fallback to a safe, user-writable dir if Defender blocks Documents
                fallback = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "D2R-AI-Item-Tracker" / DEFAULT_OUTPUT_NAME
                try:
                    fallback.parent.mkdir(parents=True, exist_ok=True)
                    saved_to = save_text_atomic(str(fallback), content)
                    self.log_q.put(f"\n⚠️ Write blocked in selected folder. Saved to: {saved_to}")
                except Exception as e2:
                    self.log_q.put(f"[fatal] Could not save output (blocked): {e}; fallback failed: {e2}")
            except Exception as e:
                self.log_q.put(f"[fatal] Could not save output: {e}")
            finally:
                self.btn_run.config(state="normal")
                self.btn_stop.config(state="disabled")
                self.worker = None
        
        self.after(0, finish)

    def _run(self):
        if not self._validate():
            return
        
        # Stop any existing worker
        if self.worker and self.worker.is_alive():
            self.stop_flag["stop"] = True
            self.worker.join(timeout=2.0)
        
        self.stop_flag["stop"] = False
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("end", "Starting...\n")
        self.prog["value"] = 0

        self.p = {
            "VISION_ENDPOINT": self.var_endpoint.get().strip(),
            "VISION_MODEL": self.var_model.get().strip(),
            "VISION_API_KEY": self.var_api_key.get().strip(),
            "MAX_RETRIES": self.var_retries.get().strip(),
            "RETRY_DELAY": self.var_retry_delay.get().strip(),
            "REQUEST_TIMEOUT": self.var_timeout.get().strip(),
            "RATE_LIMIT_RPM": self.var_rpm.get().strip(),
            "RATE_JITTER_MS": self.var_jitter.get().strip(),
            "folder": self.var_folder.get().strip(),
            "output": self.var_output.get().strip(),
        }

        # Start the worker thread
        self.worker = Processor(
            self.p, 
            self.log_q, 
            self._progress_update, 
            self._processing_done, 
            self.stop_flag
        )
        self.worker.start()

    def _stop(self):
        if self.worker and self.worker.is_alive():
            self.stop_flag["stop"] = True
            self.txt.insert("end", "Stopping...\n")
            self.txt.see("end")
            
            # Wait for worker to finish
            def check_worker():
                if self.worker and self.worker.is_alive():
                    self.after(100, check_worker)
                else:
                    self.btn_run.config(state="normal")
                    self.btn_stop.config(state="disabled")
                    self.log_q.put("✅ Stopped successfully.")
                    self.worker = None
            
            self.after(100, check_worker)
        else:
            # Worker is already stopped or None
            self.btn_run.config(state="normal")
            self.btn_stop.config(state="disabled")
            self.log_q.put("✅ Already stopped.")

    def _poll_logs(self):
        try:
            while True:
                msg = self.log_q.get_nowait()
                self.txt.insert("end", msg + "\n")
                self.txt.see("end")
        except queue.Empty:
            pass
        self.after(100, self._poll_logs)


# -----------------------------
# Main App
# -----------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("900x700")
        self.minsize(800, 600)

        self._build_ui()

    def _build_ui(self):
        # Create menu bar
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Load .env", command=self._load_env)
        file_menu.add_command(label="Save .env", command=self._save_env)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)

        # Create notebook (tabs)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)
        
        # Create tabs
        self.tracker_tab = ItemTrackerTab(self.notebook, self)
        self.item_list_tab = ItemListTab(self.notebook)
        
        self.notebook.add(self.tracker_tab, text="Item Tracker")
        self.notebook.add(self.item_list_tab, text="Item List")

    def _load_env(self):
        # Let user choose .env file to load
        path = filedialog.askopenfilename(
            title="Load .env file",
            defaultextension=".env",
            filetypes=[("Environment files", "*.env"), ("All files", "*.*")],
            initialdir=os.getcwd()
        )
        
        if not path:
            return
            
        try:
            # Read the .env file manually to avoid reloading the global env
            env_vars = {}
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env_vars[key.strip()] = value.strip()
            
            # Update the tracker tab variables
            if "VISION_ENDPOINT" in env_vars:
                self.tracker_tab.var_endpoint.set(env_vars["VISION_ENDPOINT"])
            if "VISION_MODEL" in env_vars:
                self.tracker_tab.var_model.set(env_vars["VISION_MODEL"])
            if "VISION_API_KEY" in env_vars:
                self.tracker_tab.var_api_key.set(env_vars["VISION_API_KEY"])
            if "SCREENSHOTS_FOLDER" in env_vars:
                self.tracker_tab.var_folder.set(env_vars["SCREENSHOTS_FOLDER"])
            if "OUTPUT_FILE" in env_vars:
                self.tracker_tab.var_output.set(env_vars["OUTPUT_FILE"])
            if "MAX_RETRIES" in env_vars:
                self.tracker_tab.var_retries.set(env_vars["MAX_RETRIES"])
            if "RETRY_DELAY" in env_vars:
                self.tracker_tab.var_retry_delay.set(env_vars["RETRY_DELAY"])
            if "REQUEST_TIMEOUT" in env_vars:
                self.tracker_tab.var_timeout.set(env_vars["REQUEST_TIMEOUT"])
            if "RATE_LIMIT_RPM" in env_vars:
                self.tracker_tab.var_rpm.set(env_vars["RATE_LIMIT_RPM"])
            if "RATE_JITTER_MS" in env_vars:
                self.tracker_tab.var_jitter.set(env_vars["RATE_JITTER_MS"])
            
            # Update the item list tab variables
            if "ITEM_LIST_FOLDER" in env_vars:
                self.item_list_tab.var_items_folder.set(env_vars["ITEM_LIST_FOLDER"])
                
            messagebox.showinfo(APP_TITLE, f"Loaded settings from:\n{path}")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Failed to load .env file: {e}")

    def _save_env(self):
        # Let user choose where to save .env file
        path = filedialog.asksaveasfilename(
            title="Save .env file as",
            defaultextension=".env",
            filetypes=[("Environment files", "*.env"), ("All files", "*.*")],
            initialfile=".env",
            initialdir=os.getcwd()
        )
        
        if not path:
            return
            
        lines = [
            f"VISION_ENDPOINT={self.tracker_tab.var_endpoint.get().strip()}",
            f"VISION_MODEL={self.tracker_tab.var_model.get().strip()}",
            f"VISION_API_KEY={self.tracker_tab.var_api_key.get().strip()}",
            f"SCREENSHOTS_FOLDER={self.tracker_tab.var_folder.get().strip()}",
            f"OUTPUT_FILE={self.tracker_tab.var_output.get().strip()}",
            f"ITEM_LIST_FOLDER={self.item_list_tab.var_items_folder.get().strip()}",
            "MAX_WORKERS=1",
            f"MAX_RETRIES={self.tracker_tab.var_retries.get().strip()}",
            f"RETRY_DELAY={self.tracker_tab.var_retry_delay.get().strip()}",
            f"REQUEST_TIMEOUT={self.tracker_tab.var_timeout.get().strip()}",
            f"RATE_LIMIT_RPM={self.tracker_tab.var_rpm.get().strip()}",
            f"RATE_JITTER_MS={self.tracker_tab.var_jitter.get().strip()}",
            "",
        ]
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            messagebox.showinfo(APP_TITLE, f"Saved .env to:\n{path}")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Failed to save .env: {e}")


if __name__ == "__main__":
    # Avoid DPI scaling blur on Windows (optional)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    App().mainloop()