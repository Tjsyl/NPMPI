"""Add tab: the same fields `npmpi add [SITE] NODE-NAME [-s] OCTET PORT`
takes on the command line, as a form. Calls the real cmd_add unchanged
(via the stdout-capture runner) so behavior - including the append-onto-
existing-backend fix - can never drift between the CLI and the GUI."""

from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import customtkinter as ctk

from npmpi.commands.add import cmd_add
from npmpi.gui.runner import run_captured

BOTH_SITES = "Both sites (mirrored)"


class AddTab:
    def __init__(self, parent, app) -> None:
        self.app = app
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)

        form = ctk.CTkFrame(self.frame, fg_color="transparent")
        form.pack(fill="x", pady=(0, 10))

        self.site_var = tk.StringVar(value=BOTH_SITES)
        self.site_menu = ctk.CTkOptionMenu(form, variable=self.site_var, values=[BOTH_SITES])
        self.site_menu.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")

        self.name_var = tk.StringVar()
        ctk.CTkEntry(form, textvariable=self.name_var, placeholder_text="node name, e.g. prowlarr", width=200).grid(
            row=0, column=1, padx=8, pady=4,
        )

        self.https_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(form, text="HTTPS", variable=self.https_var).grid(row=0, column=2, padx=8, pady=4)

        self.octet_var = tk.StringVar()
        ctk.CTkEntry(form, textvariable=self.octet_var, placeholder_text="octet, e.g. 223", width=100).grid(
            row=0, column=3, padx=8, pady=4,
        )

        self.port_var = tk.StringVar()
        ctk.CTkEntry(form, textvariable=self.port_var, placeholder_text="port, e.g. 9696", width=100).grid(
            row=0, column=4, padx=8, pady=4,
        )

        self.add_btn = ctk.CTkButton(form, text="Add", width=90, command=self._run)
        self.add_btn.grid(row=0, column=5, padx=(8, 0), pady=4)

        self.error_label = ctk.CTkLabel(self.frame, text="", text_color="#e05656")
        self.error_label.pack(fill="x")

        self.output = ctk.CTkTextbox(self.frame, font=ctk.CTkFont(family="Consolas", size=12))
        self.output.pack(fill="both", expand=True, pady=(8, 0))

        self.on_config_reloaded()

    def on_config_reloaded(self) -> None:
        site_keys = list(self.app.cfg.get("sites", {}).keys())
        values = [BOTH_SITES] + site_keys
        self.site_menu.configure(values=values)
        if self.site_var.get() not in values:
            self.site_var.set(BOTH_SITES)

    def _run(self) -> None:
        self.error_label.configure(text="")
        name = self.name_var.get().strip()
        octet = self.octet_var.get().strip()
        port = self.port_var.get().strip()

        if not name or not octet or not port:
            self.error_label.configure(text="Name, octet, and port are all required.")
            return
        if not octet.isdigit() or not port.isdigit():
            self.error_label.configure(text="Octet and port must be numbers.")
            return

        site = self.site_var.get()
        if site == BOTH_SITES:
            raw_args = [name, octet, port]
        else:
            raw_args = [site, name, octet, port]

        args = SimpleNamespace(args=raw_args, https=self.https_var.get())
        cfg, creds = self.app.cfg, self.app.creds

        self.output.delete("1.0", "end")
        self.add_btn.configure(state="disabled", text="Adding...")

        def done(rc, error) -> None:
            self.add_btn.configure(state="normal", text="Add")
            if error is not None:
                self.output.insert("end", f"\nFAILED: {error}\n")

        run_captured(self.output, lambda: cmd_add(cfg, creds, args), on_done=done)
