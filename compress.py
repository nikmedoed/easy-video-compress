#!/usr/bin/env python3
import os
import sys


def _detach_console_for_gui_launch() -> None:
    if os.name != "nt":
        return
    args = sys.argv[1:]
    if args and args[0] not in {"gui", "--gui"}:
        return
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
        ctypes.windll.kernel32.FreeConsole()
    except Exception:
        pass


if __name__ == "__main__":
    _detach_console_for_gui_launch()
    from compress_tool.cli import main

    main()
