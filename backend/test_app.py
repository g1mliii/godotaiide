"""Test script to verify app routes"""

import sys

sys.path.insert(0, ".")

import uvicorn  # noqa: E402

from main import app  # noqa: E402

print("Registered routes:")
for route in app.routes:
    print(f"  {route.path} - {route.methods if hasattr(route, 'methods') else 'N/A'}")

print("\nStarting test server...")
uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
