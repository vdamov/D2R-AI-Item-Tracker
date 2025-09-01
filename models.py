"""Data models for D2R AI Item Tracker."""

from pathlib import Path
from typing import List


class Item:
    """Represents a game item with its properties."""

    def __init__(self, text: str, source_file: str, category: str = "MISC"):
        self.text = text.strip()
        self.source_file = source_file
        self.hero_name = Path(source_file).stem
        self.category = category.upper()
        self.is_ethereal = "ETHEREAL" in self.text.upper()
        self.is_socketed = "SOCKETED" in self.text.upper()


def fuzzy_search(
    items: List[Item], query: str, category_filter: str = "ALL"
) -> List[Item]:
    """Simple fuzzy search through items with category filtering."""
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
