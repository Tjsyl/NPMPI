"""List/Find tab: a live, searchable, site-filterable table of every NPM
proxy host - the GUI equivalent of `npmpi list`/`npmpi find` combined into
one view (a dropdown picks the site instead of typing a site letter;
typing filters like `find`'s TERM does), plus delete.

Each tree row is built directly from one real NPM proxy host record - NOT
via commands/list.py's group_by_backend(), which cosmetically merges
domain names across potentially different host records that happen to
share a backend. That merging is fine for read-only display but unsafe
here, since Delete needs to know exactly which real host['id'] a row
belongs to (see commands/delete.py's module docstring for the same
reasoning). Each row's real host dict + which domain name it represents is
tracked in self.item_meta, keyed by tree item id.

The tree's ttk selectmode is the default "extended", so ctrl/shift-click
multi-select works out of the box - Delete then covers every selected
row in one confirmation + one batch of API calls, via
commands/delete.py's confirm_message_for_selection()/delete_selection(),
which handle deduping (e.g. a primary and one of its own aliases both
selected) and grouping (multiple aliases off the same host batched into
one NPM update rather than racing each other one call at a time)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import customtkinter as ctk

from npmpi import npm as npm_api
from npmpi.commands.delete import _Entry, confirm_message_for_selection, delete_selection
from npmpi.creds import get_npm_password
from npmpi.gui import theme

ALL_SITES = "All sites"

_DARK = {"bg": "#242424", "fg": "#dce4ee", "heading_bg": "#333333"}
_LIGHT = {"bg": "#f5f5f5", "fg": "#1a1a1a", "heading_bg": "#dbdbdb"}


def _style_treeview() -> None:
    """ttk widgets don't follow CTk's appearance-mode toggle automatically,
    so this is re-run (via theme.add_appearance_listener, registered once
    below) every time the System/Light/Dark switcher is clicked, not just
    once at tab-build time - otherwise switching to Light mode leaves the
    tree stuck showing its dark-mode colors."""
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    colors = _DARK if ctk.get_appearance_mode() == "Dark" else _LIGHT
    style.configure(
        "npmpi.Treeview",
        background=colors["bg"], fieldbackground=colors["bg"], foreground=colors["fg"],
        bordercolor="#343638", borderwidth=0, rowheight=26,
        font=("Segoe UI", 10, "bold"),
    )
    style.configure(
        "npmpi.Treeview.Heading",
        background=colors["heading_bg"], foreground=colors["fg"], borderwidth=0,
        font=("Segoe UI", 10, "bold"),
    )
    style.map("npmpi.Treeview", background=[("selected", "#1f6aa5")])


theme.add_appearance_listener(_style_treeview)


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

        # Right side, opposite Refresh: a confirm checkbox + Delete button.
        # Packed side="right" in this order (delete_btn first) so delete_btn
        # lands at the outermost right edge, checkbox just to its left, and
        # status further left still - see pack(side="right") stacking order.
        self.delete_btn = ctk.CTkButton(
            controls, text="Delete", width=90, state="disabled",
            fg_color="transparent", border_width=2, border_color="#e05656",
            text_color="#e05656", hover_color="#3a2020", command=self._on_delete,
        )
        self.delete_btn.pack(side="right")

        self.delete_confirm_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            controls, text="", width=20, variable=self.delete_confirm_var,
            command=self._update_delete_state,
        ).pack(side="right", padx=(0, 8))

        self.status = ctk.CTkLabel(controls, text="", text_color=("gray30", "gray70"))
        self.status.pack(side="right", padx=(0, 12))

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

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # item id -> (site_key, host dict, domain name this row represents, is_primary)
        self.item_meta: dict[str, tuple[str, dict, str, bool]] = {}

        self.on_config_reloaded()

    def _on_tree_select(self, _evt=None) -> None:
        # A new row selection invalidates any prior confirm-checkbox state -
        # force re-confirming rather than letting a stale checked box let a
        # newly-selected row get deleted without a fresh, deliberate check.
        self.delete_confirm_var.set(False)
        self._update_delete_state()

    def _update_delete_state(self) -> None:
        sel = self.tree.selection()
        ok = bool(sel) and all(i in self.item_meta for i in sel) and self.delete_confirm_var.get()
        self.delete_btn.configure(state="normal" if ok else "disabled")

    def on_config_reloaded(self) -> None:
        site_keys = list(self.app.cfg.get("sites", {}).keys())
        values = [ALL_SITES] + site_keys
        self.site_menu.configure(values=values)
        if self.site_var.get() not in values:
            self.site_var.set(ALL_SITES)
        self.refresh()

    def _host_matches(self, query: str | None, host: dict) -> bool:
        if not query:
            return True
        q = query.lower()
        if q in (host.get("forward_host") or "").lower():
            return True
        return any(q in d.lower() for d in host.get("domain_names", []))

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.item_meta = {}
        self.delete_confirm_var.set(False)
        self.delete_btn.configure(state="disabled", text="Delete")

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
                    # One tree parent per real NPM host record (never merged
                    # across host ids, even if two hosts happen to share a
                    # backend) - see module docstring for why.
                    hosts = [h for h in payload if h.get("enabled", True)]
                    hosts = [h for h in hosts if self._host_matches(query, h)]
                    hosts.sort(key=lambda h: (h.get("forward_host") or "", h.get("forward_port") or 0))
                    for host in hosts:
                        domains_sorted = sorted(host.get("domain_names", []), key=str.lower)
                        if not domains_sorted:
                            continue
                        prefix = f"[{site_key}] " if selected == ALL_SITES else ""
                        scheme = host.get("forward_scheme", "http")
                        ip = host.get("forward_host", "")
                        port = host.get("forward_port", "")
                        parent = self.tree.insert(
                            "", "end", text=f"{prefix}{domains_sorted[0]}",
                            values=(scheme.upper(), ip, port),
                        )
                        self.item_meta[parent] = (site_key, host, domains_sorted[0], True)
                        for alias in domains_sorted[1:]:
                            child = self.tree.insert(parent, "end", text=alias, values=("", "", ""))
                            self.item_meta[child] = (site_key, host, alias, False)
                        self.tree.item(parent, open=True)
                        shown += 1
            except queue.Empty:
                pass
            self.frame.after(50, poll)

        poll()

    def _on_delete(self) -> None:
        sel = self.tree.selection()
        entries = [_Entry(*self.item_meta[i]) for i in sel if i in self.item_meta]
        if not entries:
            return

        msg = confirm_message_for_selection(self.app.cfg, entries)
        if not messagebox.askyesno("Confirm delete", msg):
            return

        self.delete_btn.configure(state="disabled", text="Deleting...")

        def worker() -> None:
            try:
                failures = delete_selection(self.app.cfg, self.app.creds, entries)
            except Exception as e:  # noqa: BLE001 - reported, not swallowed
                failures = [str(e)]
            self.frame.after(0, lambda: self._delete_done(failures))

        threading.Thread(target=worker, daemon=True).start()

    def _delete_done(self, failures: list[str]) -> None:
        if failures:
            messagebox.showerror("Delete", f"Completed with failures in: {', '.join(failures)}")
        self.refresh()
