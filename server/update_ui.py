"""
OBS Remote update progress dialog.

A native-feeling progress window shown during auto-update, similar to
OBS Studio's own update dialog.  Uses tkinter (bundled with Python).

Thread model
------------
- Create an UpdateDialog instance on any thread.
- Call dialog.run() in a dedicated daemon thread — it blocks on the
  tkinter mainloop.
- Drive it from any other thread via the thread-safe helper methods:
  log(), set_status(), set_progress(), set_indeterminate(), etc.
"""

import threading
import tkinter as tk
from tkinter import ttk


class UpdateDialog:
    """Tkinter update-progress window."""

    def __init__(self, version: str):
        self._version = version
        self._root: tk.Tk | None = None
        self._status_var: tk.StringVar | None = None
        self._progress: ttk.Progressbar | None = None
        self._log_text: tk.Text | None = None
        self._log_frame: tk.Frame | None = None
        self._hide_btn: tk.Button | None = None
        self._cancel_btn: tk.Button | None = None
        self._log_visible = True
        self._cancelled = False
        # Fired once the window is built and mainloop has started
        self._ready = threading.Event()

    # ------------------------------------------------------------------
    # Build / run
    # ------------------------------------------------------------------

    def run(self):
        """Create the window and start the event loop.  Call from a dedicated thread."""
        root = tk.Tk()
        root.title("OBS Remote Update")
        root.geometry("520x310")
        root.resizable(False, False)
        root.configure(bg="#2d2d3f")

        # Centre on screen
        root.update_idletasks()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"+{(sw - 520) // 2}+{(sh - 310) // 2}")
        root.attributes("-topmost", True)

        self._root = root

        # --- Status label ---
        self._status_var = tk.StringVar(
            value=f"Downloading OBS Remote v{self._version}..."
        )
        tk.Label(
            root,
            textvariable=self._status_var,
            anchor="w",
            padx=12,
            pady=8,
            bg="#2d2d3f",
            fg="#e0e0f0",
            font=("Segoe UI", 9),
        ).pack(fill="x")

        # --- Progress bar ---
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Update.Horizontal.TProgressbar",
            troughcolor="#1a1a2e",
            background="#7c3aed",
            thickness=18,
        )
        self._progress = ttk.Progressbar(
            root,
            mode="indeterminate",
            length=496,
            style="Update.Horizontal.TProgressbar",
        )
        self._progress.pack(padx=12, pady=(0, 6), fill="x")
        self._progress.start(8)

        # --- Log area ---
        self._log_frame = tk.Frame(root, bg="#2d2d3f")
        self._log_text = tk.Text(
            self._log_frame,
            height=9,
            wrap="word",
            state="disabled",
            bg="#12121e",
            fg="#99aab5",
            insertbackground="white",
            font=("Consolas", 8),
            relief="flat",
            borderwidth=0,
            padx=6,
            pady=4,
        )
        scroll = tk.Scrollbar(self._log_frame, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._log_text.pack(side="left", fill="both", expand=True)
        self._log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 4))

        # --- Buttons ---
        btn_frame = tk.Frame(root, bg="#2d2d3f")
        btn_frame.pack(fill="x", padx=12, pady=(2, 10))

        self._hide_btn = tk.Button(
            btn_frame,
            text="Hide Log",
            command=self._toggle_log,
            width=10,
            font=("Segoe UI", 8),
            relief="groove",
            cursor="hand2",
        )
        self._hide_btn.pack(side="left")

        self._cancel_btn = tk.Button(
            btn_frame,
            text="Cancel",
            command=self._on_cancel,
            width=10,
            font=("Segoe UI", 8),
            relief="groove",
            cursor="hand2",
        )
        self._cancel_btn.pack(side="right")

        root.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._ready.set()
        root.mainloop()

    # ------------------------------------------------------------------
    # Internal callbacks (run on UI thread)
    # ------------------------------------------------------------------

    def _toggle_log(self):
        if self._log_visible:
            self._log_frame.pack_forget()
            self._hide_btn.config(text="Show Log")
            self._root.geometry("520x130")
            self._log_visible = False
        else:
            self._log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 4))
            self._hide_btn.config(text="Hide Log")
            self._root.geometry("520x310")
            self._log_visible = True

    def _on_cancel(self):
        self._cancelled = True
        if self._root:
            self._root.destroy()
            self._root = None

    def _append_log(self, msg: str):
        if self._log_text:
            self._log_text.configure(state="normal")
            self._log_text.insert("end", msg + "\n")
            self._log_text.see("end")
            self._log_text.configure(state="disabled")

    def _set_det(self, pct: float):
        if self._progress["mode"] == "indeterminate":
            self._progress.stop()
            self._progress.configure(mode="determinate")
        self._progress["value"] = pct

    def _set_indet(self):
        self._progress.configure(mode="indeterminate")
        self._progress.start(8)

    # ------------------------------------------------------------------
    # Thread-safe public API
    # ------------------------------------------------------------------

    def log(self, msg: str):
        """Append a line to the log area (thread-safe)."""
        if self._root:
            self._root.after(0, self._append_log, msg)

    def set_status(self, msg: str):
        """Update the status label (thread-safe)."""
        if self._root and self._status_var:
            self._root.after(0, self._status_var.set, msg)

    def set_progress(self, pct: float):
        """Set determinate progress 0–100 (thread-safe)."""
        if self._root:
            self._root.after(0, self._set_det, pct)

    def set_indeterminate(self):
        """Switch to spinner mode (thread-safe)."""
        if self._root:
            self._root.after(0, self._set_indet)

    def disable_cancel(self):
        """Disable the Cancel button once install begins (thread-safe)."""
        if self._root and self._cancel_btn:
            self._root.after(0, lambda: self._cancel_btn.config(state="disabled"))

    def close(self):
        """Destroy the window (thread-safe)."""
        if self._root:
            self._root.after(0, self._on_cancel)

    @property
    def cancelled(self) -> bool:
        return self._cancelled
