"""
run.py — Local launcher for development / production on Kali Linux / VPS.

Usage:
    python run.py

This script:
  1. Validates required environment variables.
  2. Runs Alembic migrations automatically.
  3. Starts the uvicorn server.
"""
from __future__ import annotations

import os
import subprocess
import sys

# ---------------------------------------------------------------------------
# Load .env if present
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Validate configuration
# ---------------------------------------------------------------------------
from app.config import get_settings

settings = get_settings()

# Will raise SystemExit if required vars are missing
settings.validate_required_for_run()

# ---------------------------------------------------------------------------
# Auto-run Alembic migrations
# ---------------------------------------------------------------------------
print("[run.py] Running Alembic migrations...")
result = subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    capture_output=False,
)
if result.returncode != 0:
    print("[run.py] ERROR: Alembic migration failed. Fix the database schema before starting.", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Start uvicorn
# ---------------------------------------------------------------------------
import uvicorn

if __name__ == "__main__":
    print(f"[run.py] Starting Network Monitor on {settings.app_host}:{settings.app_port}")
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
        workers=1,
    )
