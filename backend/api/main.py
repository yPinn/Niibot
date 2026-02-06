"""Application entry point

Run with:
    python main.py
    or
    uvicorn main:app --reload
"""

import sys
from pathlib import Path

# Add parent directory to path for shared imports — must be before any local imports
sys.path.insert(0, str(Path(__file__).parent.parent))

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
