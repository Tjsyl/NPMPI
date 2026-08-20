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
one NPM update rather than racing each other one call at a time).

Ticking "Edit IP/Port" turns on inline editing: double-clicking a PRIMARY
row's IP or Port cell (aliases share their host's backend, so they're not
independently editable) opens a small text entry right over that cell.
Enter/click-away stages the change (shown immediately in the cell, row
tagged "pending" until saved); Escape discards just that one edit.

There's one shared action button (not two separate ones) whose label and
behavior depend on which mode is active: with "Edit IP/Port" ticked it
reads "Confirm" and, like Delete, shows a confirmation listing every
staged old -> new IP:Port before pushing anything (via
npm.update_proxy_host_backend()); otherwise it reads "Delete" and behaves
exactly as before, gated by the "Confirm delete" checkbox + a tree
selection. All of the row-1 controls (site dropdown, search, Refresh)
plus the row-2 controls (status, the two checkboxes, the action button)
live in one FlowRow (see widgets.py) that wraps row 2 onto its own line
once the window's too narrow to fit everything on one row, instead of
the two groups overlapping."""

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
from npmpi.gui.widgets import FlowRow

ALL_SITES = "All sites"

_DARK = {"bg": "#242424", "fg": "#dce4ee", "heading_bg": "#333333"}
_LIGHT = {"bg": "#f5f5f5", "fg": "#1a1a1a", "heading_bg": "#dbdbdb"}

_DELETE_STYLE = {
    "fg_color": "transparent", "border_width": 2, "border_color": "#e05656",
    "text_color": "#e05656", "hover_color": "#3a2020",
}
_CONFIRM_STYLE = {
    "fg_color": "#3d7eff", "border_width": 0, "border_color": "#3d7eff",
    "text_color": "white", "hover_color": "#2f63cc",
}


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

    # ttk.Style().configure() alone doesn't reliably force an ALREADY-DRAWN
    # Treeview to repaint on Windows - a known ttk quirk where existing rows
    # keep whatever colors were cached at their last draw until something
    # forces a harder refresh (this is why detouring through "System" before
    # "Dark" used to "unstick" it - that extra click happened to trigger a
    # fuller repaint as a side effect). Toggling the active theme off and
    # back forces ttk to fully discard and rebuild its style/element cache,
    # which reliably repaints every existing row on every switch, not just
    # some of them.
    style.theme_use("default")
    style.theme_use("clam")


theme.add_appearance_listener(_style_treeview)


class ListTab:
    def __init__(self, parent, app) -> None:
        self.app = app
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)

        controls = ctk.CTkFrame(self.frame, fg_color="transparent")
        controls.pack(fill="x", pady=(0, 10))

        self.row1 = ctk.CTkFrame(controls, fg_color="transparent")
        self.row1.pack(fill="x")
        self.row2 = ctk.CTkFrame(controls, fg_color="transparent")
        self.row2.pack(fill="x", pady=(8, 0))

        # Every control's master is `controls` - which row (row1/row2) each
        # one actually lands in is decided live by the FlowRow built below,
        # not fixed here (same pattern as add_tab.py/gen_tab.py).
        self.site_var = tk.StringVar(value=ALL_SITES)
        self.site_menu = ctk.CTkOptionMenu(controls, variable=self.site_var, values=[ALL_SITES])

        # No textvariable - always starts empty, needs the placeholder to work
        # (see add_tab.py's note on why textvariable + placeholder_text conflict).
        self.search_var = ctk.CTkEntry(controls, placeholder_text="Search hostname or IP...", width=280)
        self.search_var.bind("<Return>", lambda _e: self.refresh())

        self.refresh_btn = ctk.CTkButton(controls, text="Refresh", width=90, command=self.refresh)

        self.status = ctk.CTkLabel(controls, text="", text_color=("gray30", "gray70"))

        # Mode toggle: unticking it discards any staged, unsaved edits.
        self.edit_mode_var = tk.BooleanVar(value=False)
        self.edit_check = ctk.CTkCheckBox(
            controls, text="Edit IP/Port", width=20, variable=self.edit_mode_var,
            command=self._on_toggle_edit_mode,
        )

        # Gate for the Delete side of the shared button below - only relevant
        # when Edit IP/Port is unticked.
        self.delete_confirm_var = tk.BooleanVar(value=False)
        self.delete_check = ctk.CTkCheckBox(
            controls, text="Confirm delete", width=20, variable=self.delete_confirm_var,
            command=self._update_action_button,
        )

        # One shared button instead of two - its text/color/enabled state and
        # what it actually does are entirely driven by edit_mode_var, kept in
        # sync by _update_action_button() (called from every place that could
        # change either mode's readiness: selection, checkboxes, edits staged/
        # cleared, refresh).
        self.action_btn = ctk.CTkButton(
            controls, text="Delete", width=100, state="disabled",
            command=self._on_action, **_DELETE_STYLE,
        )

        self.flow = FlowRow(
            container=controls, row1=self.row1, row2=self.row2,
            items=[
                (self.site_menu, 0),
                (self.search_var, 10),
                (self.refresh_btn, 8),
                (self.status, 16),
                (self.edit_check, 16),
                (self.delete_check, 12),
                (self.action_btn, 12),
            ],
            wrap_index=3,
        )

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
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        # Amber, not tied to the Light/Dark palette - reads fine against
        # either background, so it doesn't need re-applying in
        # _style_treeview() the way the base colors do.
        self.tree.tag_configure("pending", foreground="#e0a020")

        # item id -> (site_key, host dict, domain name this row represents, is_primary)
        self.item_meta: dict[str, tuple[str, dict, str, bool]] = {}
        # item id -> {"orig_ip", "orig_port", and "ip"/"port" if changed} -
        # staged edits not yet pushed to NPM. Only primary rows appear here.
        self.pending_edits: dict[str, dict] = {}
        # (Entry widget, row_id, field) for whichever cell editor is
        # currently open, or None - at most one at a time.
        self._active_editor: tuple[tk.Entry, str, str] | None = None

        # theme.add_appearance_listener(_style_treeview) above gives an
        # instant restyle for direct Light/Dark clicks, which resolve
        # synchronously. "System" mode does NOT resolve synchronously in
        # customtkinter - clicking it only flags "check periodically", and
        # the actual OS-theme detection happens ~30ms later via CTk's own
        # internal polling loop (confirmed by reading
        # AppearanceModeTracker.set_appearance_mode()'s source: the
        # "system" branch only sets a flag, it never calls
        # detect_appearance_mode() itself). CTk's own widgets are wired
        # into that same internal loop and pick up the correction
        # automatically; our ttk.Treeview isn't a CTk widget, so it never
        # gets that delayed correction - it would call our listener once,
        # synchronously, with whatever mode was still stale at that exact
        # moment, and then never hear from System's actual resolution.
        # This lightweight poll of the same public ctk.get_appearance_mode()
        # this tab already relies on is how the tree stays in sync with
        # System mode's delayed resolution too, not just direct clicks.
        self._last_appearance_mode = ctk.get_appearance_mode()
        self._poll_appearance_mode()

        self.on_config_reloaded()

    def _poll_appearance_mode(self) -> None:
        mode = ctk.get_appearance_mode()
        if mode != self._last_appearance_mode:
            self._last_appearance_mode = mode
            _style_treeview()
        self.frame.after(200, self._poll_appearance_mode)

    def _on_tree_select(self, _evt=None) -> None:
        # A new row selection invalidates any prior confirm-checkbox state -
        # force re-confirming rather than letting a stale checked box let a
        # newly-selected row get deleted without a fresh, deliberate check.
        self.delete_confirm_var.set(False)
        self._update_action_button()

    def _update_action_button(self) -> None:
        """Keeps the one shared button's label/color/enabled-state in sync
        with whichever mode is active - called after anything that could
        change either mode's readiness (selection, either checkbox, an edit
        staged/discarded, or a refresh)."""
        if self.edit_mode_var.get():
            self.action_btn.configure(text="Confirm", **_CONFIRM_STYLE)
            state = "normal" if self.pending_edits else "disabled"
        else:
            self.action_btn.configure(text="Delete", **_DELETE_STYLE)
            sel = self.tree.selection()
            ok = bool(sel) and all(i in self.item_meta for i in sel) and self.delete_confirm_var.get()
            state = "normal" if ok else "disabled"
        self.action_btn.configure(state=state)

    def _on_action(self) -> None:
        if self.edit_mode_var.get():
            self._on_save_edits()
        else:
            self._on_delete()

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
        self._cancel_active_editor()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.item_meta = {}
        self.pending_edits = {}
        self.delete_confirm_var.set(False)
        self._update_action_button()

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

        self.action_btn.configure(state="disabled", text="Deleting...")

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

    def _on_toggle_edit_mode(self) -> None:
        self._cancel_active_editor()
        if not self.edit_mode_var.get():
            self._discard_pending_edits()
        self._update_action_button()

    def _discard_pending_edits(self) -> None:
        for row_id, edit in self.pending_edits.items():
            if not self.tree.exists(row_id):
                continue
            self.tree.set(row_id, "ip", edit["orig_ip"])
            self.tree.set(row_id, "port", edit["orig_port"])
            tags = tuple(t for t in self.tree.item(row_id, "tags") if t != "pending")
            self.tree.item(row_id, tags=tags)
        self.pending_edits = {}

    def _on_tree_double_click(self, event) -> str | None:
        if not self.edit_mode_var.get():
            return None
        if self.tree.identify_region(event.x, event.y) != "cell":
            return None
        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if row_id not in self.item_meta:
            return None
        _site_key, _host, _domain, is_primary = self.item_meta[row_id]
        if not is_primary:
            return None  # aliases share their host's backend - not independently editable
        field = {"#2": "ip", "#3": "port"}.get(col_id)
        if not field:
            return None
        self._open_cell_editor(row_id, col_id, field)
        return "break"  # suppress the default double-click expand/collapse

    def _open_cell_editor(self, row_id: str, col_id: str, field: str) -> None:
        self._cancel_active_editor()
        bbox = self.tree.bbox(row_id, col_id)
        if not bbox:
            return
        x, y, width, height = bbox
        entry = tk.Entry(self.tree)
        entry.insert(0, self.tree.set(row_id, field))
        entry.select_range(0, "end")
        entry.place(x=x, y=y, width=width, height=height)
        entry.focus_set()
        entry.bind("<Return>", lambda _e: self._commit_active_editor())
        entry.bind("<Escape>", lambda _e: self._cancel_active_editor())
        entry.bind("<FocusOut>", lambda _e: self._commit_active_editor())
        self._active_editor = (entry, row_id, field)

    def _commit_active_editor(self) -> None:
        if self._active_editor is None:
            return
        entry, row_id, field = self._active_editor
        self._active_editor = None
        value = entry.get().strip()
        entry.destroy()
        self._commit_cell_edit(row_id, field, value)

    def _cancel_active_editor(self) -> None:
        if self._active_editor is None:
            return
        entry, _row_id, _field = self._active_editor
        self._active_editor = None
        entry.destroy()

    def _commit_cell_edit(self, row_id: str, field: str, new_value: str) -> None:
        if row_id not in self.item_meta or not self.tree.exists(row_id):
            return
        _site_key, host, _domain, is_primary = self.item_meta[row_id]
        if not is_primary:
            return
        if new_value == self.tree.set(row_id, field):
            return  # unchanged (or user just re-typed the same value) - nothing to stage

        if field == "port":
            if not new_value.isdigit() or not (1 <= int(new_value) <= 65535):
                messagebox.showerror("Invalid port", f"'{new_value}' isn't a valid port (1-65535).")
                return
        elif field == "ip" and not new_value:
            messagebox.showerror("Invalid IP", "IP/hostname can't be empty.")
            return

        edit = self.pending_edits.setdefault(row_id, {
            "orig_ip": str(host.get("forward_host", "")),
            "orig_port": str(host.get("forward_port", "")),
        })
        edit[field] = new_value
        self.tree.set(row_id, field, new_value)

        still_changed = (
            edit.get("ip", edit["orig_ip"]) != edit["orig_ip"]
            or edit.get("port", edit["orig_port"]) != edit["orig_port"]
        )
        if still_changed:
            self.tree.item(row_id, tags=("pending",))
        else:
            # Edited back to the original value(s) - nothing left to save
            # for this row, drop it rather than leave a no-op staged edit.
            del self.pending_edits[row_id]
            tags = tuple(t for t in self.tree.item(row_id, "tags") if t != "pending")
            self.tree.item(row_id, tags=tags)

        self._update_action_button()

    def _on_save_edits(self) -> None:
        if not self.pending_edits:
            return
        lines = []
        for row_id, edit in self.pending_edits.items():
            _site_key, host, _domain, _is_primary = self.item_meta[row_id]
            new_ip = edit.get("ip", edit["orig_ip"])
            new_port = edit.get("port", edit["orig_port"])
            names = ", ".join(sorted(host.get("domain_names", []), key=str.lower))
            lines.append(f"{names}: {edit['orig_ip']}:{edit['orig_port']} -> {new_ip}:{new_port}")
        msg = f"Apply the following {len(lines)} change(s) to NPM?\n\n" + "\n".join(lines)
        if not messagebox.askyesno("Confirm changes", msg):
            return

        self.action_btn.configure(state="disabled", text="Saving...")
        edits_to_apply = dict(self.pending_edits)

        def worker() -> None:
            failures = []
            for row_id, edit in edits_to_apply.items():
                site_key, host, _domain, _is_primary = self.item_meta[row_id]
                new_ip = edit.get("ip", edit["orig_ip"])
                new_port = edit.get("port", edit["orig_port"])
                names = ", ".join(host.get("domain_names", []))
                try:
                    npm_cfg = self.app.cfg["sites"][site_key]["npm"]
                    pw = get_npm_password(self.app.creds, site_key)
                    token = npm_api.login(npm_cfg["url"], npm_cfg["email"], pw)
                    npm_api.update_proxy_host_backend(npm_cfg["url"], token, host, new_ip, new_port)
                except Exception as e:  # noqa: BLE001 - reported, not swallowed
                    failures.append(f"{names}: {e}")
            self.frame.after(0, lambda: self._save_edits_done(failures))

        threading.Thread(target=worker, daemon=True).start()

    def _save_edits_done(self, failures: list[str]) -> None:
        if failures:
            messagebox.showerror("Save changes", "Completed with failures:\n\n" + "\n".join(failures))
        self.refresh()
