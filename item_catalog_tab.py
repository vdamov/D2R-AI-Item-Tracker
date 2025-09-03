"""Item Catalog Tab GUI component for D2R AI Item Tracker (virtualized scrolling).

This version replaces the old grid-with-placeholders approach with a Canvas-
backed virtualization that only creates widgets for items currently visible in
(the viewport ± 1 row). It significantly reduces lag with 300+ items.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import List, Dict, Tuple

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
    """GUI tab for displaying and searching item lists with virtualized scrolling."""

    # Layout constants
    MIN_CARD_WIDTH = 280
    CARD_HEIGHT = 260
    HPAD = 8
    VPAD = 8
    PREFETCH_ROWS = 1  # render ± this many rows beyond the viewport

    def __init__(self, parent):
        super().__init__(parent)
        self.items: List[Item] = []
        self.filtered_items: List[Item] = []

        # Virtualization state
        self.items_per_row: int = 3  # will auto-recompute on resize
        self.card_width: int = self.MIN_CARD_WIDTH
        self.visible_tiles: Dict[int, Tuple[int, tk.Frame]] = (
            {}
        )  # idx -> (win_id, frame)
        self.debounce_timer = None
        self.debounce_delay = 300  # milliseconds

        self.var_items_folder = tk.StringVar(value=DEFAULTS["ITEM_LIST_FOLDER"])
        self.var_search = tk.StringVar()
        self.var_category_filter = tk.StringVar(value="ALL")

        self._build_ui()

        # Set up traces with debouncing for search
        self.var_search.trace("w", self._on_search_change_debounced)
        self.var_category_filter.trace("w", self._on_filter_change)

        # Load cached items on startup
        self._load_cached_items()

    # -----------------------------
    # UI setup
    # -----------------------------
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

        ttk.Label(frm_search, text="Search:").pack(side="left")
        search_entry = ttk.Entry(frm_search, textvariable=self.var_search, width=25)
        search_entry.pack(side="left", padx=(6, 20))

        ttk.Label(frm_search, text="Item Type:").pack(side="left")
        type_combo = ttk.Combobox(
            frm_search,
            textvariable=self.var_category_filter,
            values=ITEM_CATEGORIES,
            state="readonly",
            width=12,
        )
        type_combo.pack(side="left", padx=(6, 20))
        type_combo.set("ALL")

        self.lbl_count = ttk.Label(frm_search, text="No items loaded")
        self.lbl_count.pack(side="right")

        # Items display area — Canvas + Scrollbar (no inner grid; we place tiles directly)
        frm_items = ttk.LabelFrame(self, text="Items")
        frm_items.pack(fill="both", expand=True, **pad)

        self.canvas = tk.Canvas(frm_items, bg="#1a1a1a", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            frm_items, orient="vertical", command=self._on_scrollbar
        )
        self.canvas.configure(yscrollcommand=self._on_canvas_yscroll)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Ensure drag-scrolling the scrollbar updates virtualization continuously
        self.scrollbar.bind("<B1-Motion>", lambda e: self._check_visibility())
        self.scrollbar.bind("<ButtonRelease-1>", lambda e: self._check_visibility())

        # Events
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel_global)
        self.canvas.bind(
            "<ButtonRelease-1>", lambda e: self.after(1, self._check_visibility)
        )

    # -----------------------------
    # Folder / cache
    # -----------------------------
    def _pick_items_folder(self):
        folder = filedialog.askdirectory(title="Select Items Folder (with .txt files)")
        if folder:
            self.var_items_folder.set(str(Path(folder).resolve()))

    def _load_cached_items(self):
        try:
            cached_items, cached_folder = load_items_cache()
            if cached_items:
                self.items = cached_items
                if cached_folder:
                    self.var_items_folder.set(cached_folder)
                self._apply_filters()
                self._update_count()
        except Exception as e:
            print(f"Error loading cached items: {e}")

    def _clear_items(self):
        self.items = []
        self.filtered_items = []
        self.lbl_count.config(text="No items loaded")
        clear_items_cache()
        self.var_search.set("")
        self.var_category_filter.set("ALL")
        self._update_display()

    def _load_items(self):
        folder = self.var_items_folder.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showerror(APP_TITLE, "Please select a valid folder.")
            return
        try:
            self.items = load_items_from_folder(folder)
            save_items_cache(self.items, folder)
            self._apply_filters()
            self._update_count()
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Error loading items: {e}")

    # -----------------------------
    # Search / filter
    # -----------------------------
    def _on_search_change_debounced(self, *_):
        if self.debounce_timer:
            self.after_cancel(self.debounce_timer)
        self.debounce_timer = self.after(self.debounce_delay, self._apply_filters)

    def _on_filter_change(self, *_):
        self._apply_filters()

    def _apply_filters(self):
        query = self.var_search.get()
        category = self.var_category_filter.get()
        if query.strip() or category != "ALL":
            self.filtered_items = fuzzy_search(self.items, query, category)
        else:
            self.filtered_items = self.items[:]
        self._update_display()
        if query.strip() or category != "ALL":
            txt = f"{len(self.filtered_items)} / {len(self.items)} items"
            if category != "ALL":
                txt += f" (Type: {category})"
            self.lbl_count.config(text=txt)
        else:
            self._update_count()

    # -----------------------------
    # Virtualized canvas helpers
    # -----------------------------
    def _compute_layout(self):
        """Compute items_per_row and card_width based on canvas width."""
        width = max(1, self.canvas.winfo_width())
        # Max columns given a minimum card width + padding
        possible_cols = max(1, (width - self.HPAD) // (self.MIN_CARD_WIDTH + self.HPAD))
        self.items_per_row = int(possible_cols) or 1
        # Recompute card width to use available width evenly
        total_hpad = (self.items_per_row + 1) * self.HPAD
        self.card_width = max(
            self.MIN_CARD_WIDTH,
            (width - total_hpad) // self.items_per_row,
        )

    def _index_bounds_for_view(self) -> Tuple[int, int]:
        """Return (first_idx, last_idx_exclusive) that should be rendered."""
        if not self.filtered_items:
            return 0, 0
        y1 = self.canvas.canvasy(0)
        y2 = self.canvas.canvasy(self.canvas.winfo_height())
        row_h = self.CARD_HEIGHT + self.VPAD
        first_row = max(0, int(y1 // row_h) - self.PREFETCH_ROWS)
        last_row = int(y2 // row_h) + 1 + self.PREFETCH_ROWS
        first_idx = first_row * self.items_per_row
        last_idx = min(len(self.filtered_items), (last_row + 1) * self.items_per_row)
        return first_idx, last_idx

    def _tile_xy(self, idx: int) -> Tuple[int, int]:
        row = idx // self.items_per_row
        col = idx % self.items_per_row
        x = self.HPAD + col * (self.card_width + self.HPAD)
        y = self.VPAD + row * (self.CARD_HEIGHT + self.VPAD)
        return x, y

    def _on_canvas_configure(self, _event):
        prev_cols = self.items_per_row
        self._compute_layout()
        # Update scrollregion and reflow tiles if columns changed
        if self.items_per_row != prev_cols:
            self._update_scrollregion()
            # Recreate visible tiles to match new positions/widths
            self._refresh_visible_tiles(recreate=True)
        else:
            # Only check visibility/positions
            self._check_visibility()

    def _on_mousewheel(self, event):
        if not self.canvas.winfo_exists():
            return
        # Windows delta is typically ±120
        delta = -1 * int(event.delta / 120)
        self.canvas.yview_scroll(delta, "units")
        self.after(1, self._check_visibility)
        return "break"

    def _on_mousewheel_global(self, event):
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget and (
            widget == self.canvas or str(widget).startswith(str(self.canvas))
        ):
            return self._on_mousewheel(event)

    def _on_canvas_yscroll(self, *args):
        """Sync scrollbar position and trigger virtualization when the canvas scrolls."""
        self.scrollbar.set(*args)
        # Canvas just moved; schedule visibility check
        self.after(1, self._check_visibility)

    def _on_scrollbar(self, *args):
        """Route scrollbar actions to the canvas and update visible tiles."""
        # args are ('moveto', fraction) or ('scroll', number, 'units'|'pages')
        self.canvas.yview(*args)
        self.after(1, self._check_visibility)

    def _update_scrollregion(self):
        total_rows = (
            len(self.filtered_items) + self.items_per_row - 1
        ) // self.items_per_row
        total_height = self.VPAD + total_rows * (self.CARD_HEIGHT + self.VPAD)
        # width can be full canvas width; height defines vertical range
        self.canvas.configure(
            scrollregion=(0, 0, max(1, self.canvas.winfo_width()), total_height)
        )

    def _update_display(self):
        # Clear any existing tiles
        self._destroy_all_tiles()

        if not self.filtered_items:
            # Show empty state text directly on the canvas
            self.canvas.delete("emptystate")
            self.canvas.delete("all")  # clear any residual items
            msg = "No items loaded. Click 'Load Items' to begin."
            self.canvas.create_text(
                self.canvas.winfo_width() // 2,
                80,
                text=msg,
                fill="#cccccc",
                font=("Segoe UI", 12),
                tags=("emptystate",),
            )
            self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), 0))
            return

        # Compute layout and scrollregion, then render visible slice
        self._compute_layout()
        self._update_scrollregion()
        self.canvas.delete("emptystate")
        # Ensure we start at the top on a fresh load
        self.canvas.yview_moveto(0)
        self._check_visibility(force_recreate=True)

    def _destroy_all_tiles(self):
        for idx, (win_id, frame) in list(self.visible_tiles.items()):
            try:
                if frame and frame.winfo_exists():
                    frame.destroy()
                if win_id:
                    self.canvas.delete(win_id)
            except Exception:
                pass
        self.visible_tiles.clear()

    def _refresh_visible_tiles(self, recreate: bool = False):
        """Refresh positions/sizes of currently visible tiles. If recreate=True, destroy and re-create."""
        if recreate:
            indices = list(self.visible_tiles.keys())
            self._destroy_all_tiles()
            for idx in indices:
                self._create_item_tile(idx)
        else:
            for idx, (win_id, frame) in list(self.visible_tiles.items()):
                x, y = self._tile_xy(idx)
                try:
                    self.canvas.coords(win_id, x, y)
                    self.canvas.itemconfigure(
                        win_id, width=self.card_width, height=self.CARD_HEIGHT
                    )
                except Exception:
                    # If the window was removed, recreate it
                    self._create_item_tile(idx)

    def _check_visibility(self, force_recreate: bool = False):
        if not self.filtered_items:
            return
        first_idx, last_idx = self._index_bounds_for_view()

        # Remove tiles that are no longer in the visible range
        for idx in list(self.visible_tiles.keys()):
            if idx < first_idx or idx >= last_idx:
                win_id, frame = self.visible_tiles.pop(idx)
                try:
                    if frame and frame.winfo_exists():
                        frame.destroy()
                    self.canvas.delete(win_id)
                except Exception:
                    pass

        # Add tiles that should be visible
        for idx in range(first_idx, last_idx):
            if idx not in self.visible_tiles and idx < len(self.filtered_items):
                self._create_item_tile(idx)
            elif idx in self.visible_tiles and force_recreate:
                # Recreate to apply new width/positions cleanly
                win_id, frame = self.visible_tiles.pop(idx)
                try:
                    if frame and frame.winfo_exists():
                        frame.destroy()
                    self.canvas.delete(win_id)
                except Exception:
                    pass
                self._create_item_tile(idx)

        # Update positions for all visible tiles (in case of resize)
        self._refresh_visible_tiles(recreate=False)

    # -----------------------------
    # Tile creation & interactions
    # -----------------------------
    def _create_item_tile(self, idx: int):
        item = self.filtered_items[idx]
        x, y = self._tile_xy(idx)

        tile = tk.Frame(self.canvas, relief="solid", bd=1, bg="#2a2a2a")
        tile.configure(width=self.card_width, height=self.CARD_HEIGHT)
        tile.pack_propagate(False)

        # Header with hero/category and delete button
        header = tk.Frame(tile, bg="#2a2a2a", height=30)
        header.pack(fill="x")
        header.pack_propagate(False)

        left = tk.Frame(header, bg="#2a2a2a")
        left.pack(side="left", fill="both", expand=True)

        hero_text = f"📁 {item.hero_name}"
        if item.category != "MISC":
            hero_text += f" [{item.category}]"
        tk.Label(
            left,
            text=hero_text,
            fg="#ffffff",
            bg="#2a2a2a",
            font=("Exocet", 11, "bold"),
        ).pack(pady=4)

        tk.Button(
            header,
            text="✕",
            fg="#ff6666",
            bg="#2a2a2a",
            font=("Arial", 10, "bold"),
            bd=0,
            cursor="hand2",
            activebackground="#3a3a3a",
            activeforeground="#ff9999",
            command=lambda itm=item: self._delete_item(itm),
        ).pack(side="right", padx=(0, 5), pady=2)

        # Item body
        body = tk.Text(
            tile,
            wrap="word",
            bg="#121212",
            fg="#5959C7",
            font=("Exocet", 11),
            relief="flat",
            borderwidth=0,
            cursor="arrow",
        )
        # Determine a reasonable height from content (clamped)
        lines = item.text.count("\n") + 1
        lines += len(item.text) // 35
        height = max(6, min(20, lines + 1))
        body.config(height=height)
        body.pack(padx=6, pady=(0, 6), fill="both", expand=True)
        body.insert("1.0", item.text)
        body.config(state="disabled")

        # Mousewheel support inside tiles
        tile.bind("<MouseWheel>", self._on_mousewheel)
        header.bind("<MouseWheel>", self._on_mousewheel)
        body.bind("<MouseWheel>", self._on_mousewheel)

        win_id = self.canvas.create_window(
            x,
            y,
            anchor="nw",
            window=tile,
            width=self.card_width,
            height=self.CARD_HEIGHT,
        )
        self.visible_tiles[idx] = (win_id, tile)

    def _delete_item(self, item: Item):
        # Confirmation dialog
        dialog = tk.Toplevel(self)
        dialog.title("Delete Item")
        dialog.resizable(False, False)
        dialog.configure(bg="#1e1e1e")
        dialog.withdraw()

        sw, sh = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        dw, dh = 400, 200
        x = (sw - dw) // 2
        y = (sh - dh) // 2
        dialog.geometry(f"{dw}x{dh}+{x}+{y}")
        dialog.transient(self)
        dialog.grab_set()

        name = item.text.split("\n")[0] if item.text else "this item"

        msgf = tk.Frame(dialog, bg="#1e1e1e")
        msgf.pack(fill="both", expand=True, padx=20, pady=20)
        tk.Label(
            msgf,
            text=f"Are you sure you want to delete:\n\n{name}\n\nfrom the catalog?",
            bg="#1e1e1e",
            fg="#ffffff",
            font=("Segoe UI", 10),
            wraplength=350,
        ).pack(pady=(0, 15))

        var_delete_from_file = tk.BooleanVar(value=False)
        tk.Checkbutton(
            msgf,
            text="Also delete from source file (permanent)",
            variable=var_delete_from_file,
            bg="#1e1e1e",
            fg="#ffffff",
            selectcolor="#1e1e1e",
            activebackground="#1e1e1e",
            activeforeground="#ffffff",
            font=("Segoe UI", 9),
        ).pack()

        btnf = tk.Frame(dialog, bg="#1e1e1e")
        btnf.pack(fill="x", padx=20, pady=(0, 20))

        def confirm_delete():
            try:
                if var_delete_from_file.get():
                    success = remove_item_from_file(item)
                    if not success:
                        messagebox.showwarning(
                            APP_TITLE,
                            "Could not remove item from file. It may have been already modified.",
                        )
                if item in self.items:
                    self.items.remove(item)
                folder_path = self.var_items_folder.get()
                save_items_cache(self.items, folder_path)
                self._apply_filters()
                self._update_count()
                dialog.destroy()
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"Error deleting item: {e}")
                dialog.destroy()

        tk.Button(
            btnf,
            text="Delete",
            command=confirm_delete,
            bg="#d32f2f",
            fg="#ffffff",
            width=10,
            relief="flat",
            cursor="hand2",
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            btnf,
            text="Cancel",
            command=dialog.destroy,
            bg="#333333",
            fg="#ffffff",
            width=10,
            relief="flat",
            cursor="hand2",
        ).pack(side="left")

        btnf.winfo_children()[1].focus_set()
        dialog.deiconify()

    # -----------------------------
    # Count / stats
    # -----------------------------
    def _update_count(self):
        category_counts: Dict[str, int] = {}
        for item in self.items:
            category_counts[item.category] = category_counts.get(item.category, 0) + 1
        if self.items:
            count_text = f"{len(self.items)} items"
            if category_counts:
                details = ", ".join(
                    [
                        f"{cat}: {count}"
                        for cat, count in sorted(category_counts.items())
                    ]
                )
                count_text += f" ({details})"
        else:
            count_text = "No items loaded"
        self.lbl_count.config(text=count_text)
