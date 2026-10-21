"""J.A.R.V.I.S. Assistant Launcher.

Forwards to main.main() with full CLI flag compatibility.
"""

from __future__ import annotations

import sys
from main import main

if __name__ == "__main__":
    sys.exit(main())
