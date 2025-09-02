"""Dark theme styling for D2R AI Item Tracker."""

import tkinter as tk
from tkinter import ttk


def apply_dark_theme(root):
    """Apply dark theme to the application."""
    DARK_BG = "#1e1e1e"
    PANEL_BG = "#242424"  # section panels / labelframes
    RAISED_BG = "#2a2a2a"  # fields
    TEXT_FG = "#ffffff"
    MUTED_FG = "#c7c7c7"
    ACCENT_BG = "#333333"
    HILIGHT = "#3a3a3a"

    root.configure(bg=DARK_BG)
    # Defaults for classic tk widgets
    root.option_add("*Background", DARK_BG)
    root.option_add("*Foreground", TEXT_FG)
    root.option_add("*insertBackground", TEXT_FG)
    root.option_add("*selectBackground", DARK_BG)
    root.option_add("*selectForeground", TEXT_FG)
    root.option_add("*highlightThickness", 0)

    style = ttk.Style()
    # 'clam' is most re-colorable across platforms
    try:
        style.theme_use("clam")
    except tk.TclError:
        style.theme_use(style.theme_use())

    # Notebook
    style.configure("TNotebook", background=DARK_BG, borderwidth=0)
    style.configure(
        "TNotebook.Tab", background=ACCENT_BG, foreground=TEXT_FG, padding=(10, 6)
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", HILIGHT)],
        foreground=[("disabled", MUTED_FG)],
    )

    # Frames / LabelFrames
    style.configure("TFrame", background=DARK_BG)
    style.configure("TLabelframe", background=PANEL_BG, bordercolor=HILIGHT)
    style.configure("TLabelframe.Label", background=PANEL_BG, foreground=TEXT_FG)

    # Labels / Buttons
    style.configure("TLabel", background=DARK_BG, foreground=TEXT_FG)
    style.configure("TButton", background=ACCENT_BG, foreground=TEXT_FG, borderwidth=1)
    style.map(
        "TButton",
        background=[("active", HILIGHT), ("disabled", "#555555")],
        foreground=[("disabled", "#9a9a9a")],
    )

    # Entry / Combobox
    style.configure(
        "TEntry", fieldbackground=RAISED_BG, foreground=TEXT_FG, bordercolor=HILIGHT
    )
    style.map(
        "TEntry",
        fieldbackground=[("disabled", "#1b1b1b")],
        foreground=[("disabled", "#888888")],
    )
    style.configure(
        "Dark.TCheckbutton",
        background="#1e1e1e",
        foreground="#ffffff",
    )
    style.map(
        "Dark.TCheckbutton",
        background=[("active", "#2a2a2a")],
        foreground=[("disabled", "#9a9a9a")],
    )

    style.configure(
        "TCombobox",
        fieldbackground=RAISED_BG,
        background=RAISED_BG,
        foreground=TEXT_FG,
        bordercolor=HILIGHT,
        selectbackground=ACCENT_BG,
        selectforeground=TEXT_FG,
        arrowcolor=TEXT_FG
    )
    
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", RAISED_BG), ("disabled", "#1b1b1b")],
        foreground=[("readonly", TEXT_FG), ("disabled", "#888888")],
        selectbackground=[("readonly", ACCENT_BG)],
        selectforeground=[("readonly", TEXT_FG)]
    )
    
    # Make the dropdown list dark (clam supports this)
    style.configure("ComboboxPopdownFrame", background=RAISED_BG)
    style.configure(
        "Treeview",
        background=RAISED_BG,
        foreground=TEXT_FG,
        fieldbackground=RAISED_BG,
        bordercolor=HILIGHT,
    )
    style.map(
        "Treeview",
        background=[("selected", "#444444")],
        foreground=[("disabled", MUTED_FG)],
    )

    # Scrollbars / Progressbar
    style.configure("TScrollbar", background=ACCENT_BG, troughcolor=DARK_BG)
    style.configure("TProgressbar", background="#6a6a6a", troughcolor=DARK_BG)
