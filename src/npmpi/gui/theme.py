"""Appearance-mode (light/dark/system) helpers shared across the GUI."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from npmpi.gui.widgets import ButtonBar

MODES = ["System", "Light", "Dark"]

# CTk widgets restyle themselves automatically on an appearance-mode change,
# but plain ttk widgets (e.g. list_tab.py's Treeview) don't - anything that
# needs to react registers a no-arg callback here instead.
_listeners: list[Callable[[], None]] = []


def init_appearance() -> None:
    """Call once at startup - defaults to following Windows' own theme."""
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")


def add_appearance_listener(fn: Callable[[], None]) -> None:
    """Register a callback to run every time the mode switcher changes the
    appearance mode - e.g. list_tab.py re-styling its ttk.Treeview, which
    CTk otherwise leaves stuck on whatever colors it had when first drawn."""
    _listeners.append(fn)


def set_mode(mode: str) -> None:
    if mode in MODES:
        ctk.set_appearance_mode(mode)
        for fn in _listeners:
            fn()


def make_mode_switcher(parent) -> ButtonBar:
    """A small System/Light/Dark button row - same greyed-out/turns-blue
    style as the main tab bar - that live-switches the whole app's
    appearance mode when clicked."""
    return ButtonBar(parent, MODES, command=set_mode, initial="System")
