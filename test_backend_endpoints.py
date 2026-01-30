"""
Quick test script to verify backend Git endpoints
Run this after starting the backend server: uvicorn main:app --reload --port 8005
"""
import requests
import json

BASE_URL = "http://127.0.0.1:8005"

def test_git_status():
    """Test GET /git/status"""
    print("\n=== Testing GET /git/status ===")
    response = requests.get(f"{BASE_URL}/git/status")
    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"Branch: {data.get('branch')}")
        print(f"Files: {len(data.get('files', []))} changed")
        print(f"Is Clean: {data.get('is_clean')}")

        # Print first 3 files
        for file in data.get('files', [])[:3]:
            print(f"  - {file['path']} [{file['status']}] (staged: {file['staged']})")
    else:
        print(f"Error: {response.text}")

def test_git_add():
    """Test POST /git/add"""
    print("\n=== Testing POST /git/add ===")

    # First get status to find a file to stage
    status_response = requests.get(f"{BASE_URL}/git/status")
    if status_response.status_code != 200:
        print("Cannot get status, skipping add test")
        return

    files = status_response.json().get('files', [])
    unstaged_files = [f for f in files if not f['staged']]

    if not unstaged_files:
        print("No unstaged files to test with")
        return

    test_file = unstaged_files[0]['path']
    print(f"Staging file: {test_file}")

    response = requests.post(
        f"{BASE_URL}/git/add",
        json={"files": [test_file]}
    )
    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"Success: {data.get('success')}")
        print(f"Message: {data.get('message')}")
    else:
        print(f"Error: {response.text}")

def test_ai_commit_message():
    """Test POST /ai/generate/commit-message"""
    print("\n=== Testing POST /ai/generate/commit-message ===")

    # Get staged files
    status_response = requests.get(f"{BASE_URL}/git/status")
    if status_response.status_code != 200:
        print("Cannot get status, skipping AI test")
        return

    files = status_response.json().get('files', [])
    staged_files = [f['path'] for f in files if f['staged']]

    if not staged_files:
        print("No staged files to generate message for")
        return

    print(f"Generating commit message for {len(staged_files)} files")

    response = requests.post(
        f"{BASE_URL}/ai/generate/commit-message",
        json={
            "staged_files": staged_files,
            "diff_content": ""
        },
        timeout=30
    )
    print(f"Status Code: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"Generated Message: {data.get('message')}")
    else:
        print(f"Error: {response.text}")

def main():
    print("Testing Godot-Minds Backend Endpoints")
    print(f"Base URL: {BASE_URL}")

    try:
        # Test basic connectivity
        print("\n=== Testing Server Connectivity ===")
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Health Check: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to backend server!")
        print("Please start the server with: cd backend && uvicorn main:app --reload --port 8005")
        return

    # Run tests
    test_git_status()

    # Note: Uncomment these if you want to test staging and AI
    # test_git_add()
    # test_ai_commit_message()

    print("\n=== Tests Complete ===")

if __name__ == "__main__":
    main()
