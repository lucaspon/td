from __future__ import annotations

import sys

from .tui import run_main, run_archive


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "archive":
        run_archive()
    else:
        run_main()


if __name__ == "__main__":
    main()