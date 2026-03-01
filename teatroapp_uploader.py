# -*- coding: utf-8 -*-
"""teatroapp_uploader.py (compatibilidade)

Este ficheiro é apenas um *shim* para manter um entry-point único.
O código real vive no pacote `teatroapp_uploader/`.

Execução recomendada:
  - `py -m teatroapp_uploader`

Execução alternativa (este ficheiro):
  - `py teatroapp_uploader_entry.py`
"""

from __future__ import annotations

import sys
from typing import Optional

from teatroapp_uploader.__main__ import main as _pkg_main


def main(argv: Optional[list[str]] = None) -> int:
    return _pkg_main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))