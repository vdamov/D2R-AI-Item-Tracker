"""Main application for D2R AI Item Tracker."""

import os
import sys
import tkinter as tk
from tkinter import ttk
import ctypes

from config import APP_TITLE
from theme import apply_dark_theme
from tracker_tab import ItemTrackerTab
from item_catalog_tab import ItemCatalogTab
from cache import save_items_cache, save_settings_cache
from utils import load_fonts, asset_path


class App(tk.Tk):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.iconbitmap(asset_path("images/icon-color.ico"))
        self.title(APP_TITLE)
        
        # Set window size
        window_width = 900
        window_height = 700
        
        # Get screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Calculate center position
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        # Set geometry with centered position
        self.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.minsize(800, 600)
        
        apply_dark_theme(self)

        self._build_ui()

        # Handle window close event to save cache
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _on_closing(self):
        """Save cache before closing the application."""
        try:
            # Save current items to cache if any are loaded
            if hasattr(self, "item_list_tab") and self.item_list_tab.items:
                folder_path = self.item_list_tab.var_items_folder.get()
                save_items_cache(self.item_list_tab.items, folder_path)
            
            # Save tracker settings to cache
            if hasattr(self, "tracker_tab"):
                settings = {
                    "VISION_ENDPOINT": self.tracker_tab.var_endpoint.get(),
                    "VISION_MODEL": self.tracker_tab.var_model.get(),
                    "VISION_API_KEY": self.tracker_tab.var_api_key.get(),
                    "SCREENSHOTS_FOLDER": self.tracker_tab.var_folder.get(),
                    "OUTPUT_FILE": self.tracker_tab.var_output.get(),
                    "ITEM_LIST_FOLDER": self.item_list_tab.var_items_folder.get(),
                    "MAX_WORKERS": self.tracker_tab.var_workers.get(),
                    "MAX_RETRIES": self.tracker_tab.var_retries.get(),
                    "RETRY_DELAY": self.tracker_tab.var_retry_delay.get(),
                    "REQUEST_TIMEOUT": self.tracker_tab.var_timeout.get(),
                    "RATE_LIMIT_RPM": self.tracker_tab.var_rpm.get(),
                    "RATE_JITTER_MS": self.tracker_tab.var_jitter.get(),
                }
                save_settings_cache(settings)
        except Exception as e:
            print(f"Error saving cache on exit: {e}")
        finally:
            self.destroy()

    def _build_ui(self):
        """Build the main user interface."""
        # Create notebook (tabs)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        # Create tabs
        self.tracker_tab = ItemTrackerTab(self.notebook, self)
        self.item_list_tab = ItemCatalogTab(self.notebook)

        self.notebook.add(self.tracker_tab, text="Item Tracker")
        self.notebook.add(self.item_list_tab, text="Item Catalog")


def main():
    """Application entry point."""
    try:
        # Optional: improve DPI rendering on Windows
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # Per-monitor v1
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()  # Legacy fallback
            except Exception:
                pass

        load_fonts()
    except Exception as e:
        print(f"Could not load custom fonts: {e}")

    App().mainloop()


if __name__ == "__main__":
    main()