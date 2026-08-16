"""Generate tab: `npmpi gen` (the static-HTML dashboard) as a form. Saves the
site/output/title choice to config.json first (mirroring what the CLI's
own interactive first-run prompt would save), then calls the real cmd_gen
unchanged via the stdout-capture runner - guaranteed non-interactive since
the config is already valid by the time cmd_gen runs.

Fields live in one FlowRow (see widgets.py) that packs left to right and
wraps onto a second row only when the window's too narrow to fit
everything on one line."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog
from types import SimpleNamespace

import customtkinter as ctk

from npmpi.commands.gen import DEFAULT_TITLE, cmd_gen
from npmpi.config import write_config
from npmpi.gui.runner import run_captured
from npmpi.gui.widgets import FlowRow


class GenTab:
    def __init__(self, parent, app) -> None:
        self.app = app
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)

        self.form = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.form.pack(fill="x", pady=(0, 10))

        self.row1 = ctk.CTkFrame(self.form, fg_color="transparent")
        self.row1.pack(fill="x")
        self.row2 = ctk.CTkFrame(self.form, fg_color="transparent")
        self.row2.pack(fill="x", pady=(8, 0))

        self.site_var = tk.StringVar()
        self.site_menu = ctk.CTkOptionMenu(self.form, variable=self.site_var, values=[])

        # No textvariable - always starts empty, needs the placeholder to work
        # (see add_tab.py's note on why textvariable + placeholder_text conflict).
        # Its .get()/.set() still work the same as a StringVar would.
        self.output_var = ctk.CTkEntry(self.form, width=320,
                                        placeholder_text=r"e.g. \\server\share\home-services\index.html")
        self.browse_btn = ctk.CTkButton(self.form, text="Browse...", width=90, command=self._browse)

        self.title_var = tk.StringVar(value=DEFAULT_TITLE)
        self.title_entry = ctk.CTkEntry(self.form, textvariable=self.title_var, width=180, placeholder_text="Page title")

        self.run_btn = ctk.CTkButton(self.form, text="Save & Generate", width=140, command=self._run)

        self.flow = FlowRow(
            container=self.form, row1=self.row1, row2=self.row2,
            items=[
                (self.site_menu, 0),
                (self.output_var, 8),
                (self.browse_btn, 8),
                (self.title_entry, 8),
                (self.run_btn, 8),
            ],
            wrap_index=3,
        )

        self.error_label = ctk.CTkLabel(self.frame, text="", text_color="#e05656")
        self.error_label.pack(fill="x")

        self.output = ctk.CTkTextbox(self.frame, font=ctk.CTkFont(family="Consolas", size=12))
        self.output.pack(fill="both", expand=True, pady=(8, 0))

        self.on_config_reloaded()
        self.form.after(100, self.flow.relayout)  # initial pass, once geometry has settled

    def on_config_reloaded(self) -> None:
        site_keys = list(self.app.cfg.get("sites", {}).keys())
        self.site_menu.configure(values=site_keys)
        gen = self.app.cfg.get("gen", {})
        default_site = gen.get("site") if gen.get("site") in site_keys else (site_keys[0] if site_keys else "")
        if self.site_var.get() not in site_keys:
            self.site_var.set(default_site)
        if gen.get("output") and not self.output_var.get():
            self.output_var.set(gen["output"])
        if gen.get("title") and self.title_var.get() == DEFAULT_TITLE:
            self.title_var.set(gen["title"])
        self.flow.relayout()

    def _browse(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Where should index.html be written?",
            defaultextension=".html", initialfile="index.html",
        )
        if path:
            self.output_var.set(path)

    def _run(self) -> None:
        self.error_label.configure(text="")
        site = self.site_var.get()
        output = self.output_var.get().strip()
        title = self.title_var.get().strip() or DEFAULT_TITLE

        if not site:
            self.error_label.configure(text="No site configured yet - see the Setup tab.")
            return
        if not output:
            self.error_label.configure(text="Output path is required.")
            return

        self.app.cfg["gen"] = {"enabled": True, "site": site, "output": output, "title": title}
        write_config(self.app.cfg)

        args = SimpleNamespace(output=None, title=None)
        cfg, creds = self.app.cfg, self.app.creds

        self.output.delete("1.0", "end")
        self.run_btn.configure(state="disabled", text="Working...")

        def done(rc, error) -> None:
            self.run_btn.configure(state="normal", text="Save & Generate")
            if error is not None:
                self.output.insert("end", f"\nFAILED: {error}\n")

        run_captured(self.output, lambda: cmd_gen(cfg, creds, args), on_done=done)
