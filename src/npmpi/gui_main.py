"""Entry point for npmpigui.exe - a second, separate executable (built
--windowed, no console subsystem at all) that always opens straight to the
npmpi GUI. No argv/CLI dispatch here whatsoever, unlike __main__.py/cli.py.

Exists so double-clicking, a Start Menu tile, a desktop shortcut, or Win+R
reliably opens the GUI - a single console-subsystem exe can't tell "double-
clicked" apart from "run from an existing terminal" once PyInstaller's
onefile bootloader is in the picture (see the note in commands/gui.py for
why that was tried and abandoned). npmpi.exe (from __main__.py) remains
the CLI, unchanged, and is what stays on PATH for terminal use; `npmpi gui`
there still works too, calling into the exact same npmpi.gui.app.run_app().
"""

from __future__ import annotations

from npmpi.gui.app import run_app

if __name__ == "__main__":
    run_app()
