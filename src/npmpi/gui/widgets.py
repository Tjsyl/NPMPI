"""Small shared GUI building blocks."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

ACCENT = "#3d7eff"
INACTIVE_TEXT = ("gray40", "gray55")
INACTIVE_HOVER = ("gray85", "gray25")


class ButtonBar:
    """A row of separate, individually-styled buttons - not one connected
    segmented control. Unselected buttons sit flat/grey; the selected one
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
                fg_color="transparent", text_color=INACTIVE_TEXT,
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
                btn.configure(fg_color="transparent", text_color=INACTIVE_TEXT, hover_color=INACTIVE_HOVER)

    def set(self, value: str) -> None:
        """Update selection programmatically (no command callback fired) -
        used when something other than a button click changes the active
        tab, e.g. auto-opening Setup on first run."""
        self.selected = value
        self._restyle()

    def pack(self, **kwargs) -> None:
        self.frame.pack(**kwargs)
