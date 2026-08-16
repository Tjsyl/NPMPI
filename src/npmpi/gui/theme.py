"""Appearance-mode (light/dark/system) helpers shared across the GUI."""

from __future__ import annotations

import customtkinter as ctk

from npmpi.gui.widgets import ButtonBar

MODES = ["System", "Light", "Dark"]


def init_appearance() -> None:
    """Call once at startup - defaults to following Windows' own theme."""
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")


def set_mode(mode: str) -> None:
    if mode in MODES:
        ctk.set_appearance_mode(mode)


def make_mode_switcher(parent) -> ButtonBar:
    """A small System/Light/Dark button row - same greyed-out/turns-blue
    style as the main tab bar - that live-switches the whole app's
    appearance mode when clicked."""
    return ButtonBar(parent, MODES, command=set_mode, initial="System")
