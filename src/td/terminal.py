from __future__ import annotations

import os
import sys

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import msvcrt

    def _enable_vt_mode() -> None:
        """Enable virtual terminal processing for ANSI escapes on Windows."""
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        mode.value |= 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        kernel32.SetConsoleMode(handle, mode)

    _enable_vt_mode()

    class _RawContext:
        """Context manager for raw terminal mode on Windows."""
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def raw_mode():
        return _RawContext()

    def read_key() -> str:
        """Read a single keypress on Windows, handling escape sequences."""
        ch = msvcrt.getwch()
        if ch == '\x1b':
            # Check for extended key sequence
            seq = ch
            if msvcrt.kbhit():
                ch2 = msvcrt.getwch()
                if ch2 == '[':
                    seq += ch2
                    if msvcrt.kbhit():
                        ch3 = msvcrt.getwch()
                        seq += ch3
                        # Check for CSI sequences like 1;2A (shift-arrow)
                        if ch3 == '1':
                            if msvcrt.kbhit():
                                ch4 = msvcrt.getwch()  # ';'
                                seq += ch4
                                if msvcrt.kbhit():
                                    ch5 = msvcrt.getwch()  # modifier
                                    seq += ch5
                                    if msvcrt.kbhit():
                                        ch6 = msvcrt.getwch()  # direction
                                        seq += ch6
                else:
                    seq += ch2
            return seq
        if ch == '\r':
            return '\n'
        if ch == '\x08':  # Windows backspace
            return '\x7f'
        return ch

else:
    import tty
    import termios

    class _RawContext:
        """Context manager for raw terminal mode on Unix."""
        def __init__(self):
            self.fd = sys.stdin.fileno()
            self.old_settings = termios.tcgetattr(self.fd)

        def __enter__(self):
            tty.setcbreak(self.fd)
            return self

        def __exit__(self, *args):
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)

    def raw_mode():
        return _RawContext()

    ESC = "\x1b"

    def read_key() -> str:
        """Read a single keypress on Unix, handling escape sequences."""
        fd = sys.stdin.fileno()
        ch = sys.stdin.read(1)
        if ch == ESC:
            seq = ch
            try:
                old = termios.tcgetattr(fd)
                new = termios.tcgetattr(fd)
                new[3] = new[3] & ~(termios.ICANON | termios.ECHO)
                new[6][termios.VMIN] = 0
                new[6][termios.VTIME] = 1
                termios.tcsetattr(fd, termios.TCSANOW, new)
                while True:
                    c = sys.stdin.read(1)
                    if c:
                        seq += c
                        if c.isalpha() or c == "~":
                            break
                    else:
                        break
                termios.tcsetattr(fd, termios.TCSANOW, old)
            except Exception:
                pass
            return seq
        return ch


def clear_screen() -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def hide_cursor() -> None:
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def show_cursor() -> None:
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


# Key constants (ANSI sequences work cross-platform with VT mode on Windows)
KEY_ENTER = "\n"
KEY_BACKSPACE = "\x7f"
KEY_DELETE = "\x1b[3~"
KEY_ESC = "\x1b"
KEY_ARROW_UP = "\x1b[A"
KEY_ARROW_DOWN = "\x1b[B"
KEY_SHIFT_ARROW_UP = "\x1b[1;2A"
KEY_SHIFT_ARROW_DOWN = "\x1b[1;2B"
KEY_ALT_ARROW_UP = "\x1b[1;3A"
KEY_ALT_ARROW_DOWN = "\x1b[1;3B"