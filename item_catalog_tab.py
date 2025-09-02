"""Item Catalog Tab GUI component for D2R AI Item Tracker."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import List

from config import APP_TITLE, DEFAULTS, ITEM_CATEGORIES
from models import Item, fuzzy_search
from cache import (
    save_items_cache,
    load_items_cache,
    clear_items_cache,
    load_items_from_folder,
    remove_item_from_file,
)


class ItemCatalogTab(ttk.Frame):
    """GUI tab for displaying and searching item lists."""

    def __init__(self, parent):
        super().__init__(parent)
        self.items: List[Item] = []
        self.filtered_items: List[Item] = []
        self.scrollable_frame = None  # Initialize early to prevent AttributeError

        self.var_items_folder = tk.StringVar(value=DEFAULTS["ITEM_LIST_FOLDER"])
        self.var_search = tk.StringVar()
        self.var_category_filter = tk.StringVar(value="ALL")

        # Build UI first, then set up traces to avoid AttributeError
        self._build_ui()

        # Set up traces after UI is built
        self.var_search.trace("w", self._on_search_change)
        self.var_category_filter.trace("w", self._on_filter_change)

        # Load cached items on startup
        self._load_cached_items()

    def _build_ui(self):
        """Build the user interface for the tab."""
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
        type_combo = ttk.Combobox(
            frm_search,
            textvariable=self.var_category_filter,
            values=ITEM_CATEGORIES,
            state="readonly",
            width=12,
        )
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
        self.scrollbar = ttk.Scrollbar(
            frm_items, orient="vertical", command=self.canvas.yview
        )
        self.scrollable_frame = tk.Frame(self.canvas, bg="#1a1a1a")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.scrollable_frame, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Bind canvas resize to update scrollable frame width
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Bind mousewheel to canvas
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)

    def _on_canvas_configure(self, event):
        """Update scrollable frame width to match canvas."""
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling."""
        # Check if the canvas has focus or if we're scrolling over it
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"  # Prevent event from propagating

    def _pick_items_folder(self):
        """Open folder selection dialog."""
        folder = filedialog.askdirectory(title="Select Items Folder (with .txt files)")
        if folder:
            folder_path = str(Path(folder).resolve())
            self.var_items_folder.set(folder_path)

    def _load_cached_items(self):
        """Load items from cache on startup."""
        try:
            cached_items, cached_folder = load_items_cache()
            if cached_items:
                self.items = cached_items
                if cached_folder:
                    self.var_items_folder.set(cached_folder)
                self._apply_filters()

                # Count items by category
                category_counts = {}
                for item in self.items:
                    category_counts[item.category] = (
                        category_counts.get(item.category, 0) + 1
                    )

                count_text = f"{len(self.items)} items loaded from cache"
                if category_counts:
                    sorted_cats = sorted(category_counts.items())
                    details = ", ".join(
                        [f"{cat}: {count}" for cat, count in sorted_cats]
                    )
                    count_text += f" ({details})"

                self.lbl_count.config(text=count_text)
        except Exception as e:
            print(f"Error loading cached items: {e}")

    def _clear_items(self):
        """Clear all loaded items, reset the display, and delete cache."""
        self.items = []
        self.filtered_items = []
        self.lbl_count.config(text="No items loaded")

        # Clear cache files
        clear_items_cache()

        # Reset UI
        if self.scrollable_frame:  # Check if scrollable_frame exists
            self._update_display()

        # Reset search and filter
        self.var_search.set("")
        self.var_category_filter.set("ALL")

    def _load_items(self):
        """Load items from the selected folder."""
        folder = self.var_items_folder.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showerror(APP_TITLE, "Please select a valid folder.")
            return

        try:
            self.items = load_items_from_folder(folder)
            self._apply_filters()

            # Save to cache
            save_items_cache(self.items, folder)

            # Count items by category
            category_counts = {}
            for item in self.items:
                category_counts[item.category] = (
                    category_counts.get(item.category, 0) + 1
                )

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
        """Handle search text change."""
        self._apply_filters()

    def _on_filter_change(self, *args):
        """Handle filter change."""
        self._apply_filters()

    def _apply_filters(self):
        """Apply both search and category filters."""
        query = self.var_search.get()
        category = self.var_category_filter.get()

        if query.strip() or category != "ALL":
            self.filtered_items = fuzzy_search(self.items, query, category)
        else:
            self.filtered_items = self.items[:]

        # Only update display and scroll if UI is fully initialized
        if hasattr(self, "scrollable_frame") and self.scrollable_frame is not None:
            self._update_display()
            # Scroll to top when filters change
            if hasattr(self, "canvas"):
                self.canvas.yview_moveto(0)

        # Update counter
        if query.strip() or category != "ALL":
            filter_text = f"{len(self.filtered_items)} / {len(self.items)} items"
            if category != "ALL":
                filter_text += f" (Type: {category})"
            if hasattr(self, "lbl_count"):
                self.lbl_count.config(text=filter_text)
        else:
            if hasattr(self, "lbl_count"):
                self.lbl_count.config(text=f"{len(self.items)} items loaded")

    def _delete_item(self, item: Item):
        """Delete an item from the catalog with confirmation."""
        # Create custom dialog
        dialog = tk.Toplevel(self)
        dialog.title("Delete Item")
        dialog.resizable(False, False)
        dialog.configure(bg="#1e1e1e")

        # Hide the dialog initially to prevent flashing
        dialog.withdraw()

        # Get screen dimensions
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()

        # Set dialog dimensions
        dialog_width = 400
        dialog_height = 200

        # Calculate center position
        x = (screen_width - dialog_width) // 2
        y = (screen_height - dialog_height) // 2

        # Set geometry with position
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        dialog.transient(self)
        dialog.grab_set()

        # Get item name (first line of item text)
        item_name = item.text.split("\n")[0] if item.text else "this item"

        # Message
        msg_frame = tk.Frame(dialog, bg="#1e1e1e")
        msg_frame.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(
            msg_frame,
            text=f"Are you sure you want to delete:\n\n{item_name}\n\nfrom the catalog?",
            bg="#1e1e1e",
            fg="#ffffff",
            font=("Segoe UI", 10),
            wraplength=350,
        ).pack(pady=(0, 15))

        # Checkbox for file deletion
        var_delete_from_file = tk.BooleanVar(value=False)
        checkbox = tk.Checkbutton(
            msg_frame,
            text="Also delete from source file (permanent)",
            variable=var_delete_from_file,
            bg="#1e1e1e",
            fg="#ffffff",
            selectcolor="#1e1e1e",
            activebackground="#1e1e1e",
            activeforeground="#ffffff",
            font=("Segoe UI", 9),
        )
        checkbox.pack()

        # Buttons
        btn_frame = tk.Frame(dialog, bg="#1e1e1e")
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))

        def confirm_delete():
            try:
                # Remove from file if requested
                if var_delete_from_file.get():
                    success = remove_item_from_file(item)
                    if not success:
                        messagebox.showwarning(
                            APP_TITLE,
                            "Could not remove item from file. It may have been already modified.",
                        )

                # Remove from current items list
                if item in self.items:
                    self.items.remove(item)

                # Update cache
                folder_path = self.var_items_folder.get()
                save_items_cache(self.items, folder_path)

                # Refresh display
                self._apply_filters()

                # Update count
                self._update_count()

                dialog.destroy()

            except Exception as e:
                messagebox.showerror(APP_TITLE, f"Error deleting item: {e}")
                dialog.destroy()

        tk.Button(
            btn_frame,
            text="Delete",
            command=confirm_delete,
            bg="#d32f2f",
            fg="#ffffff",
            width=10,
            relief="flat",
            cursor="hand2",
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            btn_frame,
            text="Cancel",
            command=dialog.destroy,
            bg="#333333",
            fg="#ffffff",
            width=10,
            relief="flat",
            cursor="hand2",
        ).pack(side="left")

        # Focus on cancel button by default for safety
        btn_frame.winfo_children()[1].focus_set()

        # Show the dialog now that it's fully constructed and positioned
        dialog.deiconify()

    def _update_count(self):
        """Update the item count display."""
        category_counts = {}
        for item in self.items:
            category_counts[item.category] = category_counts.get(item.category, 0) + 1

        if self.items:
            count_text = f"{len(self.items)} items"
            if category_counts:
                sorted_cats = sorted(category_counts.items())
                details = ", ".join([f"{cat}: {count}" for cat, count in sorted_cats])
                count_text += f" ({details})"
        else:
            count_text = "No items loaded"

        self.lbl_count.config(text=count_text)

    def _update_display(self):
        """Update the display with current filtered items."""
        # Clear existing items
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        if not self.filtered_items:
            if self.items:
                msg_frame = tk.Frame(self.scrollable_frame, bg="#1a1a1a")
                msg_frame.pack(fill="both", expand=True)
                msg_frame.bind("<MouseWheel>", self._on_mousewheel)
                msg_label = ttk.Label(
                    msg_frame,
                    text="No items match your search/filter.",
                    font=("Segoe UI", 12),
                    background="#1a1a1a",
                    foreground="#cccccc",
                )
                msg_label.pack(pady=40)
                msg_label.bind("<MouseWheel>", self._on_mousewheel)
            else:
                msg_frame = tk.Frame(self.scrollable_frame, bg="#1a1a1a")
                msg_frame.pack(fill="both", expand=True)
                msg_frame.bind("<MouseWheel>", self._on_mousewheel)
                msg_label = ttk.Label(
                    msg_frame,
                    text="No items loaded. Click 'Load Items' to begin.",
                    font=("Segoe UI", 12),
                    background="#1a1a1a",
                    foreground="#cccccc",
                )
                msg_label.pack(pady=40)
                msg_label.bind("<MouseWheel>", self._on_mousewheel)
            return

        # Create main container frame
        container = tk.Frame(self.scrollable_frame, bg="#1a1a1a")
        container.pack(fill="both", expand=True, padx=8, pady=8)

        # Bind mousewheel to container
        container.bind("<MouseWheel>", self._on_mousewheel)

        # Display items in a grid (3 per row)
        cols = 3
        for i, item in enumerate(self.filtered_items):
            row = i // cols
            col = i % cols

            # Create item tile with fixed width
            tile = tk.Frame(container, relief="solid", bd=1, bg="#2a2a2a", width=280)
            tile.grid(row=row, column=col, padx=8, pady=8, sticky="new")
            tile.grid_propagate(False)  # Maintain fixed width

            # Bind mousewheel to tile
            tile.bind("<MouseWheel>", self._on_mousewheel)

            # Hero name header with category badge and delete button
            hero_frame = tk.Frame(tile, bg="#2a2a2a", height=30)
            hero_frame.pack(fill="x")
            hero_frame.pack_propagate(False)

            # Bind mousewheel to hero frame
            hero_frame.bind("<MouseWheel>", self._on_mousewheel)

            # Left side - hero name and category
            left_frame = tk.Frame(hero_frame, bg="#2a2a2a")
            left_frame.pack(side="left", fill="both", expand=True)
            left_frame.bind("<MouseWheel>", self._on_mousewheel)

            hero_text = f"📁 {item.hero_name}"
            if item.category != "MISC":
                hero_text += f" [{item.category}]"

            hero_lbl = tk.Label(
                left_frame,
                text=hero_text,
                fg="#ffffff",
                bg="#2a2a2a",
                font=("Exocet", 11, "bold"),
            )
            hero_lbl.pack(pady=4)
            hero_lbl.bind("<MouseWheel>", self._on_mousewheel)

            # Right side - delete button (X)
            delete_btn = tk.Button(
                hero_frame,
                text="✕",
                fg="#ff6666",
                bg="#2a2a2a",
                font=("Arial", 10, "bold"),
                bd=0,
                cursor="hand2",
                activebackground="#3a3a3a",
                activeforeground="#ff9999",
                command=lambda itm=item: self._delete_item(itm),
            )
            delete_btn.pack(side="right", padx=(0, 5), pady=2)
            delete_btn.bind("<MouseWheel>", self._on_mousewheel)

            # Item text with color coding and auto height
            item_text = tk.Text(
                tile,
                wrap="word",
                bg="#121212",
                fg="#5959C7",
                font=("Exocet", 11),
                relief="flat",
                borderwidth=0,
                state="disabled",
                cursor="arrow",
            )

            # Bind mousewheel to item text widget
            item_text.bind("<MouseWheel>", self._on_mousewheel)

            item_text.tag_configure(
                "linegap",
                spacing1=2,  # extra pixels above the first display line of a paragraph
                spacing2=4,  # extra pixels between wrapped display lines
                spacing3=2,  # extra pixels below the last display line of a paragraph
            )

            # Calculate required height for the text
            lines = item.text.count("\n") + 1
            lines += (
                len(item.text) // 35
            )  # Account for word wrapping (35 chars per line approx)
            height = max(6, min(25, lines + 1))  # Min 6, max 25 lines
            item_text.config(height=height)

            item_text.pack(padx=6, pady=(0, 6), fill="both", expand=True)
            item_text.config(state="normal")
            item_text.insert("1.0", item.text)
            item_text.config(state="disabled")

        # Configure grid weights for 3 equal columns
        for col in range(cols):
            container.grid_columnconfigure(col, weight=1, uniform="col")
