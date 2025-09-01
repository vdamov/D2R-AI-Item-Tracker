"""Item Tracker Tab GUI component for D2R AI Item Tracker."""

import os
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from config import APP_TITLE, DEFAULTS, DEFAULT_OUTPUT_NAME
from processor import Processor
from utils import ensure_txt_path, save_text_atomic


class ItemTrackerTab(ttk.Frame):
    """GUI tab for processing screenshot images."""
    
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
        """Build the user interface for the tracker tab."""
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
            frm_top,
            text="Show",
            variable=self._show_key,
            command=self._toggle_key,
            style="Dark.TCheckbutton",
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
        """Toggle API key visibility."""
        self._key_entry.configure(show="" if self._show_key.get() else "*")

    def _pick_folder(self):
        """Open folder selection dialog."""
        folder = filedialog.askdirectory(title="Select D2R Screenshots Folder")
        if folder:
            folder_path = str(Path(folder).resolve())
            self.var_folder.set(folder_path)
            if not self.var_output.get():
                output_path = str(Path(folder_path) / DEFAULT_OUTPUT_NAME)
                self.var_output.set(output_path)

    def _pick_output(self):
        """Open output file selection dialog."""
        current_folder = self.var_folder.get() or str(Path.cwd())
        initial = self.var_output.get() or str(
            Path(current_folder) / DEFAULT_OUTPUT_NAME
        )

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
        """Validate user input before processing."""
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
        fixed = ensure_txt_path(
            self.var_output.get().strip(), folder, DEFAULT_OUTPUT_NAME
        )
        self.var_output.set(str(Path(fixed).resolve()))

        return True

    def _progress_update(self, done: int, total: int):
        """Thread-safe progress update."""
        def update():
            pct = int(done * 100 / max(1, total))
            self.prog["value"] = pct

        self.after(0, update)

    def _processing_done(self, content: str):
        """Thread-safe completion handler."""
        def finish():
            try:
                if content:  # Only save if we have content
                    out_path = ensure_txt_path(
                        self.p["output"], self.p["folder"], DEFAULT_OUTPUT_NAME
                    )
                    saved_to = save_text_atomic(out_path, content)
                    self.log_q.put(f"\n✅ Saved to: {saved_to}")
                else:
                    self.log_q.put("\n❌ No content to save.")
            except PermissionError as e:
                # Fallback to a safe, user-writable dir if Defender blocks Documents
                fallback = (
                    Path(os.getenv("LOCALAPPDATA", str(Path.home())))
                    / "D2R-AI-Item-Tracker"
                    / DEFAULT_OUTPUT_NAME
                )
                try:
                    fallback.parent.mkdir(parents=True, exist_ok=True)
                    saved_to = save_text_atomic(str(fallback), content)
                    self.log_q.put(
                        f"\n⚠️ Write blocked in selected folder. Saved to: {saved_to}"
                    )
                except Exception as e2:
                    self.log_q.put(
                        f"[fatal] Could not save output (blocked): {e}; fallback failed: {e2}"
                    )
            except Exception as e:
                self.log_q.put(f"[fatal] Could not save output: {e}")
            finally:
                self.btn_run.config(state="normal")
                self.btn_stop.config(state="disabled")
                self.worker = None

        self.after(0, finish)

    def _run(self):
        """Start the processing."""
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
            self.stop_flag,
        )
        self.worker.start()

    def _stop(self):
        """Stop the processing."""
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
        """Poll log messages from the worker thread."""
        try:
            while True:
                msg = self.log_q.get_nowait()
                self.txt.insert("end", msg + "\n")
                self.txt.see("end")
        except queue.Empty:
            pass
        self.after(100, self._poll_logs)