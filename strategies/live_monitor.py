"""Backwards-compatible entry point.

The live logic now lives in ``trade_lab.live``. Prefer:

    python -m trade_lab.live [--dry-run]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trade_lab.live import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
