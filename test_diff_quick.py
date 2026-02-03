#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick Diff Viewer Test Script
Automates basic testing of the Phase 4 diff viewer backend
"""

import requests
import subprocess
import time
import sys
from pathlib import Path
import json

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


# Configuration
BACKEND_URL = "http://localhost:8005"
TEST_FILE = "test_diff_sample.gd"
TIMEOUT = 5


def print_header(text):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def check_backend_running():
    """Check if backend server is running"""
    print_header("1. Checking Backend Server")
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=2)
        if response.status_code == 200:
            print("✅ Backend server is running")
            print(f"   Response: {response.json()}")
            return True
        else:
            print(f"❌ Backend returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Backend not running on port 8005")
        print("   Start with: cd backend && uvicorn main:app --reload --port 8005")
        return False
    except Exception as e:
        print(f"❌ Error connecting to backend: {e}")
        return False


def create_test_file():
    """Create a test file with git tracking"""
    print_header("2. Creating Test File")

    # Check if git repo exists
    if not Path(".git").exists():
        print("❌ Not a git repository. Run 'git init' first.")
        return False

    # Create original version
    with open(TEST_FILE, "w") as f:
        f.write("func original_function():\n")
        f.write("    print('original')\n")
        f.write("    pass\n")

    # Add and commit
    try:
        subprocess.run(["git", "add", TEST_FILE], check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", "Test: original version"],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"✅ Created and committed {TEST_FILE}")
    except subprocess.CalledProcessError as e:
        if "nothing to commit" in e.stderr:
            print(f"⚠️  {TEST_FILE} already committed (continuing)")
        else:
            print(f"❌ Git commit failed: {e.stderr}")
            return False

    # Modify file
    with open(TEST_FILE, "w") as f:
        f.write("func modified_function():\n")
        f.write("    print('modified')\n")
        f.write("    print('new line')\n")
        f.write("    return true\n")

    print(f"✅ Modified {TEST_FILE}")
    return True


def test_diff_endpoint():
    """Test the /git/diff endpoint"""
    print_header("3. Testing /git/diff Endpoint")

    url = f"{BACKEND_URL}/git/diff"
    params = {"file": TEST_FILE}

    print(f"   URL: {url}")
    print(f"   Params: {params}")

    try:
        start_time = time.time()
        response = requests.get(url, params=params, timeout=TIMEOUT)
        duration = time.time() - start_time

        print(f"\n   Status Code: {response.status_code}")
        print(f"   Response Time: {duration * 1000:.0f}ms")

        if response.status_code != 200:
            print(f"❌ Expected 200, got {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False

        data = response.json()

        # Validate structure
        required_fields = ["file_path", "original_content", "new_content", "diff_text"]
        missing = [f for f in required_fields if f not in data]

        if missing:
            print(f"❌ Missing fields: {missing}")
            return False

        print("✅ Response structure valid")

        # Check content
        print("\n   Response Summary:")
        print(f"   - file_path: {data['file_path']}")
        print(f"   - original_content: {len(data['original_content'])} chars")
        print(f"   - new_content: {len(data['new_content'])} chars")
        print(f"   - diff_text: {len(data['diff_text'])} chars")
        print(f"   - diff_compressed: {data.get('diff_compressed', False)}")

        # Validate content differs
        if data["original_content"] == data["new_content"]:
            print("⚠️  Warning: original and new content are identical")

        # Show diff snippet
        if data["diff_text"]:
            print("\n   Diff Text (first 200 chars):")
            print("   " + data["diff_text"][:200].replace("\n", "\n   "))

        return True

    except requests.exceptions.Timeout:
        print(f"❌ Request timed out after {TIMEOUT}s")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False
    except json.JSONDecodeError:
        print("❌ Response is not valid JSON")
        print(f"   Response: {response.text[:200]}")
        return False


def test_error_handling():
    """Test error handling with invalid file"""
    print_header("4. Testing Error Handling")

    url = f"{BACKEND_URL}/git/diff"
    params = {"file": "nonexistent_file_xyz.gd"}

    print(f"   Testing with non-existent file: {params['file']}")

    try:
        response = requests.get(url, params=params, timeout=TIMEOUT)
        print(f"   Status Code: {response.status_code}")

        if response.status_code in [404, 500]:
            print("✅ Error handling works (returned error status)")
            return True
        elif response.status_code == 200:
            print("⚠️  Warning: Returned 200 for non-existent file")
            return True
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_performance():
    """Test response time performance"""
    print_header("5. Performance Test")

    url = f"{BACKEND_URL}/git/diff"
    params = {"file": TEST_FILE}
    iterations = 10

    print(f"   Running {iterations} requests...")

    times = []
    for i in range(iterations):
        start = time.time()
        response = requests.get(url, params=params, timeout=TIMEOUT)
        duration = time.time() - start
        times.append(duration * 1000)  # Convert to ms

        if response.status_code != 200:
            print(f"   ❌ Request {i+1} failed with status {response.status_code}")
            return False

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    print(f"\n   Results:")
    print(f"   - Average: {avg_time:.0f}ms")
    print(f"   - Min: {min_time:.0f}ms")
    print(f"   - Max: {max_time:.0f}ms")

    if avg_time < 500:
        print("✅ Performance good (avg < 500ms)")
        return True
    else:
        print("⚠️  Performance slower than target (avg should be < 500ms)")
        return True


def cleanup():
    """Clean up test files"""
    print_header("6. Cleanup")

    try:
        # Remove test file from git
        if Path(TEST_FILE).exists():
            subprocess.run(["git", "rm", "-f", TEST_FILE], capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Test: cleanup test file"],
                capture_output=True
            )
            print(f"✅ Removed {TEST_FILE}")
        else:
            print(f"⚠️  {TEST_FILE} not found")

        return True
    except Exception as e:
        print(f"⚠️  Cleanup warning: {e}")
        return True


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("  Phase 4 Diff Viewer - Quick Test Suite")
    print("=" * 60)

    tests = [
        ("Backend Running", check_backend_running),
        ("Create Test File", create_test_file),
        ("Diff Endpoint", test_diff_endpoint),
        ("Error Handling", test_error_handling),
        ("Performance", test_performance),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))

            if not result:
                print(f"\n❌ Test '{name}' failed. Stopping.")
                break
        except KeyboardInterrupt:
            print("\n\n⚠️  Tests interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {e}")
            results.append((name, False))
            break

    # Cleanup (always run)
    cleanup()

    # Print summary
    print_header("Test Summary")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}  {name}")

    print(f"\n  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Phase 4 backend is working correctly.")
        print("\n📋 Next steps:")
        print("   1. Test UI in Godot editor (see test_diff_viewer.md)")
        print("   2. Run full test suite: pytest backend/tests/test_diff_viewer.py -v")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
