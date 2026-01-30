"""
Git operations service using GitPython
"""
import git
from git.exc import GitCommandError, InvalidGitRepositoryError
from pathlib import Path
from typing import Optional, List
import time

from models.git_models import (
    FileStatus,
    GitStatusResponse,
    GitDiffResponse,
    Branch,
    CommitInfo
)


class GitService:
    """Service for Git operations"""

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
                for line in status_output.split('\0'):
                    if not line:
                        continue

                    status_code = line[:2]
                    file_path = line[3:]

                    # Parse status codes
                    staged = False
                    status = "??"

                    if status_code[0] != ' ' and status_code[0] != '?':
                        staged = True
                        status = status_code[0]
                    elif status_code[1] != ' ':
                        staged = False
                        status = status_code[1]
                    elif status_code == '??':
                        staged = False
                        status = "??"

                    files.append(FileStatus(
                        path=file_path,
                        status=status,
                        staged=staged
                    ))
        except GitCommandError:
            # Fallback to old method if porcelain fails
            files = self._fetch_status_fallback()

        is_clean = len(files) == 0

        return GitStatusResponse(
            branch=current_branch,
            files=files,
            is_clean=is_clean
        )

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
            files.append(FileStatus(
                path=item.a_path,
                status=status,
                staged=True
            ))

        # Unstaged changes
        unstaged_diff = self.repo.index.diff(None)
        for item in unstaged_diff:
            status = "M" if item.change_type == "M" else item.change_type
            files.append(FileStatus(
                path=item.a_path,
                status=status,
                staged=False
            ))

        # Untracked files
        untracked = self.repo.untracked_files
        for file_path in untracked:
            files.append(FileStatus(
                path=file_path,
                status="??",
                staged=False
            ))

        return files

    def invalidate_cache(self):
        """Invalidate status cache (call after modifications)"""
        self._status_cache = None
        self._status_cache_time = 0

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
            new_content = file_full_path.read_text(encoding="utf-8")
        else:
            # File was deleted
            new_content = ""

        # Get unified diff
        try:
            diff_text = self.repo.git.diff("HEAD", "--", file_path)
        except GitCommandError:
            diff_text = ""

        return GitDiffResponse(
            file_path=file_path,
            original_content=original_content,
            new_content=new_content,
            diff_text=diff_text
        )

    def add_files(self, files: List[str]) -> None:
        """
        Stage files for commit

        Args:
            files: List of file paths to stage
        """
        self.repo.index.add(files)
        self.invalidate_cache()

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
        self.invalidate_cache()
        return commit.hexsha

    def get_branches(self) -> List[Branch]:
        """
        Get list of all branches

        Returns:
            List of Branch objects
        """
        current_branch = self.repo.active_branch.name
        branches = []

        for branch in self.repo.branches:
            branches.append(Branch(
                name=branch.name,
                is_current=(branch.name == current_branch)
            ))

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
        self.invalidate_cache()

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
            commits.append(CommitInfo(
                hash=commit.hexsha,
                short_hash=commit.hexsha[:7],
                message=commit.message.strip(),
                author=f"{commit.author.name} <{commit.author.email}>",
                date=commit.committed_datetime.isoformat()
            ))

        return commits
