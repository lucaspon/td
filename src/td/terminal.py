from __future__ import annotations

import os
import sys

IS_WINDOWS = sys.platform == "win32"


# Key constants. The Unix terminal emits these ANSI sequences directly; on
# Windows we translate the native scancode protocol into the same strings so
# the rest of the app can compare keys identically on every platform.
KEY_ENTER = "\n"
KEY_BACKSPACE = "\x7f"
KEY_DELETE = "\x1b[3~"
KEY_ESC = "\x1b"
KEY_ARROW_UP = "\x1b[A"
KEY_ARROW_DOWN = "\x1b[B"
KEY_ARROW_LEFT = "\x1b[D"
KEY_ARROW_RIGHT = "\x1b[C"
KEY_HOME = "\x1b[H"
KEY_END = "\x1b[F"
KEY_SHIFT_ARROW_UP = "\x1b[1;2A"
KEY_SHIFT_ARROW_DOWN = "\x1b[1;2B"
KEY_ALT_ARROW_UP = "\x1b[1;3A"
KEY_ALT_ARROW_DOWN = "\x1b[1;3B"
KEY_CTRL_ARROW_UP = "\x1b[1;5A"
KEY_CTRL_ARROW_DOWN = "\x1b[1;5B"
KEY_CTRL_P = "\x10"


if IS_WINDOWS:
    import msvcrt

    # Windows delivers special keys as a two-char sequence: a prefix of
    # '\x00' or '\xe0' followed by a scancode char. Map each scancode to the
    # matching ANSI sequence above. Keys absent here (e.g. Shift+arrow, which
    # legacy consoles don't report distinctly) simply do nothing.
    _WIN_SCANCODE_MAP = {
        "H": KEY_ARROW_UP,
        "P": KEY_ARROW_DOWN,
        "K": KEY_ARROW_LEFT,
        "M": KEY_ARROW_RIGHT,
        "G": KEY_HOME,
        "O": KEY_END,
        "S": KEY_DELETE,
        "\x8d": KEY_CTRL_ARROW_UP,
        "\x91": KEY_CTRL_ARROW_DOWN,
        "\x98": KEY_ALT_ARROW_UP,
        "\xa0": KEY_ALT_ARROW_DOWN,
    }

    def _enable_vt_mode() -> None:
        """Enable virtual terminal processing for ANSI escapes on Windows."""
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            mode.value |= 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(handle, mode)
        except Exception:
            # Older consoles may not support VT mode; rendering degrades but
            # the app should not crash on startup.
            pass

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
        """Read a single keypress on Windows.

        Special keys arrive as a '\\x00'/'\\xe0' prefix plus a scancode, which
        we translate to ANSI sequences. A literal Esc (or a VT-input terminal
        sending real escape sequences) is handled as a fallback.
        """
        ch = msvcrt.getwch()

        # Native special-key protocol.
        if ch in ("\x00", "\xe0"):
            scan = msvcrt.getwch()
            return _WIN_SCANCODE_MAP.get(scan, "")

        # Real ANSI escape: plain Esc, or VT input mode passing sequences through.
        if ch == "\x1b":
            seq = ch
            if msvcrt.kbhit():
                ch2 = msvcrt.getwch()
                seq += ch2
                if ch2 == "[":
                    while msvcrt.kbhit():
                        c = msvcrt.getwch()
                        seq += c
                        if c.isalpha() or c == "~":
                            break
            return seq

        if ch == "\r":
            return "\n"
        if ch == "\x08":  # Windows backspace
            return "\x7f"
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


def reset_cursor() -> None:
    sys.stdout.write("\033[H")
    sys.stdout.flush()


def hide_cursor() -> None:
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def show_cursor() -> None:
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()
