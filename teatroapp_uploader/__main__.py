# -*- coding: utf-8 -*-
"""Entry-point: py -m teatroapp_uploader"""

from __future__ import annotations

import sys
from typing import Optional

from .env import load_config
from .runner import run


def main(argv: Optional[list[str]] = None) -> int:
    _ = argv or sys.argv[1:]
    cfg = load_config()
    return run(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
