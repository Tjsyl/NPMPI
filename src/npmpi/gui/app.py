"""Main npmpi GUI window - a tabbed shell wiring together List/Find, Add,
Sync, Gen, Migrate, and Setup, all sharing one loaded config/credentials
state that any tab can trigger a reload of after it changes something."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from npmpi.config import config_exists, load_config
from npmpi.creds import creds_exist, load_creds
from npmpi.gui import theme
from npmpi.gui.tabs.add_tab import AddTab
from npmpi.gui.tabs.gen_tab import GenTab
from npmpi.gui.tabs.list_tab import ListTab
from npmpi.gui.tabs.migrate_tab import MigrateTab
from npmpi.gui.tabs.setup_tab import SetupTab
from npmpi.gui.tabs.sync_tab import SyncTab
from npmpi.gui.widgets import ButtonBar

TAB_NAMES = ["List / Find", "Add", "Sync", "Gen", "Migrate", "Setup"]


def _asset_path(name: str) -> Path:
    """Resolve a bundled GUI asset (icon, etc.) whether running from a source
    checkout or from the PyInstaller-frozen exe, where data files added via
    --add-data are extracted under sys._MEIPASS instead of living next to
    this file on disk."""
    if getattr(sys, "_MEIPASS", None):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parents[2]  # .../src
    return base / "npmpi" / "gui" / "assets" / name


class NpmpiApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("npmpi")
        self.geometry("980x640")
        self.minsize(760, 480)
        self._set_icon()

        self.cfg: dict = {}
        self.creds: dict = {}
        self._tabs: list = []
        self._load_state(initial=True)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 0))
        ctk.CTkLabel(header, text="npmpi", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        theme.make_mode_switcher(header).pack(side="right")

        self.tab_bar = ButtonBar(self, TAB_NAMES, command=self._show_tab, initial=TAB_NAMES[0])
        self.tab_bar.pack(fill="x", padx=16, pady=(14, 0))

        self.tab_container = ctk.CTkFrame(self, fg_color="transparent")
        self.tab_container.pack(fill="both", expand=True, padx=16, pady=16)

        self._tab_frames: dict[str, ctk.CTkFrame] = {
            name: ctk.CTkFrame(self.tab_container, fg_color="transparent") for name in TAB_NAMES
        }

        self.list_tab = ListTab(self._tab_frames["List / Find"], self)
        self.add_tab = AddTab(self._tab_frames["Add"], self)
        self.sync_tab = SyncTab(self._tab_frames["Sync"], self)
        self.gen_tab = GenTab(self._tab_frames["Gen"], self)
        self.migrate_tab = MigrateTab(self._tab_frames["Migrate"], self)
        self.setup_tab = SetupTab(self._tab_frames["Setup"], self)
        self._tabs = [self.list_tab, self.add_tab, self.sync_tab, self.gen_tab, self.migrate_tab, self.setup_tab]

        self._show_tab(TAB_NAMES[0])
        if not self.has_config:
            self._show_tab("Setup")

    def _set_icon(self) -> None:
        """Best-effort - a missing or unsupported icon file should never
        stop the app from launching. .ico via iconbitmap gives the sharpest
        result on Windows (titlebar + taskbar + Alt-Tab); iconphoto with the
        .png is the cross-platform fallback if that's unavailable."""
        try:
            ico = _asset_path("icon.ico")
            if ico.exists():
                self.iconbitmap(default=str(ico))
                return
        except Exception:
            pass
        try:
            png = _asset_path("icon.png")
            if png.exists():
                self._icon_img = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _show_tab(self, name: str) -> None:
        for tab_name, frame in self._tab_frames.items():
            if tab_name == name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()
        self.tab_bar.set(name)

    def _load_state(self, initial: bool = False) -> None:
        if config_exists():
            self.cfg = load_config()
        else:
            self.cfg = {}
        if creds_exist():
            self.creds = load_creds()
        else:
            self.creds = {}
        if not initial:
            for tab in self._tabs:
                refresh = getattr(tab, "on_config_reloaded", None)
                if refresh:
                    refresh()

    @property
    def has_config(self) -> bool:
        return bool(self.cfg.get("sites"))

    def reload(self) -> None:
        """Called by any tab (typically Setup) after it writes config.json/
        credentials.dat, so every other open tab picks up the change without
        needing a restart."""
        self._load_state(initial=False)


def run_app() -> None:
    theme.init_appearance()
    app = NpmpiApp()
    app.mainloop()
