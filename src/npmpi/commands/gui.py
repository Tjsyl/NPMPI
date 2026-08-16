"""
npmpi gui - launch the npmpi desktop GUI.

    npmpi gui

Every command (add/sync/list/find/gen/migrate/setup) is available as a tab
in one window, calling the same underlying code the CLI commands use - the
CLI itself is untouched and works exactly as before regardless of whether
the GUI is ever used. Safe to run even before `npmpi setup` has been run
at all - it opens straight to the Setup tab in that case.

There's also a second, separate executable - npmpigui.exe (built from
src/npmpi/gui_main.py) - that always opens straight to the GUI with no
CLI dispatch at all, meant for a desktop/Start Menu shortcut so
double-clicking or Win+R gets you the GUI without typing this subcommand.
It calls run_app() directly rather than going through this command at
all. npmpi.exe (this file's command) stays CLI-only and unchanged
regardless of how it's launched - a single console-subsystem exe can't
reliably tell double-click apart from an existing terminal once
PyInstaller's onefile bootloader is involved, so we don't try.
"""

from __future__ import annotations

import argparse


def register(subparsers) -> None:
    p = subparsers.add_parser(
        "gui",
        help="Launch the npmpi desktop GUI",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p.set_defaults(func=cmd_gui, _skip_config_load=True)


def cmd_gui(cfg, creds, args) -> int:
    from npmpi.gui.app import run_app  # lazy import - customtkinter/Tk only touched when actually launching the GUI
    run_app()
    return 0
