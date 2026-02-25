"""Global test configuration — adds backend/ to sys.path so all packages are importable."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
