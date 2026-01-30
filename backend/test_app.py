"""Test script to verify app routes"""

import sys

sys.path.insert(0, ".")

import uvicorn  # noqa: E402

from main import app  # noqa: E402

print("Registered routes:")
for route in app.routes:
    path = getattr(route, "path", "N/A")
    methods = getattr(route, "methods", "N/A")
    print(f"  {path} - {methods}")

print("\nStarting test server...")
uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
