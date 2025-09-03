"""Configuration and constants for D2R AI Item Tracker."""

import os
from pathlib import Path

# Application constants
APP_TITLE = "D2R AI Item Tracker (GUI)"
DEFAULT_OUTPUT_NAME = "output.txt"
CACHE_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "D2R-AI-Item-Tracker"
CACHE_FILE = CACHE_DIR / "items_cache.pkl"
SETTINGS_CACHE_FILE = CACHE_DIR / "settings_cache.pkl"

# Default settings
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

# API prompts
SYSTEM_PROMPT = (
    "You are an OCR-style vision assistant. Read ONLY the item tooltip text in the image. "
    "Return the text as it appears, preserving line breaks, without extra commentary. "
    "Do NOT include the bottom control-hint lines such as 'Shift + Left Click to Unequip' or "
    "'Ctrl + Left Click to Move'. "
    "If the item is part of a set, do NOT include the list of other set items "
    "that always appears at the very bottom (e.g., 'NAJ'S ANCIENT VESTIGE, TAL RASHA'S WRAPPINGS ...'). "
    "Only return the actual stats and description of the currently hovered item. "
    "After the item text, add this line: "
    "[CATEGORY: X] where X is one of: WEAPON, ARMOR, CHARM, RING, AMULET, JEWEL, GEM, RUNE, MISC "
)

USER_PROMPT = "Extract the exact text content from this item tooltip. Only output the text, no explanations."

# Text filtering
BANNED_LINES = {
    "SHIFT + LEFT CLICK TO UNEQUIP",
    "CTRL + LEFT CLICK TO MOVE",
    "SHIFT + LEFT CLICK TO EQUIP",
    "HOLD SHIFT TO COMPARE",
    "LEFT CLICK TO CAST",
    "KEEP IN INVENTORY TO GAIN BONUS",
    "CAN BE INSERTED INTO SOCKETED ITEMS"
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
    "MISC",
]
