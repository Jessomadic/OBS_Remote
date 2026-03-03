"""Shared pytest fixtures and path setup for OBS Remote tests."""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so 'server', 'version', etc. are importable
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
