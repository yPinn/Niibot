"""Twitch test configuration — adds twitch/ to sys.path so intra-service imports resolve.

Twitch components use bare `from core.xxx import ...` (relative to the twitch/
service root), which requires twitch/ on sys.path in addition to the backend/
root already added by the top-level conftest.

Both backend/api/ and backend/twitch/ expose a top-level `core` package.
pytest collects api/ before twitch/ (alphabetical order), so api's `core` may
already be cached in sys.modules when twitch tests are collected. We evict the
stale entries after inserting twitch/ at the front of sys.path so the next
import resolves to twitch/core/ instead.
"""

import sys
from pathlib import Path

TWITCH_DIR = Path(__file__).parent.parent.parent / "twitch"

if str(TWITCH_DIR) not in sys.path:
    sys.path.insert(0, str(TWITCH_DIR))

# Evict any api/core that was cached before this conftest ran.
for _key in list(sys.modules):
    if _key == "core" or _key.startswith("core."):
        del sys.modules[_key]
