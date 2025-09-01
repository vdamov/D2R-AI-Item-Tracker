"""Main application for D2R AI Item Tracker."""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import ctypes
from dotenv import load_dotenv

from config import APP_TITLE
from theme import apply_dark_theme
from tracker_tab import ItemTrackerTab
from item_catalog_tab import ItemCatalogTab
from cache import save_items_cache
from utils import load_fonts, asset_path

# Load .env if present
load_dotenv()


class App(tk.Tk):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.iconbitmap(asset_path("images/icon-color.ico"))
        self.title(APP_TITLE)
        self.geometry("900x700")
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
        except Exception as e:
            print(f"Error saving cache on exit: {e}")
        finally:
            self.destroy()

    def _build_ui(self):
        """Build the main user interface."""
        # Create menu bar
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        # Create notebook (tabs)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        # Create tabs
        self.tracker_tab = ItemTrackerTab(self.notebook, self)
        self.item_list_tab = ItemCatalogTab(self.notebook)

        self.notebook.add(self.tracker_tab, text="Item Tracker")
        self.notebook.add(self.item_list_tab, text="Item Catalog")

    def _load_env(self):
        """Load settings from an .env file."""
        # Let user choose .env file to load
        path = filedialog.askopenfilename(
            title="Load .env file",
            defaultextension=".env",
            filetypes=[("Environment files", "*.env"), ("All files", "*.*")],
            initialdir=os.getcwd(),
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
        """Save current settings to an .env file."""
        # Let user choose where to save .env file
        path = filedialog.asksaveasfilename(
            title="Save .env file as",
            defaultextension=".env",
            filetypes=[("Environment files", "*.env"), ("All files", "*.*")],
            initialfile=".env",
            initialdir=os.getcwd(),
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