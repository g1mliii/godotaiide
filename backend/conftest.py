"""
Pytest configuration file.

This file is automatically loaded by pytest and ensures the backend
directory is in the Python path for proper module imports.
"""

import sys
from pathlib import Path

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
