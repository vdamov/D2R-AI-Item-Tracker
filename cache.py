"""Cache management for D2R AI Item Tracker."""

import pickle
import re
from pathlib import Path
from typing import List, Tuple

from config import CACHE_FILE, SETTINGS_CACHE_FILE
from models import Item


def save_items_cache(items: List[Item], folder_path: str):
    """Save items to cache file."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cache_data = {"folder_path": folder_path, "items": []}

        # Convert items to serializable format
        for item in items:
            item_data = {
                "text": item.text,
                "source_file": item.source_file,
                "category": item.category,
            }
            cache_data["items"].append(item_data)

        with open(CACHE_FILE, "wb") as f:
            pickle.dump(cache_data, f)
    except Exception as e:
        print(f"Error saving cache: {e}")


def load_items_cache() -> Tuple[List[Item], str]:
    """Load items from cache file. Returns (items, folder_path)."""
    try:
        if not CACHE_FILE.exists():
            return [], ""

        with open(CACHE_FILE, "rb") as f:
            cache_data = pickle.load(f)

        items = []
        for item_data in cache_data.get("items", []):
            item = Item(
                item_data["text"],
                item_data["source_file"],
                item_data["category"],
            )
            items.append(item)

        return items, cache_data.get("folder_path", "")
    except Exception as e:
        print(f"Error loading cache: {e}")
        return [], ""


def clear_items_cache():
    """Delete cache files."""
    try:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        if SETTINGS_CACHE_FILE.exists():
            SETTINGS_CACHE_FILE.unlink()
    except Exception as e:
        print(f"Error clearing cache: {e}")


def load_items_from_folder(folder_path: str) -> List[Item]:
    """Load all items from text files in a folder."""
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

                # Parse category if present (from new OCR output)
                category = "MISC"

                category_match = re.search(
                    r"\[CATEGORY:\s*(\w+)\]", item_text, re.IGNORECASE
                )
                if category_match:
                    category = category_match.group(1).upper()
                    # Remove category line from display text
                    item_text = re.sub(
                        r"\[CATEGORY:\s*\w+\]", "", item_text, flags=re.IGNORECASE
                    ).strip()

                if item_text:  # Only add if there's actual item text after cleaning
                    items.append(Item(item_text, str(txt_file), category))
        except Exception as e:
            print(f"Error reading {txt_file}: {e}")

    return items


def load_items_from_folder(folder_path: str) -> List[Item]:
    """Load all items from text files in a folder."""
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
                # Parse category if present (from new OCR output)
                category = "MISC"
                category_match = re.search(
                    r"\[CATEGORY:\s*(\w+)\]", item_text, re.IGNORECASE
                )
                if category_match:
                    category = category_match.group(1).upper()
                    # Remove category line from display text
                    item_text = re.sub(
                        r"\[CATEGORY:\s*\w+\]", "", item_text, flags=re.IGNORECASE
                    ).strip()
                if item_text:  # Only add if there's actual item text after cleaning
                    items.append(Item(item_text, str(txt_file), category))
        except Exception as e:
            print(f"Error reading {txt_file}: {e}")
    return items


def remove_item_from_file(item: "Item") -> bool:
    """Remove an item from its source text file."""
    try:
        source_file = Path(item.source_file)
        if not source_file.exists():
            return False
            
        # Read the file
        content = source_file.read_text(encoding="utf-8")
        
        # Split into items
        item_texts = content.split("---")
        
        # Find and remove the matching item
        # We need to reconstruct the full item text with category
        _ = f"{item.text}\n[CATEGORY: {item.category}]"
        
        # Create a new list of items without the one to remove
        new_items = []
        found = False
        
        for item_text in item_texts:
            item_text_stripped = item_text.strip()
            if not item_text_stripped:
                continue
                
            # Check if this is the item to remove
            # We compare the core text (without category) to handle both old and new formats
            text_without_category = re.sub(
                r"\[CATEGORY:\s*\w+\]", "", item_text_stripped, flags=re.IGNORECASE
            ).strip()
            
            if text_without_category == item.text and not found:
                # Skip this item (remove it)
                found = True
                continue
            else:
                # Keep this item
                new_items.append(item_text_stripped)
        
        if not found:
            # Item wasn't found in file, possibly already removed
            return False
        
        # Write back the file
        if new_items:
            new_content = "\n---\n".join(new_items)
            source_file.write_text(new_content, encoding="utf-8")
        else:
            # File would be empty, so delete it
            source_file.unlink()
            
        return True
        
    except Exception as e:
        print(f"Error removing item from file: {e}")
        return False