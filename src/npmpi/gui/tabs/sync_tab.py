"""Sync tab: `npmpi sync [--dry-run] [--only PREFIX ...] [--repair-pihole]`
as a form. Calls the real cmd_sync unchanged via the stdout-capture
runner - same reasoning as the Add tab."""

from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import customtkinter as ctk

from npmpi.commands.sync import cmd_sync
from npmpi.gui.runner import run_captured


class SyncTab:
    def __init__(self, parent, app) -> None:
        self.app = app
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)

        form = ctk.CTkFrame(self.frame, fg_color="transparent")
        form.pack(fill="x", pady=(0, 10))

        self.dry_run_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(form, text="Dry run (preview only)", variable=self.dry_run_var).grid(
            row=0, column=0, padx=(0, 12), pady=4, sticky="w",
        )

        self.repair_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(form, text="Repair Pi-hole DNS too", variable=self.repair_var).grid(
            row=0, column=1, padx=12, pady=4, sticky="w",
        )

        self.only_var = tk.StringVar()
        ctk.CTkEntry(
            form, textvariable=self.only_var, width=260,
            placeholder_text="Only these prefixes (space-separated, blank = all)",
        ).grid(row=0, column=2, padx=12, pady=4)

        self.run_btn = ctk.CTkButton(form, text="Run", width=90, command=self._run)
        self.run_btn.grid(row=0, column=3, padx=(8, 0), pady=4)

        note = "Only one site configured - sync mirrors nothing until a second site is added." \
            if len(self.app.cfg.get("sites", {})) < 2 else ""
        self.note_label = ctk.CTkLabel(self.frame, text=note, text_color=("gray30", "gray70"))
        self.note_label.pack(fill="x")

        self.output = ctk.CTkTextbox(self.frame, font=ctk.CTkFont(family="Consolas", size=12))
        self.output.pack(fill="both", expand=True, pady=(8, 0))

    def on_config_reloaded(self) -> None:
        note = "Only one site configured - sync mirrors nothing until a second site is added." \
            if len(self.app.cfg.get("sites", {})) < 2 else ""
        self.note_label.configure(text=note)

    def _run(self) -> None:
        only_raw = self.only_var.get().strip()
        only = only_raw.split() if only_raw else None
        args = SimpleNamespace(dry_run=self.dry_run_var.get(), only=only, repair_pihole=self.repair_var.get())
        cfg, creds = self.app.cfg, self.app.creds

        self.output.delete("1.0", "end")
        self.run_btn.configure(state="disabled", text="Running...")

        def done(rc, error) -> None:
            self.run_btn.configure(state="normal", text="Run")
            if error is not None:
                self.output.insert("end", f"\nFAILED: {error}\n")

        run_captured(self.output, lambda: cmd_sync(cfg, creds, args), on_done=done)
