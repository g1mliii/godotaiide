"""
Git operations service using GitPython
"""

import git
from git.exc import GitCommandError, InvalidGitRepositoryError
from pathlib import Path
from typing import Optional, List
import time
import gzip
import base64

from models.git_models import (
    FileStatus,
    GitStatusResponse,
    GitDiffResponse,
    Branch,
    CommitInfo,
)


class GitService:
    """Service for Git operations"""

    # Safety limits
    MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit for file reads
    DIFF_COMPRESSION_THRESHOLD = 50 * 1024  # Compress diffs larger than 50KB

    def __init__(self, repo_path: str = "."):
        """
        Initialize Git service

        Args:
            repo_path: Path to the Git repository (default: current directory)
        """
        self.repo_path = Path(repo_path).resolve()
        try:
            self.repo = git.Repo(self.repo_path)
        except InvalidGitRepositoryError:
            raise ValueError(f"Not a Git repository: {self.repo_path}")

        # Status caching to reduce redundant git operations
        self._status_cache: Optional[GitStatusResponse] = None
        self._status_cache_time: float = 0
        self._cache_ttl: float = 2.0  # 2 second TTL

    def get_status(self) -> GitStatusResponse:
        """
        Get current working tree status with caching

        Returns:
            GitStatusResponse with branch and file changes
        """
        now = time.time()
        if self._status_cache and (now - self._status_cache_time) < self._cache_ttl:
            return self._status_cache

        # Cache miss, fetch fresh status
        status = self._fetch_status()
        self._status_cache = status
        self._status_cache_time = now
        return status

    def _fetch_status(self) -> GitStatusResponse:
        """
        Actually fetch status from git (optimized with batched operations)

        Returns:
            GitStatusResponse with branch and file changes
        """
        # Get current branch
        try:
            current_branch = self.repo.active_branch.name
        except TypeError:
            # Detached HEAD state
            current_branch = "HEAD (detached)"

        # Use single git status call instead of 3 separate commands
        files: List[FileStatus] = []
        try:
            # Get status in porcelain format for faster parsing
            status_output = self.repo.git.status("--porcelain=v1", "-z")

            if status_output:
                # Split by null character
                for line in status_output.split("\0"):
                    if not line:
                        continue

                    status_code = line[:2]
                    file_path = line[3:]

                    # Parse status codes (index vs working tree)
                    # status_code[0] = staging area (index)
                    # status_code[1] = working tree

                    # Add staged changes (if any)
                    if status_code[0] != " " and status_code[0] != "?":
                        files.append(
                            FileStatus(path=file_path, status=status_code[0], staged=True)
                        )

                    # Add unstaged changes (if any)
                    if status_code[1] != " ":
                        files.append(
                            FileStatus(path=file_path, status=status_code[1], staged=False)
                        )
                    elif status_code == "??":
                        # Untracked files
                        files.append(
                            FileStatus(path=file_path, status="??", staged=False)
                        )
        except GitCommandError:
            # Fallback to old method if porcelain fails
            files = self._fetch_status_fallback()

        is_clean = len(files) == 0

        return GitStatusResponse(branch=current_branch, files=files, is_clean=is_clean)

    def _fetch_status_fallback(self) -> List[FileStatus]:
        """
        Fallback method using GitPython API (original implementation)

        Returns:
            List of FileStatus objects
        """
        files: List[FileStatus] = []

        # Staged files
        staged_diff = self.repo.index.diff("HEAD")
        for item in staged_diff:
            status = "M" if item.change_type == "M" else item.change_type
            files.append(FileStatus(path=item.a_path, status=status, staged=True))

        # Unstaged changes
        unstaged_diff = self.repo.index.diff(None)
        for item in unstaged_diff:
            status = "M" if item.change_type == "M" else item.change_type
            files.append(FileStatus(path=item.a_path, status=status, staged=False))

        # Untracked files
        untracked = self.repo.untracked_files
        for file_path in untracked:
            files.append(FileStatus(path=file_path, status="??", staged=False))

        return files

    def invalidate_cache(self, operation: str = "unknown"):
        """
        Invalidate status cache based on operation type (delta-based invalidation)

        Args:
            operation: The git operation performed (add, commit, checkout, etc.)
        """
        # Only operations that change working tree status need cache invalidation
        status_changing_ops = {
            "add",
            "commit",
            "restore",
            "checkout",
            "reset",
            "revert",
        }

        if operation in status_changing_ops or operation == "unknown":
            self._status_cache = None
            self._status_cache_time = 0
        # Operations like log, branches, diff don't affect status - keep cache

    def get_diff(self, file_path: str) -> GitDiffResponse:
        """
        Get diff for a specific file

        Args:
            file_path: Path to the file

        Returns:
            GitDiffResponse with original and new content
        """
        # Get HEAD version (original)
        try:
            original_content = self.repo.git.show(f"HEAD:{file_path}")
        except GitCommandError:
            # File is new (not in HEAD)
            original_content = ""

        # Get working directory version (new)
        file_full_path = self.repo_path / file_path
        if file_full_path.exists():
            # Check file size before reading to prevent OOM
            file_size = file_full_path.stat().st_size
            if file_size > self.MAX_FILE_SIZE_BYTES:
                raise ValueError(
                    f"File too large: {file_path} ({file_size} bytes, max {self.MAX_FILE_SIZE_BYTES})"
                )
            try:
                new_content = file_full_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Binary file - don't try to read as text
                new_content = "[Binary file - cannot display content]"
        else:
            # File was deleted
            new_content = ""

        # Get unified diff
        try:
            diff_text = self.repo.git.diff("HEAD", "--", file_path)
        except GitCommandError:
            diff_text = ""

        # Compress large diffs to save bandwidth
        diff_compressed = False
        diff_size = len(diff_text.encode("utf-8"))

        if diff_size > self.DIFF_COMPRESSION_THRESHOLD:
            # Compress with gzip and base64 encode
            compressed_bytes = gzip.compress(diff_text.encode("utf-8"))
            diff_text = base64.b64encode(compressed_bytes).decode("ascii")
            diff_compressed = True

        return GitDiffResponse(
            file_path=file_path,
            original_content=original_content,
            new_content=new_content,
            diff_text=diff_text,
            diff_compressed=(
                diff_compressed if diff_compressed else None
            ),  # Optional field
        )

    def add_files(self, files: List[str]) -> None:
        """
        Stage files for commit

        Args:
            files: List of file paths to stage
        """
        self.repo.index.add(files)
        self.invalidate_cache("add")

    def unstage_files(self, files: List[str]) -> None:
        """
        Unstage files (git restore --staged) - batched for performance

        Args:
            files: List of file paths to unstage
        """
        if not files:
            return

        # Batch operation - pass all files at once instead of looping
        self.repo.git.restore("--staged", *files)
        self.invalidate_cache("restore")

    def commit(self, message: str, files: Optional[List[str]] = None) -> str:
        """
        Create a commit

        Args:
            message: Commit message
            files: Optional list of files to commit (if None, commits all staged)

        Returns:
            Commit hash
        """
        if files:
            self.repo.index.add(files)

        commit = self.repo.index.commit(message)
        self.invalidate_cache("commit")
        return commit.hexsha

    def get_branches(self) -> List[Branch]:
        """
        Get list of all branches

        Returns:
            List of Branch objects
        """
        current_branch = self.repo.active_branch.name
        branches = []

        for branch in self.repo.branches:  # type: ignore[attr-defined]
            branches.append(
                Branch(name=branch.name, is_current=(branch.name == current_branch))
            )

        return branches

    def checkout(self, branch_name: str, create_new: bool = False) -> None:
        """
        Checkout a branch

        Args:
            branch_name: Name of the branch
            create_new: If True, create a new branch
        """
        if create_new:
            self.repo.create_head(branch_name)

        self.repo.git.checkout(branch_name)
        self.invalidate_cache("checkout")

    def get_log(self, max_count: int = 20) -> List[CommitInfo]:
        """
        Get commit history

        Args:
            max_count: Maximum number of commits to return

        Returns:
            List of CommitInfo objects
        """
        commits = []
        for commit in self.repo.iter_commits(max_count=max_count):
            commits.append(
                CommitInfo(
                    hash=commit.hexsha,
                    short_hash=commit.hexsha[:7],
                    message=str(commit.message).strip(),
                    author=f"{commit.author.name} <{commit.author.email}>",
                    date=commit.committed_datetime.isoformat(),
                )
            )

        return commits
