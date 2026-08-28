"""Sweep every AppError subclass defined anywhere in the API for contract
violations. Lives under tests/api/ because it imports the router package.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-error-catalog-secret-key-32chars")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

import app as _app  # noqa: F401  (imports every router → every domain error class)
from shared.errors import validate_catalog


def test_full_error_catalog_is_clean() -> None:
    problems = validate_catalog()
    assert not problems, "\n".join(problems)
