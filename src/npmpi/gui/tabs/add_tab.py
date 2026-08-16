"""Add tab: the same fields `npmpi add [multi] SITE NODE-NAME [-s] OCTET PORT`
takes on the command line, as a form. Calls the real cmd_add unchanged
(via the stdout-capture runner) so behavior - including the append-onto-
existing-backend fix - can never drift between the CLI and the GUI.

Two dropdowns: the mode dropdown (Multi, or a single site key) and the
real-site dropdown (which site the backend actually lives on). In Multi
mode the real-site dropdown is live and picks which site is real - the
hostname is created there and mirrored onto every other site. In
single-site mode there's nothing to choose, so the real-site dropdown just
mirrors that same site and is disabled.

All the fields live in one FlowRow (see widgets.py) that packs left to
right and wraps onto a second row only when the window's too narrow to
fit everything on one line - so widening the window pulls the IP prefix/
octet/port/Add button back up next to the HTTPS checkbox instead of
leaving them stuck on their own line."""

from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import customtkinter as ctk

from npmpi.commands.add import cmd_add
from npmpi.gui.runner import run_captured
from npmpi.gui.widgets import FlowRow

MULTI = "Multi"


class AddTab:
    def __init__(self, parent, app) -> None:
        self.app = app
        self._last_multi_site: str | None = None  # remembers the real-site choice across Multi selections

        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)

        self.form = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.form.pack(fill="x", pady=(0, 10))

        self.row1 = ctk.CTkFrame(self.form, fg_color="transparent")
        self.row1.pack(fill="x")
        self.row2 = ctk.CTkFrame(self.form, fg_color="transparent")
        self.row2.pack(fill="x", pady=(8, 0))

        # Every control's master is self.form - which row (self.row1/row2) each one
        # actually lands in is decided live by the FlowRow built below, not fixed here.
        self.mode_var = tk.StringVar(value=MULTI)
        self.site_menu = ctk.CTkOptionMenu(self.form, variable=self.mode_var, values=[MULTI], command=self._on_mode_change)

        self.real_site_var = tk.StringVar(value="")
        self.real_site_menu = ctk.CTkOptionMenu(
            self.form, variable=self.real_site_var, values=[], command=self._on_real_site_change,
        )

        # No textvariable here - see the placeholder note below.
        self.name_var = ctk.CTkEntry(self.form, placeholder_text="node name, e.g. prowlarr", width=200)

        self.https_var = tk.BooleanVar(value=False)
        self.https_check = ctk.CTkCheckBox(self.form, text="HTTPS", variable=self.https_var)

        # The real site's IP prefix (read-only, updates live) + octet + port + Add
        self.prefix_label = ctk.CTkLabel(
            self.form, text="", font=ctk.CTkFont(family="Consolas", size=13), text_color=("gray30", "gray70"),
        )

        # NOTE: octet_var/port_var deliberately do NOT use a textvariable - CustomTkinter's
        # CTkEntry only activates placeholder_text when textvariable is None (see
        # _activate_placeholder in ctk_entry.py), so a bound StringVar silently kills
        # the placeholder. Read values with the entry's own .get() instead.
        self.octet_var = ctk.CTkEntry(self.form, placeholder_text="octet, e.g. 223", width=100)
        self.port_var = ctk.CTkEntry(self.form, placeholder_text="port, e.g. 9696", width=100)
        self.add_btn = ctk.CTkButton(self.form, text="Add", width=90, command=self._run)

        # (widget, left-padding when it's NOT the first control on its row).
        # Split point when things don't fit on one line: everything from
        # prefix_label onward wraps to row2 together, never mid-group.
        self.flow = FlowRow(
            container=self.form, row1=self.row1, row2=self.row2,
            items=[
                (self.site_menu, 0),
                (self.real_site_menu, 8),
                (self.name_var, 8),
                (self.https_check, 8),
                (self.prefix_label, 16),
                (self.octet_var, 2),
                (self.port_var, 8),
                (self.add_btn, 8),
            ],
            wrap_index=4,
        )

        self.error_label = ctk.CTkLabel(self.frame, text="", text_color="#e05656")
        self.error_label.pack(fill="x")

        self.output = ctk.CTkTextbox(self.frame, font=ctk.CTkFont(family="Consolas", size=12))
        self.output.pack(fill="both", expand=True, pady=(8, 0))

        self.on_config_reloaded()
        self.form.after(100, self.flow.relayout)  # initial pass, once geometry has settled

    def on_config_reloaded(self) -> None:
        site_keys = list(self.app.cfg.get("sites", {}).keys())

        mode_values = [MULTI] + site_keys
        self.site_menu.configure(values=mode_values)
        if self.mode_var.get() not in mode_values:
            self.mode_var.set(MULTI)

        self.real_site_menu.configure(values=site_keys)
        if self._last_multi_site not in site_keys:
            self._last_multi_site = site_keys[0] if site_keys else None

        self._sync_real_site()
        self.flow.relayout()  # site-key text length can change how much fits on one row

    def _on_mode_change(self, _value: str | None = None) -> None:
        self._sync_real_site()

    def _on_real_site_change(self, _value: str | None = None) -> None:
        if self.mode_var.get() == MULTI:
            self._last_multi_site = self.real_site_var.get()
        self._update_prefix_label()

    def _sync_real_site(self) -> None:
        """Keep the real-site dropdown, its enabled/disabled state, and the IP-prefix
        label consistent with whatever's currently selected in the mode dropdown."""
        mode = self.mode_var.get()
        site_keys = list(self.app.cfg.get("sites", {}).keys())

        if mode == MULTI:
            self.real_site_menu.configure(state="normal")
            default = self._last_multi_site if self._last_multi_site in site_keys else (site_keys[0] if site_keys else "")
            self.real_site_var.set(default or "")
        else:
            self.real_site_menu.configure(state="disabled")
            self.real_site_var.set(mode)

        self._update_prefix_label()

    def _update_prefix_label(self) -> None:
        site = self.app.cfg.get("sites", {}).get(self.real_site_var.get())
        self.prefix_label.configure(text=site["ip_prefix"] if site else "")

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

        mode = self.mode_var.get()
        if mode == MULTI:
            real_site = self.real_site_var.get()
            if not real_site:
                self.error_label.configure(text="No sites configured yet - see the Setup tab.")
                return
            raw_args = ["multi", real_site, name, octet, port]
        else:
            raw_args = [mode, name, octet, port]

        args = SimpleNamespace(args=raw_args, https=self.https_var.get())
        cfg, creds = self.app.cfg, self.app.creds

        self.output.delete("1.0", "end")
        self.add_btn.configure(state="disabled", text="Adding...")

        def done(rc, error) -> None:
            self.add_btn.configure(state="normal", text="Add")
            if error is not None:
                self.output.insert("end", f"\nFAILED: {error}\n")

        run_captured(self.output, lambda: cmd_add(cfg, creds, args), on_done=done)
