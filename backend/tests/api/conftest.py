"""API test configuration — adds backend/api/ to sys.path.

The api package uses flat imports like `from core.config import get_settings`
(not `api.core.config`), so backend/api/ must be on sys.path in addition to
backend/ (which the global conftest already adds).
"""

import sys
from pathlib import Path

_API_DIR = Path(__file__).parent.parent.parent / "api"

if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))
