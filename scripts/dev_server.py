"""Start the API for local development (uses a local .pydeps folder if present)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path[:0] = [str(ROOT), str(ROOT / ".pydeps")]

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
