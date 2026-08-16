"""
Migrate tab: `npmpi migrate [SITE]` as a step-by-step wizard. Rebuilt
directly against npm_api/pihole_api rather than reusing cmd_migrate, which
is written around blocking input()/getpass() prompts that have nowhere to
go in a GUI. Mirrors the same flow: back up the source NPM first,
optionally back up Pi-hole too, preview the destination import, and only
then create anything - nothing is written to a destination until the
final step is explicitly confirmed.

Path resolution (_resolve_backup_path) and the field-stripping set
(FIELDS_TO_STRIP) are imported straight from commands/migrate.py so this
can never drift from the CLI's own backup-path behavior.
"""

from __future__ import annotations

import datetime
import json
import tkinter as tk

import customtkinter as ctk

from npmpi import npm as npm_api
from npmpi import pihole as pihole_api
from npmpi.commands.migrate import FIELDS_TO_STRIP, _resolve_backup_path
from npmpi.creds import get_npm_password, get_pihole_password
from npmpi.gui.runner import run_captured
from npmpi.gui.widgets import DynamicWrapLabel


class MigrateTab:
    def __init__(self, parent, app) -> None:
        self.app = app
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)

        self.state: dict = {}
        self.step = 0

        self.content = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.content.pack(fill="x")

        self.output = ctk.CTkTextbox(self.frame, font=ctk.CTkFont(family="Consolas", size=12))
        self.output.pack(fill="both", expand=True, pady=(10, 0))

        self.on_config_reloaded()

    def on_config_reloaded(self) -> None:
        self.state = {}
        self.step = 0
        self._render()

    def _clear(self) -> None:
        for w in self.content.winfo_children():
            w.destroy()

    def _log(self, text: str) -> None:
        self.output.insert("end", text + "\n")
        self.output.see("end")

    def _back_button(self, target_step: int) -> None:
        ctk.CTkButton(self.content, text="Back", width=80, fg_color="transparent",
                      border_width=1, command=lambda: self._goto(target_step)).pack(anchor="w", pady=(10, 0))

    def _goto(self, step: int) -> None:
        self.step = step
        self._render()

    def _render(self) -> None:
        self._clear()
        site_keys = list(self.app.cfg.get("sites", {}).keys())
        if not site_keys:
            ctk.CTkLabel(self.content, text="No sites configured yet - see the Setup tab.").pack(anchor="w")
            return

        [self._step0, self._step1, self._step2, self._step3, self._step4][self.step](site_keys)

    # -- Step 0: pick site -------------------------------------------------
    def _step0(self, site_keys: list[str]) -> None:
        ctk.CTkLabel(self.content, text="Step 1 of 5 - choose the site to migrate", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        # DynamicWrapLabel instead of a fixed wraplength=N - a hardcoded wrap width
        # overflows past the window edge and gets clipped once the window is
        # narrower than that, instead of actually wrapping to fit.
        DynamicWrapLabel(
            self.content, self.content, text_color=("gray30", "gray70"),
            text="Backs up the source NPM's proxy hosts, optionally backs up that site's Pi-hole(s) "
                 "too, previews what would be recreated on a new NPM, and only creates anything there "
                 "once you confirm the preview.",
        ).pack(anchor="w", pady=(4, 10))

        row = ctk.CTkFrame(self.content, fg_color="transparent")
        row.pack(fill="x")
        self.site_var = tk.StringVar(value=self.state.get("site_key", site_keys[0]))
        ctk.CTkOptionMenu(row, variable=self.site_var, values=site_keys).pack(side="left")
        ctk.CTkButton(row, text="Continue", width=100, command=self._from_step0).pack(side="left", padx=8)

    def _from_step0(self) -> None:
        self.state["site_key"] = self.site_var.get()
        self._goto(1)

    # -- Step 1: back up the source NPM ------------------------------------
    def _step1(self, site_keys: list[str]) -> None:
        site_key = self.state["site_key"]
        ctk.CTkLabel(self.content, text=f"Step 2 of 5 - back up site '{site_key}'s NPM", font=ctk.CTkFont(weight="bold")).pack(anchor="w")

        row = ctk.CTkFrame(self.content, fg_color="transparent")
        row.pack(fill="x", pady=(6, 0))
        default_backup = f"npmpi_migrate_{site_key}_{datetime.date.today().isoformat()}.json"
        self.backup_path_var = tk.StringVar(value=self.state.get("backup_path_raw", default_backup))
        ctk.CTkEntry(row, textvariable=self.backup_path_var, width=420).pack(side="left")
        self.backup_btn = ctk.CTkButton(row, text="Run backup", width=110, command=self._run_backup)
        self.backup_btn.pack(side="left", padx=8)
        ctk.CTkLabel(self.content, text="Relative paths are saved under ~\\npmpi_backups.",
                     text_color=("gray30", "gray70")).pack(anchor="w", pady=(4, 0))

        if self.state.get("backup_done"):
            ctk.CTkButton(self.content, text="Continue", width=100, command=lambda: self._goto(2)).pack(anchor="w", pady=(10, 0))
        self._back_button(0)

    def _run_backup(self) -> None:
        site_key = self.state["site_key"]
        site = self.app.cfg["sites"][site_key]
        raw = self.backup_path_var.get().strip()
        self.state["backup_path_raw"] = raw
        backup_path = _resolve_backup_path(raw)
        creds = self.app.creds

        def work() -> int:
            pw = get_npm_password(creds, site_key)
            print(f"[npm] logging in to {site['npm']['url']} ...")
            token = npm_api.login(site["npm"]["url"], site["npm"]["email"], pw)
            hosts = npm_api.get_proxy_hosts(site["npm"]["url"], token)
            certs = npm_api.get_certificates(site["npm"]["url"], token)
            out = {"source_url": site["npm"]["url"], "proxy_hosts": hosts, "certificates": certs}
            backup_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
            print(f"[npm] exported {len(hosts)} proxy hosts and {len(certs)} certificates")
            print(f"[npm] saved to: {backup_path}")
            self.state["hosts"] = hosts
            self.state["backup_files"] = [str(backup_path)]
            return 0

        self.backup_btn.configure(state="disabled", text="Running...")

        def done(rc, error) -> None:
            self.backup_btn.configure(state="normal", text="Run backup")
            if error is not None:
                self._log(f"FAILED: {error}")
                return
            self.state["backup_done"] = True
            self._render()

        run_captured(self.output, work, on_done=done)

    # -- Step 2: optional Pi-hole backup ------------------------------------
    def _step2(self, site_keys: list[str]) -> None:
        site_key = self.state["site_key"]
        ctk.CTkLabel(self.content, text="Step 3 of 5 - optionally back up Pi-hole too", font=ctk.CTkFont(weight="bold")).pack(anchor="w")

        row = ctk.CTkFrame(self.content, fg_color="transparent")
        row.pack(fill="x", pady=(6, 0))
        self.pihole_choice_var = tk.StringVar(value=self.state.get("pihole_choice", "Skip"))
        ctk.CTkSegmentedButton(row, values=["Skip", "DNS records", "Full Teleporter"],
                                variable=self.pihole_choice_var).pack(side="left")

        if not self.state.get("pihole_backup_done"):
            ctk.CTkButton(self.content, text="Run", width=90, command=self._run_pihole_backup).pack(anchor="w", pady=(10, 0))
        else:
            ctk.CTkLabel(self.content, text="Pi-hole backup step complete.", text_color=("gray30", "gray70")).pack(anchor="w", pady=(6, 0))

        ctk.CTkButton(self.content, text="Continue", width=100, command=lambda: self._goto(3)).pack(anchor="w", pady=(10, 0))
        self._back_button(1)

    def _run_pihole_backup(self) -> None:
        site_key = self.state["site_key"]
        site = self.app.cfg["sites"][site_key]
        choice = self.pihole_choice_var.get()
        self.state["pihole_choice"] = choice
        creds = self.app.creds

        if choice == "Skip":
            self.state["pihole_backup_done"] = True
            self._render()
            return

        default_name = f"npmpi_migrate_{site_key}_pihole_{'teleporter' if choice == 'Full Teleporter' else 'dns'}_{datetime.date.today().isoformat()}"

        def work() -> int:
            written = []
            if choice == "Full Teleporter":
                for ph in site["piholes"]:
                    name = ph["name"]
                    path = _resolve_backup_path(f"{default_name}_{name}.zip")
                    try:
                        phpw = get_pihole_password(creds, site_key, name)
                        print(f"[{name}] logging in to {ph['url']} ...")
                        sid = pihole_api.login(ph["url"], phpw)
                        try:
                            archive = pihole_api.teleporter_export(ph["url"], sid)
                            path.write_bytes(archive)
                            print(f"[{name}] wrote Teleporter backup ({len(archive)} bytes)")
                            print(f"[{name}] saved to: {path}")
                            written.append(str(path))
                        finally:
                            pihole_api.logout(ph["url"], sid)
                    except Exception as e:  # noqa: BLE001
                        print(f"[{name}] FAILED to back up: {e}")
            else:
                path = _resolve_backup_path(f"{default_name}.json")
                dns_out = {}
                for ph in site["piholes"]:
                    name = ph["name"]
                    try:
                        phpw = get_pihole_password(creds, site_key, name)
                        print(f"[{name}] logging in to {ph['url']} ...")
                        sid = pihole_api.login(ph["url"], phpw)
                        try:
                            dns_out[name] = {"url": ph["url"], "hosts": pihole_api.get_hosts(ph["url"], sid)}
                            print(f"[{name}] backed up {len(dns_out[name]['hosts'])} DNS record(s)")
                        finally:
                            pihole_api.logout(ph["url"], sid)
                    except Exception as e:  # noqa: BLE001
                        print(f"[{name}] FAILED to back up: {e}")
                path.write_text(json.dumps(dns_out, indent=2), encoding="utf-8")
                print(f"Wrote Pi-hole DNS backup -> saved to: {path}")
                written.append(str(path))
            self.state.setdefault("backup_files", []).extend(written)
            return 0

        def done(rc, error) -> None:
            if error is not None:
                self._log(f"FAILED: {error}")
            self.state["pihole_backup_done"] = True
            self._render()

        run_captured(self.output, work, on_done=done)

    # -- Step 3: destination + preview --------------------------------------
    def _step3(self, site_keys: list[str]) -> None:
        site_key = self.state["site_key"]
        site = self.app.cfg["sites"][site_key]
        ctk.CTkLabel(self.content, text="Step 4 of 5 - destination NPM + preview", font=ctk.CTkFont(weight="bold")).pack(anchor="w")

        grid = ctk.CTkFrame(self.content, fg_color="transparent")
        grid.pack(fill="x", pady=(6, 0))
        # No textvariable on any of these four - see add_tab.py's note on why a
        # bound StringVar silently disables CustomTkinter's placeholder_text.
        # Pre-filled values go in via .insert() instead of textvariable(value=...).
        self.dest_url_var = ctk.CTkEntry(grid, width=260, placeholder_text="New NPM URL")
        self.dest_url_var.grid(row=0, column=0, padx=(0, 8), pady=4)
        if self.state.get("dest_url"):
            self.dest_url_var.insert(0, self.state["dest_url"])

        self.dest_email_var = ctk.CTkEntry(grid, width=200, placeholder_text="Email")
        self.dest_email_var.grid(row=0, column=1, padx=8, pady=4)
        self.dest_email_var.insert(0, self.state.get("dest_email", site["npm"]["email"]))

        self.dest_pw_var = ctk.CTkEntry(grid, width=180, placeholder_text="Password", show="*")
        self.dest_pw_var.grid(row=0, column=2, padx=8, pady=4)

        self.exclude_var = ctk.CTkEntry(grid, width=260, placeholder_text="Exclude domains (space-separated)")
        self.exclude_var.grid(row=1, column=0, columnspan=2, padx=(0, 8), pady=4, sticky="w")
        if self.state.get("exclude_raw"):
            self.exclude_var.insert(0, self.state["exclude_raw"])

        self.preview_btn = ctk.CTkButton(self.content, text="Preview", width=100, command=self._run_preview)
        self.preview_btn.pack(anchor="w", pady=(10, 0))

        if self.state.get("to_import") is not None:
            ctk.CTkButton(self.content, text="Continue to confirm", width=160, command=lambda: self._goto(4)).pack(anchor="w", pady=(10, 0))
        self._back_button(2)

    def _run_preview(self) -> None:
        dest_url = self.dest_url_var.get().strip()
        dest_email = self.dest_email_var.get().strip()
        dest_pw = self.dest_pw_var.get()
        exclude_raw = self.exclude_var.get().strip()
        if not dest_url or not dest_email or not dest_pw:
            self._log("Destination URL, email, and password are all required.")
            return

        self.state.update(dest_url=dest_url, dest_email=dest_email, exclude_raw=exclude_raw)
        exclude = set(exclude_raw.split()) if exclude_raw else set()
        hosts = self.state["hosts"]
        to_import = [h for h in hosts if not (exclude & set(h["domain_names"]))]

        def work() -> int:
            dest_token = npm_api.login(dest_url, dest_email, dest_pw)
            dest_certs = npm_api.get_certificates(dest_url, dest_token)

            def match_cert(domain_names: list[str]) -> int:
                for cert in dest_certs:
                    for cd in cert.get("domain_names", []):
                        for d in domain_names:
                            if cd == d or (cd.startswith("*.") and d.endswith(cd[1:])):
                                return cert["id"]
                return 0

            print(f"Preview - would create {len(to_import)} proxy host(s) on {dest_url}:")
            for h in to_import:
                clean = {k: v for k, v in h.items() if k not in FIELDS_TO_STRIP}
                cert_id = match_cert(h["domain_names"])
                cert_note = "with matched SSL cert" if cert_id else "NO SSL cert matched"
                target = f"{clean['forward_scheme']}://{clean['forward_host']}:{clean['forward_port']}"
                print(f"  {', '.join(h['domain_names'])} -> {target} ({cert_note})")

            self.state["to_import"] = to_import
            self.state["dest_pw"] = dest_pw
            return 0

        self.preview_btn.configure(state="disabled", text="Checking...")

        def done(rc, error) -> None:
            self.preview_btn.configure(state="normal", text="Preview")
            if error is not None:
                self._log(f"FAILED: {error}")
                return
            self._render()

        run_captured(self.output, work, on_done=done)

    # -- Step 4: confirm + create --------------------------------------------
    def _step4(self, site_keys: list[str]) -> None:
        to_import = self.state.get("to_import", [])
        dest_url = self.state["dest_url"]
        ctk.CTkLabel(self.content, text="Step 5 of 5 - confirm and create", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        DynamicWrapLabel(
            self.content, self.content,
            text=f"Create {len(to_import)} proxy host(s) on {dest_url}? Nothing has been written yet.",
        ).pack(anchor="w", pady=(4, 10))

        self.create_btn = ctk.CTkButton(self.content, text=f"Create {len(to_import)} host(s)", width=180, command=self._run_create)
        self.create_btn.pack(anchor="w")

        if self.state.get("migration_done"):
            ctk.CTkButton(self.content, text="Start over", width=110, command=self._reset).pack(anchor="w", pady=(10, 0))
        self._back_button(3)

    def _run_create(self) -> None:
        dest_url = self.state["dest_url"]
        dest_email = self.state["dest_email"]
        dest_pw = self.state["dest_pw"]
        to_import = self.state["to_import"]
        backup_files = self.state.get("backup_files", [])

        def work() -> int:
            dest_token = npm_api.login(dest_url, dest_email, dest_pw)
            dest_certs = npm_api.get_certificates(dest_url, dest_token)

            def match_cert(domain_names: list[str]) -> int:
                for cert in dest_certs:
                    for cd in cert.get("domain_names", []):
                        for d in domain_names:
                            if cd == d or (cd.startswith("*.") and d.endswith(cd[1:])):
                                return cert["id"]
                return 0

            created, failed = [], []
            for h in to_import:
                clean = {k: v for k, v in h.items() if k not in FIELDS_TO_STRIP}
                clean["certificate_id"] = match_cert(h["domain_names"])
                try:
                    npm_api.create_proxy_host(
                        dest_url, dest_token, clean["domain_names"], clean["forward_scheme"],
                        clean["forward_host"], clean["forward_port"], clean["certificate_id"],
                    )
                    created.append(", ".join(h["domain_names"]))
                    print(f"  created: {', '.join(h['domain_names'])}")
                except Exception as e:  # noqa: BLE001
                    failed.append(", ".join(h["domain_names"]))
                    print(f"  FAILED: {', '.join(h['domain_names'])} :: {e}")

            print(f"\nDone. {len(created)} created, {len(failed)} failed.")
            print("\nBackup file(s) from this run:")
            for p in backup_files:
                print(f"  {p}")
            return 1 if failed else 0

        self.create_btn.configure(state="disabled", text="Creating...")

        def done(rc, error) -> None:
            self.create_btn.configure(state="normal")
            if error is not None:
                self._log(f"FAILED: {error}")
                return
            self.state["migration_done"] = True
            self._render()

        run_captured(self.output, work, on_done=done)

    def _reset(self) -> None:
        self.state = {}
        self.step = 0
        self.output.delete("1.0", "end")
        self._render()
