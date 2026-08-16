"""List/Find tab: a live, searchable, site-filterable table of every NPM
proxy host, grouped by backend - the GUI equivalent of `npmpi list`/`npmpi
find` combined into one view (a dropdown picks the site instead of typing
a site letter; typing filters like `find`'s TERM does)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from npmpi import npm as npm_api
from npmpi.commands.list import group_by_backend, matches
from npmpi.creds import get_npm_password

ALL_SITES = "All sites"


def _style_treeview() -> None:
    """ttk widgets don't follow CTk's appearance-mode toggle automatically -
    this applies one reasonable dark-friendly style at tab-build time rather
    than trying to live-follow every mode switch."""
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "npmpi.Treeview",
        background="#242424", fieldbackground="#242424", foreground="#dce4ee",
        bordercolor="#343638", borderwidth=0, rowheight=26,
        font=("Segoe UI", 10, "bold"),
    )
    style.configure(
        "npmpi.Treeview.Heading",
        background="#333333", foreground="#dce4ee", borderwidth=0,
        font=("Segoe UI", 10, "bold"),
    )
    style.map("npmpi.Treeview", background=[("selected", "#1f6aa5")])


class ListTab:
    def __init__(self, parent, app) -> None:
        self.app = app
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)

        controls = ctk.CTkFrame(self.frame, fg_color="transparent")
        controls.pack(fill="x", pady=(0, 10))

        self.site_var = tk.StringVar(value=ALL_SITES)
        self.site_menu = ctk.CTkOptionMenu(controls, variable=self.site_var, values=[ALL_SITES])
        self.site_menu.pack(side="left")

        # No textvariable - always starts empty, needs the placeholder to work
        # (see add_tab.py's note on why textvariable + placeholder_text conflict).
        self.search_var = ctk.CTkEntry(controls, placeholder_text="Search hostname or IP...", width=280)
        self.search_var.pack(side="left", padx=10)
        self.search_var.bind("<Return>", lambda _e: self.refresh())

        ctk.CTkButton(controls, text="Refresh", width=90, command=self.refresh).pack(side="left")

        self.status = ctk.CTkLabel(controls, text="", text_color=("gray30", "gray70"))
        self.status.pack(side="right")

        _style_treeview()
        tree_frame = ctk.CTkFrame(self.frame)
        tree_frame.pack(fill="both", expand=True)
        columns = ("scheme", "ip", "port")
        self.tree = ttk.Treeview(tree_frame, columns=columns, style="npmpi.Treeview")
        self.tree.heading("#0", text="Host")
        self.tree.heading("scheme", text="HTTP/HTTPS")
        self.tree.heading("ip", text="IP")
        self.tree.heading("port", text="Port")
        self.tree.column("#0", width=320)
        self.tree.column("scheme", width=100, anchor="center")
        self.tree.column("ip", width=140, anchor="center")
        self.tree.column("port", width=80, anchor="center")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.on_config_reloaded()

    def on_config_reloaded(self) -> None:
        site_keys = list(self.app.cfg.get("sites", {}).keys())
        values = [ALL_SITES] + site_keys
        self.site_menu.configure(values=values)
        if self.site_var.get() not in values:
            self.site_var.set(ALL_SITES)
        self.refresh()

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        site_keys = list(self.app.cfg.get("sites", {}).keys())
        if not site_keys:
            self.status.configure(text="No sites configured - see the Setup tab")
            return

        selected = self.site_var.get()
        sites_to_check = site_keys if selected == ALL_SITES else [selected]
        query = self.search_var.get().strip() or None

        self.status.configure(text="Loading...")
        q: queue.Queue = queue.Queue()

        def worker() -> None:
            for site_key in sites_to_check:
                site_cfg = self.app.cfg["sites"][site_key]
                npm_cfg = site_cfg["npm"]
                try:
                    pw = get_npm_password(self.app.creds, site_key)
                    token = npm_api.login(npm_cfg["url"], npm_cfg["email"], pw)
                    hosts = npm_api.get_proxy_hosts(npm_cfg["url"], token)
                    q.put(("ok", site_key, hosts))
                except Exception as e:  # noqa: BLE001 - reported in the UI, not swallowed
                    q.put(("error", site_key, str(e)))
            q.put(("done", None, None))

        threading.Thread(target=worker, daemon=True).start()

        shown = 0
        unreachable: list[str] = []

        def poll() -> None:
            nonlocal shown
            try:
                while True:
                    kind, site_key, payload = q.get_nowait()
                    if kind == "done":
                        suffix = f" - unreachable: {', '.join(unreachable)}" if unreachable else ""
                        self.status.configure(text=f"{shown} backend(s) shown{suffix}")
                        return
                    if kind == "error":
                        unreachable.append(site_key)
                        continue
                    groups = group_by_backend(payload)
                    groups.sort(key=lambda g: (g[0][1], g[0][2]))
                    groups = [g for g in groups if matches(query, g[0][1], g[1])]
                    for (scheme, ip, port), domains in groups:
                        prefix = f"[{site_key}] " if selected == ALL_SITES else ""
                        domains_sorted = sorted(domains, key=str.lower)
                        parent = self.tree.insert(
                            "", "end", text=f"{prefix}{domains_sorted[0]}",
                            values=(scheme.upper(), ip, port),
                        )
                        for alias in domains_sorted[1:]:
                            self.tree.insert(parent, "end", text=alias, values=("", "", ""))
                        self.tree.item(parent, open=True)
                        shown += 1
            except queue.Empty:
                pass
            self.frame.after(50, poll)

        poll()
