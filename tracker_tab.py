"""Item Tracker Tab GUI component for D2R AI Item Tracker."""

import os
import queue
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, scrolledtext

from config import APP_TITLE, DEFAULTS, DEFAULT_OUTPUT_NAME
from processor import Processor
from cache import load_settings_cache


class ItemTrackerTab(ttk.Frame):
    """GUI tab for tracking and processing items from screenshots."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.processor_thread = None
        self.stop_flag = {"stop": False}
        self.log_queue = queue.Queue()

        # Load cached settings
        cached_settings = load_settings_cache()

        # Initialize variables with cached values or defaults
        self.var_endpoint = tk.StringVar(
            value=cached_settings.get("VISION_ENDPOINT", DEFAULTS["VISION_ENDPOINT"])
        )
        self.var_model = tk.StringVar(
            value=cached_settings.get("VISION_MODEL", DEFAULTS["VISION_MODEL"])
        )
        self.var_api_key = tk.StringVar(
            value=cached_settings.get("VISION_API_KEY", DEFAULTS["VISION_API_KEY"])
        )
        self.var_folder = tk.StringVar(
            value=cached_settings.get(
                "SCREENSHOTS_FOLDER", DEFAULTS["SCREENSHOTS_FOLDER"]
            )
        )
        self.var_output = tk.StringVar(
            value=cached_settings.get("OUTPUT_FILE", DEFAULTS["OUTPUT_FILE"])
        )
        self.var_workers = tk.StringVar(
            value=cached_settings.get("MAX_WORKERS", DEFAULTS["MAX_WORKERS"])
        )
        self.var_retries = tk.StringVar(
            value=cached_settings.get("MAX_RETRIES", DEFAULTS["MAX_RETRIES"])
        )
        self.var_retry_delay = tk.StringVar(
            value=cached_settings.get("RETRY_DELAY", DEFAULTS["RETRY_DELAY"])
        )
        self.var_timeout = tk.StringVar(
            value=cached_settings.get("REQUEST_TIMEOUT", DEFAULTS["REQUEST_TIMEOUT"])
        )
        self.var_rpm = tk.StringVar(
            value=cached_settings.get("RATE_LIMIT_RPM", DEFAULTS["RATE_LIMIT_RPM"])
        )
        self.var_jitter = tk.StringVar(
            value=cached_settings.get("RATE_JITTER_MS", DEFAULTS["RATE_JITTER_MS"])
        )

        self._build_ui()

        # Start log queue processor
        self.after(100, self._process_log_queue)

    def _build_ui(self):
        """Build the user interface for the tab."""
        pad = {"padx": 8, "pady": 6}

        # API Configuration
        frm_api = ttk.LabelFrame(self, text="API Configuration")
        frm_api.pack(fill="x", **pad)

        ttk.Label(frm_api, text="Endpoint:").grid(row=0, column=0, sticky="e")
        ttk.Entry(frm_api, textvariable=self.var_endpoint, width=50).grid(
            row=0, column=1, sticky="we", columnspan=3
        )

        ttk.Label(frm_api, text="Model:").grid(row=1, column=0, sticky="e")
        ttk.Entry(frm_api, textvariable=self.var_model, width=50).grid(
            row=1, column=1, sticky="we", columnspan=3
        )

        ttk.Label(frm_api, text="API Key:").grid(row=2, column=0, sticky="e")
        self.entry_api_key = ttk.Entry(
            frm_api, textvariable=self.var_api_key, show="*", width=50
        )
        self.entry_api_key.grid(row=2, column=1, sticky="we")

        self.btn_show_key = ttk.Button(
            frm_api, text="Show", width=8, command=self._toggle_api_key_visibility
        )
        self.btn_show_key.grid(row=2, column=2, padx=(4, 0))

        frm_api.grid_columnconfigure(1, weight=1)

        # Processing Settings
        frm_settings = ttk.LabelFrame(self, text="Processing Settings")
        frm_settings.pack(fill="x", **pad)

        ttk.Label(frm_settings, text="Screenshots:").grid(row=0, column=0, sticky="e")
        ttk.Entry(frm_settings, textvariable=self.var_folder, width=50).grid(
            row=0, column=1, sticky="we"
        )
        ttk.Button(frm_settings, text="Browse…", command=self._pick_folder).grid(
            row=0, column=2
        )

        ttk.Label(frm_settings, text="Output file:").grid(row=1, column=0, sticky="e")
        ttk.Entry(frm_settings, textvariable=self.var_output, width=50).grid(
            row=1, column=1, sticky="we"
        )
        ttk.Button(frm_settings, text="Browse…", command=self._pick_output).grid(
            row=1, column=2
        )

        frm_settings.grid_columnconfigure(1, weight=1)

        # Limits & Retries
        frm_limits = ttk.LabelFrame(self, text="Limits & Retries")
        frm_limits.pack(fill="x", **pad)

        # Configure grid columns for even distribution
        for col in range(6):
            frm_limits.grid_columnconfigure(col, weight=1)

        # First row - Workers, Retries, Delay
        ttk.Label(frm_limits, text="Workers:").grid(
            row=0, column=0, sticky="e", padx=(8, 4)
        )
        worker_spinbox = tk.Spinbox(
            frm_limits,
            from_=1,
            to=10,
            textvariable=self.var_workers,
            width=8,
            bg="#2b2b2b",
            fg="#ffffff",
            insertbackground="#ffffff",
            selectbackground="#0d6efd",
            selectforeground="#ffffff",
            buttonbackground="#3c3c3c",
            relief="flat",
            bd=1,
        )
        worker_spinbox.grid(row=0, column=1, sticky="w", padx=(4, 8))

        ttk.Label(frm_limits, text="Max Retries:").grid(
            row=0, column=2, sticky="e", padx=(8, 4)
        )
        tk.Spinbox(
            frm_limits,
            from_=1,
            to=10,
            textvariable=self.var_retries,
            width=8,
            bg="#2b2b2b",
            fg="#ffffff",
            insertbackground="#ffffff",
            selectbackground="#0d6efd",
            selectforeground="#ffffff",
            buttonbackground="#3c3c3c",
            relief="flat",
            bd=1,
        ).grid(row=0, column=3, sticky="w", padx=(4, 8))

        ttk.Label(frm_limits, text="Retry Delay (s):").grid(
            row=0, column=4, sticky="e", padx=(8, 4)
        )
        tk.Spinbox(
            frm_limits,
            from_=1,
            to=60,
            textvariable=self.var_retry_delay,
            width=8,
            bg="#2b2b2b",
            fg="#ffffff",
            insertbackground="#ffffff",
            selectbackground="#0d6efd",
            selectforeground="#ffffff",
            buttonbackground="#3c3c3c",
            relief="flat",
            bd=1,
        ).grid(row=0, column=5, sticky="w", padx=(4, 8))

        # Second row - Timeout, Rate Limit, Jitter
        ttk.Label(frm_limits, text="Timeout (s):").grid(
            row=1, column=0, sticky="e", padx=(8, 4), pady=(4, 4)
        )
        tk.Spinbox(
            frm_limits,
            from_=30,
            to=300,
            textvariable=self.var_timeout,
            width=8,
            bg="#2b2b2b",
            fg="#ffffff",
            insertbackground="#ffffff",
            selectbackground="#0d6efd",
            selectforeground="#ffffff",
            buttonbackground="#3c3c3c",
            relief="flat",
            bd=1,
        ).grid(row=1, column=1, sticky="w", padx=(4, 8), pady=(4, 4))

        ttk.Label(frm_limits, text="Rate Limit (RPM):").grid(
            row=1, column=2, sticky="e", padx=(8, 4), pady=(4, 4)
        )
        tk.Spinbox(
            frm_limits,
            from_=1,
            to=120,
            textvariable=self.var_rpm,
            width=8,
            bg="#2b2b2b",
            fg="#ffffff",
            insertbackground="#ffffff",
            selectbackground="#0d6efd",
            selectforeground="#ffffff",
            buttonbackground="#3c3c3c",
            relief="flat",
            bd=1,
        ).grid(row=1, column=3, sticky="w", padx=(4, 8), pady=(4, 4))

        ttk.Label(frm_limits, text="Jitter (ms):").grid(
            row=1, column=4, sticky="e", padx=(8, 4), pady=(4, 4)
        )
        tk.Spinbox(
            frm_limits,
            from_=0,
            to=5000,
            textvariable=self.var_jitter,
            width=8,
            bg="#2b2b2b",
            fg="#ffffff",
            insertbackground="#ffffff",
            selectbackground="#0d6efd",
            selectforeground="#ffffff",
            buttonbackground="#3c3c3c",
            relief="flat",
            bd=1,
        ).grid(row=1, column=5, sticky="w", padx=(4, 8), pady=(4, 4))

        # Control buttons
        frm_controls = ttk.Frame(self)
        frm_controls.pack(fill="x", **pad)

        self.btn_run = ttk.Button(
            frm_controls, text="Run", command=self._start_processing
        )
        self.btn_run.pack(side="left", padx=(0, 8))

        self.btn_stop = ttk.Button(
            frm_controls, text="Stop", command=self._stop_processing, state="disabled"
        )
        self.btn_stop.pack(side="left", padx=(0, 8))

        self.btn_clear = ttk.Button(
            frm_controls, text="Clear Log", command=self._clear_log
        )
        self.btn_clear.pack(side="left")

        # Progress bar
        self.progress = ttk.Progressbar(frm_controls, mode="determinate")
        self.progress.pack(side="right", fill="x", expand=True, padx=(16, 0))

        # Log output
        frm_log = ttk.LabelFrame(self, text="Log")
        frm_log.pack(fill="both", expand=True, **pad)

        self.txt_log = scrolledtext.ScrolledText(
            frm_log,
            wrap=tk.WORD,
            height=10,
            bg="#1e1e1e",
            fg="#cccccc",
            font=("Consolas", 9),
        )
        self.txt_log.pack(fill="both", expand=True, padx=4, pady=4)

    def _toggle_api_key_visibility(self):
        """Toggle the visibility of the API key."""
        if self.entry_api_key["show"] == "*":
            self.entry_api_key.config(show="")
            self.btn_show_key.config(text="Hide")
        else:
            self.entry_api_key.config(show="*")
            self.btn_show_key.config(text="Show")

    def _pick_folder(self):
        """Open folder selection dialog for screenshots."""
        folder = filedialog.askdirectory(title="Select Screenshots Folder")
        if folder:
            folder_path = str(Path(folder).resolve())
            self.var_folder.set(folder_path)

    def _pick_output(self):
        """Open file selection dialog for output file."""
        # Get the current screenshots folder to suggest as initial directory
        screenshots_folder = self.var_folder.get().strip()
        if screenshots_folder and Path(screenshots_folder).is_dir():
            initial_dir = screenshots_folder
        else:
            initial_dir = os.getcwd()

        file = filedialog.asksaveasfilename(
            title="Save Output As",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=initial_dir,
            initialfile=DEFAULT_OUTPUT_NAME,
        )
        if file:
            file_path = str(Path(file).resolve())
            self.var_output.set(file_path)

    def _clear_log(self):
        """Clear the log text widget."""
        self.txt_log.delete("1.0", tk.END)

    def _log(self, msg):
        """Add a message to the log."""
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)

    def _process_log_queue(self):
        """Process messages from the log queue."""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self._log(msg)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_log_queue)

    def _update_progress(self, current, total):
        """Update the progress bar."""
        if total > 0:
            self.progress["value"] = (current / total) * 100
        else:
            self.progress["value"] = 0

    def _on_processing_done(self, content):
        """Handle processing completion."""
        # Re-enable controls
        self.btn_run.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.progress["value"] = 0

        if content:
            # Save to output file
            output_file = self.var_output.get().strip()
            if not output_file:
                # Default to screenshots folder
                folder = self.var_folder.get().strip()
                if folder:
                    output_file = str(Path(folder) / DEFAULT_OUTPUT_NAME)
                else:
                    output_file = DEFAULT_OUTPUT_NAME
                self.var_output.set(output_file)

            try:
                # Try to save to the specified location
                Path(output_file).write_text(content, encoding="utf-8")
                self._log(f"[success] Results saved to: {output_file}")
            except PermissionError as e:
                # Fall back to local app data if permission denied
                fallback_dir = (
                    Path(os.getenv("LOCALAPPDATA", "")) / "D2R-AI-Item-Tracker"
                )
                fallback_dir.mkdir(parents=True, exist_ok=True)
                fallback_file = fallback_dir / Path(output_file).name
                try:
                    fallback_file.write_text(content, encoding="utf-8")
                    self._log(f"[warning] Permission denied for original location")
                    self._log(f"[success] Results saved to: {fallback_file}")
                    self.var_output.set(str(fallback_file))
                except Exception as fallback_error:
                    self._log(f"[error] Failed to save results: {fallback_error}")
            except Exception as e:
                self._log(f"[error] Failed to save results: {e}")
        else:
            self._log("[done] Processing completed (no valid output).")

        self.processor_thread = None

    def _validate_inputs(self):
        """Validate user inputs before processing."""
        if not self.var_endpoint.get().strip():
            messagebox.showerror(APP_TITLE, "Please enter the API endpoint.")
            return False

        if not self.var_model.get().strip():
            messagebox.showerror(APP_TITLE, "Please enter the model name.")
            return False

        if not self.var_api_key.get().strip():
            messagebox.showerror(APP_TITLE, "Please enter your API key.")
            return False

        folder = self.var_folder.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showerror(APP_TITLE, "Please select a valid screenshots folder.")
            return False

        return True

    def _start_processing(self):
        """Start the processing thread."""
        if not self._validate_inputs():
            return

        # Disable controls
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.progress["value"] = 0

        # Reset stop flag
        self.stop_flag["stop"] = False

        # Prepare parameters
        params = {
            "folder": self.var_folder.get().strip(),
            "VISION_ENDPOINT": self.var_endpoint.get().strip(),
            "VISION_MODEL": self.var_model.get().strip(),
            "VISION_API_KEY": self.var_api_key.get().strip(),
            "MAX_WORKERS": self.var_workers.get().strip(),
            "MAX_RETRIES": self.var_retries.get().strip(),
            "RETRY_DELAY": self.var_retry_delay.get().strip(),
            "REQUEST_TIMEOUT": self.var_timeout.get().strip(),
            "RATE_LIMIT_RPM": self.var_rpm.get().strip(),
            "RATE_JITTER_MS": self.var_jitter.get().strip(),
        }

        # Start processor thread
        self.processor_thread = Processor(
            params,
            self.log_queue,
            self._update_progress,
            self._on_processing_done,
            self.stop_flag,
        )
        self.processor_thread.start()

        self._log("[info] Processing started...")

    def _stop_processing(self):
        """Stop the processing thread."""
        if self.processor_thread and self.processor_thread.is_alive():
            self.stop_flag["stop"] = True
            self._log("[info] Stopping processing...")
            self.btn_stop.config(state="disabled")
