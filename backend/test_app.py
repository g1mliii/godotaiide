"""Test script to verify app routes"""

import sys

sys.path.insert(0, ".")

from main import app

print("Registered routes:")
for route in app.routes:
    print(f"  {route.path} - {route.methods if hasattr(route, 'methods') else 'N/A'}")

print("\nStarting test server...")
import uvicorn

uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
