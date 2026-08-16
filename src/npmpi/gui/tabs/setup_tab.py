"""
Setup tab: `npmpi setup`/`npmpi setup --fix`/`--npm`/`--pihole`/`--gen` as
forms. Built directly against config.write_config/creds.save_creds rather
than reusing setup.py's cmd_setup (which is a long blocking input()/
getpass() wizard) - same data model (see commands/setup.py's _setup_site),
just collected through fields instead of sequential prompts. Gen's own
config is edited from the Gen tab, not duplicated here.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from npmpi.config import DEFAULT_CONFIG_PATH, config_exists, write_config
from npmpi.creds import DEFAULT_CREDS_PATH, creds_exist


class _PiholeRows:
    """A small dynamic list of (name, url, password) entry rows, used by
    the 'add a new site' form - CLI asks 'how many piholes' up front, the
    GUI just lets you add/remove rows instead."""

    def __init__(self, parent) -> None:
        self.container = ctk.CTkFrame(parent, fg_color="transparent")
        self.container.pack(fill="x", pady=(4, 0))
        self.rows: list[dict] = []
        self.add_row()

    def add_row(self) -> None:
        row_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        row_frame.pack(fill="x", pady=2)
        n = len(self.rows) + 1
        name_var = tk.StringVar(value=f"pihole{n}")
        url_var = tk.StringVar()
        pw_var = tk.StringVar()
        ctk.CTkEntry(row_frame, textvariable=name_var, width=100, placeholder_text="name").pack(side="left", padx=(0, 6))
        ctk.CTkEntry(row_frame, textvariable=url_var, width=220, placeholder_text="URL, e.g. https://10.0.1.2:8489").pack(side="left", padx=6)
        ctk.CTkEntry(row_frame, textvariable=pw_var, width=160, placeholder_text="password", show="*").pack(side="left", padx=6)
        self.rows.append({"frame": row_frame, "name": name_var, "url": url_var, "pw": pw_var})

    def remove_last(self) -> None:
        if len(self.rows) > 1:
            self.rows.pop()["frame"].destroy()

    def values(self) -> list[dict]:
        return [{"name": r["name"].get().strip(), "url": r["url"].get().strip(), "pw": r["pw"].get()} for r in self.rows]


class SetupTab:
    def __init__(self, parent, app) -> None:
        self.app = app
        # Packed before the scrollable frame (and always kept packed) so it
        # sits in a fixed top bar - packing it after a fill+expand scroll
        # frame would starve it of layout space.
        self.status_label = ctk.CTkLabel(parent, text="", text_color="#4caf50")
        self.status_label.pack(fill="x", pady=(0, 8))
        self.scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)
        self._build()

    def on_config_reloaded(self) -> None:
        self._build()

    def _status(self, text: str, ok: bool = True) -> None:
        self.status_label.configure(text=text, text_color="#4caf50" if ok else "#e05656")

    def _build(self) -> None:
        for w in self.scroll.winfo_children():
            w.destroy()

        cfg_note = "found" if config_exists() else "not created yet"
        creds_note = "found" if creds_exist() else "not created yet"
        paths = ctk.CTkFrame(self.scroll, fg_color="transparent")
        paths.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(paths, text=f"Config: {DEFAULT_CONFIG_PATH} ({cfg_note})", anchor="w").pack(fill="x")
        ctk.CTkLabel(paths, text=f"Credentials: {DEFAULT_CREDS_PATH} ({creds_note})", anchor="w").pack(fill="x")

        for site_key, site in self.app.cfg.get("sites", {}).items():
            self._build_site_card(site_key, site)

        self._build_add_site_card()

    def _build_site_card(self, site_key: str, site: dict) -> None:
        card = ctk.CTkFrame(self.scroll)
        card.pack(fill="x", pady=(0, 12), padx=2)
        ctk.CTkLabel(card, text=f"Site '{site_key}' - {site['domain']}", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=12, pady=(10, 4))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        url_var = tk.StringVar(value=site["npm"]["url"])
        email_var = tk.StringVar(value=site["npm"]["email"])
        pw_var = tk.StringVar()
        ctk.CTkEntry(row, textvariable=url_var, width=220, placeholder_text="NPM URL").pack(side="left", padx=(0, 6))
        ctk.CTkEntry(row, textvariable=email_var, width=180, placeholder_text="NPM email").pack(side="left", padx=6)
        ctk.CTkEntry(row, textvariable=pw_var, width=160, placeholder_text="New password (blank = keep)", show="*").pack(side="left", padx=6)
        ctk.CTkButton(row, text="Save NPM", width=100,
                      command=lambda: self._save_npm(site_key, url_var.get(), email_var.get(), pw_var.get())).pack(side="left", padx=6)

        ctk.CTkLabel(card, text="Pi-hole(s):", text_color=("gray30", "gray70")).pack(anchor="w", padx=12, pady=(8, 0))
        for idx, ph in enumerate(site["piholes"]):
            prow = ctk.CTkFrame(card, fg_color="transparent")
            prow.pack(fill="x", padx=12, pady=2)
            name_var = tk.StringVar(value=ph["name"])
            phurl_var = tk.StringVar(value=ph["url"])
            phpw_var = tk.StringVar()
            ctk.CTkEntry(prow, textvariable=name_var, width=100).pack(side="left", padx=(0, 6))
            ctk.CTkEntry(prow, textvariable=phurl_var, width=220).pack(side="left", padx=6)
            ctk.CTkEntry(prow, textvariable=phpw_var, width=160, placeholder_text="New password (blank = keep)", show="*").pack(side="left", padx=6)
            ctk.CTkButton(prow, text="Save", width=70,
                          command=lambda i=idx, n=name_var, u=phurl_var, p=phpw_var: self._save_pihole(site_key, i, n.get(), u.get(), p.get())).pack(side="left", padx=6)

        add_row = ctk.CTkFrame(card, fg_color="transparent")
        add_row.pack(fill="x", padx=12, pady=(6, 10))
        new_name_var = tk.StringVar(value=f"pihole{len(site['piholes']) + 1}")
        new_url_var = tk.StringVar()
        new_pw_var = tk.StringVar()
        ctk.CTkEntry(add_row, textvariable=new_name_var, width=100, placeholder_text="name").pack(side="left", padx=(0, 6))
        ctk.CTkEntry(add_row, textvariable=new_url_var, width=220, placeholder_text="URL, e.g. https://10.0.1.2:8489").pack(side="left", padx=6)
        ctk.CTkEntry(add_row, textvariable=new_pw_var, width=160, placeholder_text="password", show="*").pack(side="left", padx=6)
        ctk.CTkButton(add_row, text="+ Pi-hole", width=90,
                      command=lambda: self._add_pihole(site_key, new_name_var.get(), new_url_var.get(), new_pw_var.get())).pack(side="left", padx=6)
        if site["piholes"]:
            ctk.CTkButton(add_row, text="- Remove last", width=110, fg_color="transparent", border_width=1,
                          command=lambda: self._remove_last_pihole(site_key)).pack(side="left", padx=6)

    def _save_npm(self, site_key: str, url: str, email: str, new_pw: str) -> None:
        url, email = url.strip(), email.strip()
        if not url or not email:
            self._status("NPM URL and email are required.", ok=False)
            return
        self.app.cfg["sites"][site_key]["npm"]["url"] = url
        self.app.cfg["sites"][site_key]["npm"]["email"] = email
        if new_pw:
            self.app.creds.setdefault(site_key, {})["npm_password"] = new_pw
        write_config(self.app.cfg)
        self._save_creds()
        self._status(f"Saved site '{site_key}' NPM config.")
        self.app.reload()

    def _save_pihole(self, site_key: str, idx: int, name: str, url: str, new_pw: str) -> None:
        name, url = name.strip(), url.strip()
        if not name or not url:
            self._status("Pi-hole name and URL are required.", ok=False)
            return
        old = self.app.cfg["sites"][site_key]["piholes"][idx]
        pihole_creds = self.app.creds.setdefault(site_key, {}).setdefault("piholes", {})
        if name != old["name"]:
            old_pw = pihole_creds.pop(old["name"], None)
            if not new_pw:
                new_pw = old_pw or ""
        if new_pw:
            pihole_creds[name] = new_pw
        self.app.cfg["sites"][site_key]["piholes"][idx] = {"name": name, "url": url}
        write_config(self.app.cfg)
        self._save_creds()
        self._status(f"Saved Pi-hole '{name}' on site '{site_key}'.")
        self.app.reload()

    def _add_pihole(self, site_key: str, name: str, url: str, pw: str) -> None:
        name, url = name.strip(), url.strip()
        if not name or not url or not pw:
            self._status("New Pi-hole needs a name, URL, and password.", ok=False)
            return
        existing_names = {ph["name"] for ph in self.app.cfg["sites"][site_key]["piholes"]}
        if name in existing_names:
            self._status(f"Site '{site_key}' already has a Pi-hole named '{name}'.", ok=False)
            return
        self.app.cfg["sites"][site_key]["piholes"].append({"name": name, "url": url})
        self.app.creds.setdefault(site_key, {}).setdefault("piholes", {})[name] = pw
        write_config(self.app.cfg)
        self._save_creds()
        self._status(f"Added Pi-hole '{name}' to site '{site_key}'.")
        self.app.reload()

    def _remove_last_pihole(self, site_key: str) -> None:
        piholes = self.app.cfg["sites"][site_key]["piholes"]
        if not piholes:
            return
        removed = piholes[-1]
        if not messagebox.askyesno(
            "Remove Pi-hole", f"Remove '{removed['name']}' ({removed['url']}) from site '{site_key}'?",
        ):
            return
        piholes.pop()
        self.app.creds.get(site_key, {}).get("piholes", {}).pop(removed["name"], None)
        write_config(self.app.cfg)
        self._save_creds()
        self._status(f"Removed Pi-hole '{removed['name']}' from site '{site_key}'.")
        self.app.reload()

    def _build_add_site_card(self) -> None:
        card = ctk.CTkFrame(self.scroll)
        card.pack(fill="x", pady=(0, 12), padx=2)
        ctk.CTkLabel(card, text="Add a new site", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=12, pady=(10, 4))

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=4)
        key_var = tk.StringVar()
        domain_var = tk.StringVar()
        prefix_var = tk.StringVar()
        ctk.CTkEntry(grid, textvariable=key_var, width=100, placeholder_text="site key, e.g. h").grid(row=0, column=0, padx=(0, 6), pady=3)
        ctk.CTkEntry(grid, textvariable=domain_var, width=220, placeholder_text="domain, e.g. home.example.com").grid(row=0, column=1, padx=6, pady=3)
        ctk.CTkEntry(grid, textvariable=prefix_var, width=160, placeholder_text="IP prefix, e.g. 10.0.1.").grid(row=0, column=2, padx=6, pady=3)

        npm_url_var = tk.StringVar()
        npm_email_var = tk.StringVar()
        npm_pw_var = tk.StringVar()
        target_ip_var = tk.StringVar()
        ctk.CTkEntry(grid, textvariable=npm_url_var, width=220, placeholder_text="NPM URL").grid(row=1, column=0, padx=(0, 6), pady=3)
        ctk.CTkEntry(grid, textvariable=npm_email_var, width=160, placeholder_text="NPM email").grid(row=1, column=1, padx=6, pady=3)
        ctk.CTkEntry(grid, textvariable=npm_pw_var, width=160, placeholder_text="NPM password", show="*").grid(row=1, column=2, padx=6, pady=3)
        ctk.CTkEntry(grid, textvariable=target_ip_var, width=220, placeholder_text="Pi-hole target IP (usually the NPM IP)").grid(row=2, column=0, padx=(0, 6), pady=3, sticky="w")

        ctk.CTkLabel(card, text="Pi-hole(s):", text_color=("gray30", "gray70")).pack(anchor="w", padx=12, pady=(8, 0))
        pihole_rows = _PiholeRows(card)
        prow_btns = ctk.CTkFrame(card, fg_color="transparent")
        prow_btns.pack(fill="x", padx=12, pady=(2, 0))
        ctk.CTkButton(prow_btns, text="+ Pi-hole", width=90, command=pihole_rows.add_row).pack(side="left")
        ctk.CTkButton(prow_btns, text="- Pi-hole", width=90, command=pihole_rows.remove_last).pack(side="left", padx=6)

        ctk.CTkButton(card, text="Add site", width=110, command=lambda: self._add_site(
            key_var.get(), domain_var.get(), prefix_var.get(), npm_url_var.get(),
            npm_email_var.get(), npm_pw_var.get(), target_ip_var.get(), pihole_rows,
        )).pack(anchor="w", padx=12, pady=(10, 12))

    def _add_site(self, key, domain, ip_prefix, npm_url, npm_email, npm_pw, target_ip, pihole_rows) -> None:
        key, domain, ip_prefix = key.strip(), domain.strip(), ip_prefix.strip()
        npm_url, npm_email = npm_url.strip(), npm_email.strip()
        target_ip = target_ip.strip()

        if not all([key, domain, ip_prefix, npm_url, npm_email, npm_pw, target_ip]):
            self._status("All site/NPM fields are required to add a new site.", ok=False)
            return
        if key in self.app.cfg.get("sites", {}):
            self._status(f"Site '{key}' already exists.", ok=False)
            return

        piholes, pihole_creds = [], {}
        for row in pihole_rows.values():
            if not row["name"] or not row["url"] or not row["pw"]:
                self._status("Every Pi-hole row needs a name, URL, and password.", ok=False)
                return
            piholes.append({"name": row["name"], "url": row["url"]})
            pihole_creds[row["name"]] = row["pw"]

        self.app.cfg.setdefault("sites", {})[key] = {
            "domain": domain, "ip_prefix": ip_prefix,
            "npm": {"url": npm_url, "email": npm_email},
            "npm_target_ip": target_ip, "piholes": piholes,
        }
        self.app.cfg.setdefault("gen", {"enabled": False})
        self.app.creds[key] = {"npm_password": npm_pw, "piholes": pihole_creds}

        write_config(self.app.cfg)
        self._save_creds()
        self._status(f"Added site '{key}'.")
        self.app.reload()

    def _save_creds(self) -> None:
        from npmpi.creds import save_creds
        save_creds(self.app.creds)
