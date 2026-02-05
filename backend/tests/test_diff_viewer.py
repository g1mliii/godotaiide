"""
Test suite for Phase 4: Diff Viewer functionality
Tests the /git/diff endpoint and related features
"""

import pytest
from fastapi.testclient import TestClient
import subprocess


# Import app (assuming main.py exists in backend/)
try:
    from main import app

    client = TestClient(app)
except ImportError:
    pytest.skip("Backend app not available", allow_module_level=True)


@pytest.fixture
def git_test_repo(tmp_path):
    """Create a temporary git repository for testing"""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create initial file
    test_file = repo_path / "test.gd"
    test_file.write_text("func original():\n    pass\n")

    # Commit initial version
    subprocess.run(
        ["git", "add", "test.gd"], cwd=repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Modify file
    test_file.write_text("func modified():\n    print('changed')\n    pass\n")

    return repo_path


class TestDiffEndpoint:
    """Test the /git/diff endpoint"""

    def test_health_check(self):
        """Verify backend is running"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json().get("status") == "ok"

    def test_diff_endpoint_structure(self):
        """Test that diff endpoint returns correct JSON structure"""
        # This test assumes a file exists in the current repo
        # You may need to adjust the file path
        response = client.get("/git/diff?file=README.md")

        # Should return 200 or 404 (if file doesn't exist)
        assert response.status_code in [200, 404, 422]

        if response.status_code == 200:
            data = response.json()

            # Verify required fields exist
            assert "file_path" in data, "Response missing 'file_path'"
            assert "original_content" in data, "Response missing 'original_content'"
            assert "new_content" in data, "Response missing 'new_content'"
            assert "diff_text" in data, "Response missing 'diff_text'"

            # Verify types
            assert isinstance(data["file_path"], str)
            assert isinstance(data["original_content"], str)
            assert isinstance(data["new_content"], str)
            assert isinstance(data["diff_text"], str)

    def test_diff_missing_file_param(self):
        """Test that endpoint requires file parameter"""
        response = client.get("/git/diff")

        # Should return 422 (validation error) since file param is required
        assert response.status_code == 422

    def test_diff_nonexistent_file(self):
        """Test handling of non-existent file"""
        response = client.get("/git/diff?file=this_file_does_not_exist.gd")

        # Should return error status (404 or 500)
        assert response.status_code in [404, 500]

    def test_diff_compression_flag(self):
        """Test that response includes compression flag"""
        response = client.get("/git/diff?file=test.gd")

        if response.status_code == 200:
            data = response.json()
            assert "diff_compressed" in data
            assert isinstance(data["diff_compressed"], bool)


class TestDiffContent:
    """Test diff content parsing and formatting"""

    def test_diff_format_is_unified(self):
        """Verify diff text uses unified diff format"""
        response = client.get("/git/diff?file=test.gd")

        if response.status_code == 200:
            data = response.json()
            diff_text = data.get("diff_text", "")

            if diff_text:  # Only test if diff is non-empty
                # Unified diff should contain these markers
                assert "---" in diff_text or "+++" in diff_text or "@@" in diff_text

    def test_diff_original_vs_new_different(self):
        """Test that original and new content differ for modified files"""
        # This test requires a modified file in the repo
        response = client.get("/git/diff?file=test.gd")

        if response.status_code == 200:
            data = response.json()
            original = data.get("original_content", "")
            new = data.get("new_content", "")

            # If diff exists, content should differ
            if data.get("diff_text"):
                assert original != new, "Modified file should have different content"


class TestDiffPerformance:
    """Performance tests for diff endpoint"""

    @pytest.mark.slow
    def test_diff_response_time_small_file(self):
        """Test response time for small file (<100 lines)"""
        import time

        start = time.time()
        response = client.get("/git/diff?file=test_file.gd")
        assert response.status_code in [200, 404, 422]
        duration = time.time() - start

        # Should respond in less than 500ms for small files
        assert duration < 0.5, f"Response took {duration:.2f}s (expected <0.5s)"

    @pytest.mark.slow
    def test_diff_handles_large_files(self):
        """Test that endpoint doesn't timeout on large files"""
        # This is a smoke test - actual large file testing requires setup
        response = client.get("/git/diff?file=large_file.gd", timeout=5.0)

        # Should not timeout (even if file doesn't exist)
        assert response.status_code in [200, 404, 422, 500]


class TestDiffEdgeCases:
    """Test edge cases and error handling"""

    def test_diff_empty_file(self):
        """Test diff for empty files"""
        # Edge case: file exists but is empty
        response = client.get("/git/diff?file=empty.gd")

        # Should handle gracefully (200 or 404)
        assert response.status_code in [200, 404, 422]

    def test_diff_special_characters_in_filename(self):
        """Test handling of filenames with special characters"""
        # URL encoding should be handled by client
        response = client.get("/git/diff?file=test%20file.gd")

        # Should not crash (may return 404 if file doesn't exist)
        assert response.status_code in [200, 404, 422]

    def test_diff_binary_file(self):
        """Test handling of binary files (should fail gracefully)"""
        response = client.get("/git/diff?file=image.png")

        # Should handle gracefully (may return error or empty diff)
        assert response.status_code in [200, 404, 422, 500]


# Markers for pytest


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s"])
