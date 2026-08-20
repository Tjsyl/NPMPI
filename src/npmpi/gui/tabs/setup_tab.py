"""
Setup tab: `npmpi setup`/`npmpi setup --fix`/`--npm`/`--pihole`/`--gen` as
forms. Built directly against config.write_config/creds.save_creds rather
than reusing setup.py's cmd_setup (which is a long blocking input()/
getpass() wizard) - same data model (see commands/setup.py's _setup_site),
just collected through fields instead of sequential prompts. Gen's own
config is edited from the Generate tab, not duplicated here.

The NPM row, each existing Pi-hole row, and the "add a Pi-hole" row are
each their own FlowRow (see widgets.py, same mechanism Add/Generate use)
rather than a plain fixed-width pack() row - inside this tab's
CTkScrollableFrame, a too-narrow window doesn't shrink those fixed-width
entries/buttons, it just clips whatever doesn't fit past the visible
edge (no horizontal scrollbar), which made password placeholder text and
the "Remove last" button unreadable at anything less than full width.
_make_flow_rows() is the shared container/row1/row2 setup all three use.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from npmpi.config import DEFAULT_CONFIG_PATH, config_exists, write_config
from npmpi.creds import DEFAULT_CREDS_PATH, creds_exist
from npmpi.gui.widgets import FlowRow


def _make_flow_rows(parent, pady=4) -> tuple[ctk.CTkFrame, ctk.CTkFrame, ctk.CTkFrame]:
    """A container + its two FlowRow rows, packed and ready - widgets should
    be created with `container` as their master, then handed to a FlowRow
    built against (container, row1, row2)."""
    container = ctk.CTkFrame(parent, fg_color="transparent")
    container.pack(fill="x", padx=12, pady=pady)
    row1 = ctk.CTkFrame(container, fg_color="transparent")
    row1.pack(fill="x")
    row2 = ctk.CTkFrame(container, fg_color="transparent")
    row2.pack(fill="x", pady=(6, 0))
    return container, row1, row2


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
        row_frame, row1, row2 = _make_flow_rows(self.container, pady=2)
        n = len(self.rows) + 1
        # No textvariable on any of these - a bound StringVar silently disables
        # CustomTkinter's placeholder_text (see add_tab.py's note). name_var keeps
        # a real starting value so it's inserted directly instead.
        name_var = ctk.CTkEntry(row_frame, width=100, placeholder_text="name")
        name_var.insert(0, f"pihole{n}")
        url_var = ctk.CTkEntry(row_frame, width=220, placeholder_text="URL, e.g. https://10.0.1.2:8489")
        pw_var = ctk.CTkEntry(row_frame, width=160, placeholder_text="password", show="*")
        FlowRow(container=row_frame, row1=row1, row2=row2, items=[
            (name_var, 0), (url_var, 6), (pw_var, 6),
        ], wrap_index=2)
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

        container, row1, row2 = _make_flow_rows(card)
        url_var = tk.StringVar(value=site["npm"]["url"])
        email_var = tk.StringVar(value=site["npm"]["email"])
        url_entry = ctk.CTkEntry(container, textvariable=url_var, width=220, placeholder_text="NPM URL")
        email_entry = ctk.CTkEntry(container, textvariable=email_var, width=180, placeholder_text="NPM email")
        # No textvariable here - always starts empty, and a bound StringVar would
        # silently disable the placeholder (see add_tab.py's note).
        pw_var = ctk.CTkEntry(container, width=240, placeholder_text="New password (blank = keep)", show="*")
        save_btn = ctk.CTkButton(container, text="Save NPM", width=100,
                      command=lambda: self._save_npm(site_key, url_var.get(), email_var.get(), pw_var.get()))
        FlowRow(container=container, row1=row1, row2=row2, items=[
            (url_entry, 0), (email_entry, 6), (pw_var, 6), (save_btn, 6),
        ], wrap_index=2)

        ctk.CTkLabel(card, text="Pi-hole(s):", text_color=("gray30", "gray70")).pack(anchor="w", padx=12, pady=(8, 0))
        for idx, ph in enumerate(site["piholes"]):
            pcontainer, prow1, prow2 = _make_flow_rows(card, pady=2)
            name_var = tk.StringVar(value=ph["name"])
            phurl_var = tk.StringVar(value=ph["url"])
            name_entry = ctk.CTkEntry(pcontainer, textvariable=name_var, width=100)
            url_entry = ctk.CTkEntry(pcontainer, textvariable=phurl_var, width=220)
            # No textvariable - always starts empty, needs the placeholder to work.
            phpw_var = ctk.CTkEntry(pcontainer, width=240, placeholder_text="New password (blank = keep)", show="*")
            psave_btn = ctk.CTkButton(pcontainer, text="Save", width=70,
                          command=lambda i=idx, n=name_var, u=phurl_var, p=phpw_var: self._save_pihole(site_key, i, n.get(), u.get(), p.get()))
            FlowRow(container=pcontainer, row1=prow1, row2=prow2, items=[
                (name_entry, 0), (url_entry, 6), (phpw_var, 6), (psave_btn, 6),
            ], wrap_index=2)

        acontainer, arow1, arow2 = _make_flow_rows(card, pady=(6, 10))
        # No textvariable on any of these - see add_tab.py's note. new_name_var
        # keeps a real starting value, inserted directly instead.
        new_name_var = ctk.CTkEntry(acontainer, width=100, placeholder_text="name")
        new_name_var.insert(0, f"pihole{len(site['piholes']) + 1}")
        new_url_var = ctk.CTkEntry(acontainer, width=220, placeholder_text="URL, e.g. https://10.0.1.2:8489")
        new_pw_var = ctk.CTkEntry(acontainer, width=160, placeholder_text="password", show="*")
        add_btn = ctk.CTkButton(acontainer, text="+ Pi-hole", width=90,
                      command=lambda: self._add_pihole(site_key, new_name_var.get(), new_url_var.get(), new_pw_var.get()))
        add_items = [(new_name_var, 0), (new_url_var, 6), (new_pw_var, 6), (add_btn, 6)]
        if site["piholes"]:
            remove_btn = ctk.CTkButton(acontainer, text="- Remove last", width=110, fg_color="transparent", border_width=1,
                          command=lambda: self._remove_last_pihole(site_key))
            add_items.append((remove_btn, 6))
        FlowRow(container=acontainer, row1=arow1, row2=arow2, items=add_items, wrap_index=2)

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
        # skip=self: refresh every OTHER tab, but don't rebuild this page's
        # own fields - that would wipe any not-yet-saved edits typed into
        # other fields on this same Setup screen (e.g. a pending Pi-hole
        # rename below). See app.py's reload() docstring.
        self.app.reload(skip=self)

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
        # skip=self - see _save_npm's comment above.
        self.app.reload(skip=self)

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
        # No textvariable on any of these seven - all start empty and need the
        # placeholder to actually show (see add_tab.py's note).
        key_var = ctk.CTkEntry(grid, width=100, placeholder_text="site key, e.g. home")
        domain_var = ctk.CTkEntry(grid, width=220, placeholder_text="domain, e.g. home.example.com")
        prefix_var = ctk.CTkEntry(grid, width=160, placeholder_text="IP prefix, e.g. 10.0.1.")
        key_var.grid(row=0, column=0, padx=(0, 6), pady=3)
        domain_var.grid(row=0, column=1, padx=6, pady=3)
        prefix_var.grid(row=0, column=2, padx=6, pady=3)

        npm_url_var = ctk.CTkEntry(grid, width=220, placeholder_text="NPM URL")
        npm_email_var = ctk.CTkEntry(grid, width=160, placeholder_text="NPM email")
        npm_pw_var = ctk.CTkEntry(grid, width=160, placeholder_text="NPM password", show="*")
        target_ip_var = ctk.CTkEntry(grid, width=220, placeholder_text="Pi-hole target IP (usually the NPM IP)")
        npm_url_var.grid(row=1, column=0, padx=(0, 6), pady=3)
        npm_email_var.grid(row=1, column=1, padx=6, pady=3)
        npm_pw_var.grid(row=1, column=2, padx=6, pady=3)
        target_ip_var.grid(row=2, column=0, padx=(0, 6), pady=3, sticky="w")

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
        if key == "multi":
            self._status("'multi' is reserved (it's the `npmpi add multi <SITE> ...` keyword) - pick a different site key.", ok=False)
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
