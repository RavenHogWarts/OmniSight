"""``python -m omnisight`` 入口。"""

from __future__ import annotations

import sys

from .app import run


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
