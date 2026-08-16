"""Gen tab: `npmpi gen` (the static-HTML dashboard) as a form. Saves the
site/output/title choice to config.json first (mirroring what the CLI's
own interactive first-run prompt would save), then calls the real cmd_gen
unchanged via the stdout-capture runner - guaranteed non-interactive since
the config is already valid by the time cmd_gen runs."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog
from types import SimpleNamespace

import customtkinter as ctk

from npmpi.commands.gen import DEFAULT_TITLE, cmd_gen
from npmpi.config import write_config
from npmpi.gui.runner import run_captured


class GenTab:
    def __init__(self, parent, app) -> None:
        self.app = app
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)

        form = ctk.CTkFrame(self.frame, fg_color="transparent")
        form.pack(fill="x", pady=(0, 10))

        self.site_var = tk.StringVar()
        self.site_menu = ctk.CTkOptionMenu(form, variable=self.site_var, values=[])
        self.site_menu.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")

        self.output_var = tk.StringVar()
        ctk.CTkEntry(form, textvariable=self.output_var, width=320,
                     placeholder_text=r"e.g. \\server\share\home-services\index.html").grid(
            row=0, column=1, padx=8, pady=4,
        )
        ctk.CTkButton(form, text="Browse...", width=90, command=self._browse).grid(row=0, column=2, padx=8, pady=4)

        self.title_var = tk.StringVar(value=DEFAULT_TITLE)
        ctk.CTkEntry(form, textvariable=self.title_var, width=180, placeholder_text="Page title").grid(
            row=0, column=3, padx=8, pady=4,
        )

        self.run_btn = ctk.CTkButton(form, text="Save & Generate", width=140, command=self._run)
        self.run_btn.grid(row=0, column=4, padx=(8, 0), pady=4)

        self.error_label = ctk.CTkLabel(self.frame, text="", text_color="#e05656")
        self.error_label.pack(fill="x")

        self.output = ctk.CTkTextbox(self.frame, font=ctk.CTkFont(family="Consolas", size=12))
        self.output.pack(fill="both", expand=True, pady=(8, 0))

        self.on_config_reloaded()

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
