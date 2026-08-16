"""Small shared GUI building blocks."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

ACCENT = "#3d7eff"
INACTIVE_TEXT = ("gray40", "gray55")
INACTIVE_BG = ("gray80", "gray24")
INACTIVE_HOVER = ("gray70", "gray32")


class ButtonBar:
    """A row of separate, individually-styled buttons - not one connected
    segmented control. Unselected buttons sit on a permanent flat grey
    square (not just on hover - INACTIVE_BG is always applied, INACTIVE_HOVER
    is a distinct shade only shown on hover for feedback); the selected one
    turns blue. Used for both the main tab bar and the theme (System/Light/
    Dark) switcher so the two look consistent with each other."""

    def __init__(
        self, parent, values: list[str], command: Callable[[str], None], initial: str | None = None,
    ) -> None:
        self.command = command
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.buttons: dict[str, ctk.CTkButton] = {}
        button_font = ctk.CTkFont(size=16)
        for value in values:
            width = max(80, len(value) * 10 + 28)
            btn = ctk.CTkButton(
                self.frame, text=value, width=width, height=36, corner_radius=8,
                font=button_font,
                fg_color=INACTIVE_BG, text_color=INACTIVE_TEXT,
                hover_color=INACTIVE_HOVER,
                command=lambda v=value: self._select(v),
            )
            btn.pack(side="left", padx=4)
            self.buttons[value] = btn
        self.selected = initial or (values[0] if values else None)
        self._restyle()

    def _select(self, value: str) -> None:
        self.selected = value
        self._restyle()
        self.command(value)

    def _restyle(self) -> None:
        for value, btn in self.buttons.items():
            if value == self.selected:
                btn.configure(fg_color=ACCENT, text_color="white", hover_color=ACCENT)
            else:
                btn.configure(fg_color=INACTIVE_BG, text_color=INACTIVE_TEXT, hover_color=INACTIVE_HOVER)

    def set(self, value: str) -> None:
        """Update selection programmatically (no command callback fired) -
        used when something other than a button click changes the active
        tab, e.g. auto-opening Setup on first run."""
        self.selected = value
        self._restyle()

    def pack(self, **kwargs) -> None:
        self.frame.pack(**kwargs)


class FlowRow:
    """Packs a fixed list of widgets left-to-right into `row1`, wrapping the
    tail (from `wrap_index` onward) onto `row2` only when everything won't
    fit on one line at the container's current width - so a form widens
    back onto one row as the window grows, instead of staying stuck on
    whatever row split it started with. `container` should be an ancestor
    frame whose width tracks the window (e.g. packed with fill="x") -
    that's what's watched for resize via <Configure>.

    items: list of (widget, left_pad_px) - left_pad_px is the gap before
    that widget when it's not the first control on its row. All widgets
    must already have `container` (or a descendant of it) as their master,
    since pack(in_=...) only works within the same toplevel."""

    def __init__(self, container, row1, row2, items: list[tuple], wrap_index: int) -> None:
        self.container = container
        self.row1 = row1
        self.row2 = row2
        self.items = items
        self.wrap_index = wrap_index
        self._job: str | None = None
        container.bind("<Configure>", self._on_configure)

    def _on_configure(self, _event=None) -> None:
        # <Configure> fires a lot mid-drag (and once more from our own
        # repacking toggling row2's height) - coalesce into one relayout per
        # burst instead of recomputing on every pixel.
        if self._job is not None:
            self.container.after_cancel(self._job)
        self._job = self.container.after(50, self.relayout)

    def relayout(self) -> None:
        self._job = None
        self.container.update_idletasks()
        available = self.container.winfo_width()
        if available <= 1:
            return  # not realized yet

        for w, _pad in self.items:
            w.pack_forget()

        one_row_width = sum(w.winfo_reqwidth() for w, _ in self.items) \
            + sum(pad for _, pad in self.items[1:])

        if one_row_width <= available:
            self.row2.pack_forget()
            for i, (w, pad) in enumerate(self.items):
                w.pack(in_=self.row1, side="left", padx=(pad if i else 0, 0))
        else:
            for i, (w, pad) in enumerate(self.items[:self.wrap_index]):
                w.pack(in_=self.row1, side="left", padx=(pad if i else 0, 0))
            for i, (w, pad) in enumerate(self.items[self.wrap_index:]):
                w.pack(in_=self.row2, side="left", padx=(pad if i else 0, 0))
            self.row2.pack(fill="x", pady=(8, 0))


class DynamicWrapLabel:
    """A CTkLabel whose wraplength tracks its parent's actual width instead
    of a fixed pixel guess - a hardcoded wraplength (e.g. 800) overflows
    past the window's edge and gets clipped whenever the window is
    narrower than that, instead of wrapping to fit. Bind `container` to
    whatever ancestor's width should drive the wrap point (usually the
    label's own parent, packed with fill="x")."""

    def __init__(self, parent, container, text: str = "", **kwargs) -> None:
        self.label = ctk.CTkLabel(parent, text=text, justify="left", wraplength=600, **kwargs)
        self._job: str | None = None
        container.bind("<Configure>", self._on_configure)
        container.after(100, self._resize)

    def pack(self, **kwargs) -> None:
        self.label.pack(**kwargs)

    def configure(self, **kwargs) -> None:
        self.label.configure(**kwargs)

    def _on_configure(self, _event=None) -> None:
        if self._job is not None:
            self.label.after_cancel(self._job)
        self._job = self.label.after(50, self._resize)

    def _resize(self) -> None:
        self._job = None
        self.label.update_idletasks()
        width = self.label.master.winfo_width()
        if width > 20:
            self.label.configure(wraplength=max(200, width - 20))


class HelpButton:
    """A 'Help v' chip, styled to match ButtonBar's idle/selected look,
    that drops open a small borderless overlay window with CLI help text
    for whatever tab is currently active - pulled live from
    npmpi.cli._help_sections()/_render_section() (the exact same content
    `npmpi <command> -h` prints), rather than a separately-maintained copy
    that could drift out of sync.

    get_commands_and_title is called fresh every time the button is opened
    - a callable returning (title: str, command_names: list[str]) for
    whatever's currently selected, so switching tabs before reopening
    always shows the right content without the caller needing to push
    updates into this widget."""

    def __init__(self, parent, get_commands_and_title: Callable[[], tuple[str, list[str]]]) -> None:
        self.get_commands_and_title = get_commands_and_title
        self._popup: ctk.CTkToplevel | None = None
        self.button = ctk.CTkButton(
            parent, text="Help ▾", width=90, height=36, corner_radius=8,
            font=ctk.CTkFont(size=16),
            fg_color=INACTIVE_BG, text_color=INACTIVE_TEXT, hover_color=INACTIVE_HOVER,
            command=self._toggle,
        )

    def pack(self, **kwargs) -> None:
        self.button.pack(**kwargs)

    def close(self) -> None:
        """Close the popup if open - called by the app when switching tabs,
        since open content would otherwise be for the tab just left."""
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
        self.button.configure(fg_color=INACTIVE_BG, text_color=INACTIVE_TEXT, hover_color=INACTIVE_HOVER)

    def _toggle(self) -> None:
        if self._popup is not None:
            self.close()
        else:
            self._open()

    def _open(self) -> None:
        from npmpi.cli import _help_sections, _render_section  # local import - avoids loading cli.py until needed

        title, command_names = self.get_commands_and_title()
        sections = {s[0]: s for s in _help_sections()}
        lines: list[str] = []
        for name in command_names:
            section = sections.get(name)
            if section:
                lines.extend(_render_section(section))
        text = "\n".join(lines).rstrip() or "No help available for this tab."

        self.button.configure(fg_color=ACCENT, text_color="white", hover_color=ACCENT)

        popup = ctk.CTkToplevel(self.button)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(fg_color=("gray90", "gray14"))

        header = ctk.CTkFrame(popup, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(header, text=f"{title} - help", font=ctk.CTkFont(size=14, weight="bold")).pack(side="left")
        ctk.CTkButton(
            header, text="×", width=28, height=28, corner_radius=6,
            fg_color="transparent", hover_color=INACTIVE_HOVER, text_color=INACTIVE_TEXT,
            command=self.close,
        ).pack(side="right")

        box = ctk.CTkTextbox(popup, wrap="word", font=ctk.CTkFont(family="Consolas", size=12))
        box.insert("1.0", text)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, padx=10, pady=10)

        width, height = 560, 460
        x = self.button.winfo_rootx() + self.button.winfo_width() - width
        y = self.button.winfo_rooty() + self.button.winfo_height() + 4
        popup.geometry(f"{width}x{height}+{max(x, 0)}+{y}")

        popup.bind("<Escape>", lambda e: self.close())
        popup.bind("<FocusOut>", lambda e: self.close())
        popup.focus_force()

        self._popup = popup
