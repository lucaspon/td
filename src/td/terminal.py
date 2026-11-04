from __future__ import annotations

import os
import sys
import time

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
KEY_PAGE_UP = "\x1b[5~"
KEY_PAGE_DOWN = "\x1b[6~"
KEY_SHIFT_ARROW_UP = "\x1b[1;2A"
KEY_SHIFT_ARROW_DOWN = "\x1b[1;2B"
KEY_SHIFT_TAB = "\x1b[Z"
KEY_ALT_ARROW_UP = "\x1b[1;3A"
KEY_ALT_ARROW_DOWN = "\x1b[1;3B"
KEY_ALT_ARROW_LEFT = "\x1b[1;3D"
KEY_ALT_ARROW_RIGHT = "\x1b[1;3C"
KEY_ALT_WORD_LEFT = "\x1bb"
KEY_ALT_WORD_RIGHT = "\x1bf"
KEY_ALT_BACKSPACE = "\x1b\x7f"
KEY_ALT_BACKSPACE_BS = "\x1b\x08"
KEY_CTRL_ARROW_UP = "\x1b[1;5A"
KEY_CTRL_ARROW_DOWN = "\x1b[1;5B"
KEY_CTRL_BACKSPACE = "\x17"
KEY_CMD_BACKSPACE = "\x15"
KEY_CTRL_P = "\x10"
KEY_CTRL_S = "\x13"
KEY_RESIZE = "<resize>"

_last_size: os.terminal_size | None = None
_RESIZE_POLL_INTERVAL = 0.05


def get_terminal_size() -> os.terminal_size:
    """Read live terminal dimensions, without stale COLUMNS/LINES overrides."""
    for stream in (sys.stdout, sys.stdin):
        try:
            size = os.get_terminal_size(stream.fileno())
        except (AttributeError, OSError, ValueError):
            continue
        if size.columns > 0 and size.lines > 0:
            return size
    return os.terminal_size((80, 24))


def _terminal_resized() -> bool:
    global _last_size
    size = get_terminal_size()
    changed = _last_size is not None and size != _last_size
    _last_size = size
    return changed


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
        "I": KEY_PAGE_UP,
        "Q": KEY_PAGE_DOWN,
        "S": KEY_DELETE,
        "\x0f": KEY_SHIFT_TAB,
        "\x8d": KEY_CTRL_ARROW_UP,
        "\x91": KEY_CTRL_ARROW_DOWN,
        "\x98": KEY_ALT_ARROW_UP,
        "\xa0": KEY_ALT_ARROW_DOWN,
        "\x9b": KEY_ALT_ARROW_LEFT,
        "\x9d": KEY_ALT_ARROW_RIGHT,
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
            global _last_size
            _last_size = get_terminal_size()
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
        while True:
            if _terminal_resized():
                return KEY_RESIZE
            if msvcrt.kbhit():
                break
            time.sleep(_RESIZE_POLL_INTERVAL)
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
            return KEY_BACKSPACE
        if ch == "\x7f":  # Windows Ctrl+Backspace
            return KEY_CTRL_BACKSPACE
        return ch

else:
    import codecs
    import select
    import tty
    import termios

    _input_decoder = codecs.getincrementaldecoder(
        sys.stdin.encoding or "utf-8"
    )(errors="replace")

    class _RawContext:
        """Context manager for raw terminal mode on Unix."""
        def __init__(self):
            self.fd = sys.stdin.fileno()
            self.old_settings = termios.tcgetattr(self.fd)

        def __enter__(self):
            global _last_size, _input_decoder
            tty.setcbreak(self.fd)
            _last_size = get_terminal_size()
            _input_decoder = codecs.getincrementaldecoder(
                sys.stdin.encoding or "utf-8"
            )(errors="replace")
            return self

        def __exit__(self, *args):
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)

    def raw_mode():
        return _RawContext()

    ESC = "\x1b"

    def _read_char(fd: int, timeout: float | None = None) -> str:
        """Wait for input or a resize; keep pasted UTF-8 input out of TextIO buffers."""
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            if deadline is None and _terminal_resized():
                return KEY_RESIZE
            wait = _RESIZE_POLL_INTERVAL
            if deadline is not None:
                wait = min(wait, max(0, deadline - time.monotonic()))
            if select.select([fd], [], [], wait)[0]:
                data = os.read(fd, 1)
                if not data:
                    return ""
                char = _input_decoder.decode(data)
                if char:
                    return char
            if deadline is not None and time.monotonic() >= deadline:
                return ""

    def read_key() -> str:
        """Read a key or resize event without waiting for the next keypress."""
        fd = sys.stdin.fileno()
        ch = _read_char(fd)
        if ch == ESC:
            seq = ch
            while True:
                char = _read_char(fd, timeout=0.1)
                if not char:
                    break
                seq += char
                if char.isalpha() or char == "~":
                    break
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
