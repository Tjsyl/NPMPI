"""
Runs a blocking npmpi operation (anything that talks to NPM/Pi-hole over the
network) on a background thread so the GUI never freezes, while streaming
whatever it prints to stdout live into a textbox - the same trick that lets
the GUI reuse the CLI command functions (cmd_add, cmd_sync, cmd_gen, and the
lower-level netops.py/npm.py/pihole.py functions used by the Migrate/Setup
wizards) completely unchanged instead of re-implementing their output.
"""

from __future__ import annotations

import io
import queue
import sys
import threading
from typing import Callable


class _QueueWriter(io.TextIOBase):
    def __init__(self, q: queue.Queue) -> None:
        self.q = q

    def write(self, s: str) -> int:
        if s:
            self.q.put(s)
        return len(s)

    def flush(self) -> None:
        pass


def run_captured(
    textbox,
    fn: Callable[[], int],
    on_done: Callable[[int | None, BaseException | None], None] | None = None,
) -> None:
    """Run fn() on a background thread with sys.stdout redirected into
    `textbox` (any widget with .insert/.see, e.g. a CTkTextbox). fn should
    return an int return-code like the CLI cmd_* functions do. on_done, if
    given, is called back on the Tk main thread (safe to touch widgets)
    with (return_code, exception_or_None) once fn finishes."""
    q: queue.Queue = queue.Queue()
    result: dict = {}

    def worker() -> None:
        writer = _QueueWriter(q)
        old_stdout = sys.stdout
        sys.stdout = writer
        try:
            result["rc"] = fn()
        except BaseException as e:  # noqa: BLE001 - surfaced to the GUI, not swallowed
            result["error"] = e
        finally:
            sys.stdout = old_stdout
            q.put(None)  # sentinel: worker finished

    threading.Thread(target=worker, daemon=True).start()

    def poll() -> None:
        try:
            while True:
                item = q.get_nowait()
                if item is None:
                    if on_done:
                        on_done(result.get("rc"), result.get("error"))
                    return
                textbox.insert("end", item)
                textbox.see("end")
        except queue.Empty:
            pass
        textbox.after(50, poll)

    poll()
