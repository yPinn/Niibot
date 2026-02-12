"""Application entry point

Run with:
    python main.py
    or
    uvicorn main:app --reload
"""

import sys
from pathlib import Path

# Ensure shared module is importable (backend/ directory)
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app import create_app  # noqa: E402
from core.config import get_settings  # noqa: E402

# Create the FastAPI application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development,
        log_config=None,  # We handle logging ourselves
    )
