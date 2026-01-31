"""
Git status watcher service - monitors git repository for changes
"""

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from pathlib import Path
from typing import Callable, Optional, Awaitable, Any
import asyncio
import concurrent.futures
import logging
import time
from threading import Lock

from services.git_service import GitService

logger = logging.getLogger(__name__)


class GitChangeHandler(FileSystemEventHandler):
    """Handler for git repository changes"""

    def __init__(self, repo_path: Path, debounce_seconds: float = 0.5):
        """
        Initialize the git change handler

        Args:
            repo_path: Path to the git repository root
            debounce_seconds: Seconds to wait before processing changes
        """
        super().__init__()
        self.repo_path = repo_path
        self.git_service = GitService(str(repo_path))
        self.debounce_seconds = debounce_seconds

        # Debouncing state
        self.last_change_time: float = 0
        self.pending_broadcast: bool = False
        self.lock = Lock()
        self._stopped: bool = False  # Flag to prevent broadcasts after stop

        # Callback for broadcasting changes via WebSocket (async)
        self.broadcast_callback: Optional[Callable[[dict], Awaitable[None]]] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Background task for debounced broadcasts
        self._broadcast_task: Optional[concurrent.futures.Future[Any]] = None

    def set_broadcast_callback(
        self, callback: Callable, loop: asyncio.AbstractEventLoop
    ):
        """Set callback function to broadcast git status changes"""
        self.broadcast_callback = callback
        self._loop = loop

    def cancel(self) -> None:
        """Cancel any pending broadcasts and prevent future ones"""
        with self.lock:
            self._stopped = True
            self.pending_broadcast = False
            if self._broadcast_task and not self._broadcast_task.done():
                self._broadcast_task.cancel()

    def on_any_event(self, event: FileSystemEvent):
        """Handle any file system event in the repository"""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Check if this is a git-related change we care about
        if not self._is_git_relevant(file_path):
            return

        # Debounce: only schedule broadcast if enough time has passed
        with self.lock:
            if self._stopped:
                return
            
            current_time = time.time()
            self.last_change_time = current_time
            self.pending_broadcast = True

            # Schedule debounced broadcast
            if self._loop and self.broadcast_callback:
                if self._broadcast_task is None or self._broadcast_task.done():
                    self._broadcast_task = asyncio.run_coroutine_threadsafe(
                        self._debounced_broadcast(), self._loop
                    )

    def _is_git_relevant(self, file_path: Path) -> bool:
        """
        Check if file change is relevant to git status

        Args:
            file_path: Path to the changed file

        Returns:
            True if change affects git status
        """
        try:
            # Check if file is inside the repo
            file_path.relative_to(self.repo_path)
        except ValueError:
            return False

        # Git index changes (.git/index)
        if file_path.name == "index" and file_path.parent.name == ".git":
            return True

        # Working tree files (not in .git directory)
        if ".git" not in file_path.parts:
            # Skip common non-tracked files
            if file_path.suffix in {".pyc", ".pyo", ".swp", ".tmp"}:
                return False
            if file_path.name in {".DS_Store", "Thumbs.db"}:
                return False
            return True

        return False

    async def _debounced_broadcast(self):
        """Wait for debounce period, then broadcast if still pending"""
        await asyncio.sleep(self.debounce_seconds)

        with self.lock:
            if self._stopped or not self.pending_broadcast:
                return

            current_time = time.time()
            time_since_last_change = current_time - self.last_change_time

            # If changes happened during our sleep, wait more
            if time_since_last_change < self.debounce_seconds:
                # Reschedule
                if self._loop and self.broadcast_callback:
                    self._broadcast_task = asyncio.run_coroutine_threadsafe(
                        self._debounced_broadcast(), self._loop
                    )
                return

            # No recent changes, broadcast now
            self.pending_broadcast = False

        # Broadcast outside the lock
        await self._broadcast_git_status()

    async def _broadcast_git_status(self):
        """Fetch current git status and broadcast via WebSocket"""
        if self._stopped or not self.broadcast_callback:
            return

        try:
            # Get current git status
            status = self.git_service.get_status()

            # Convert to dict format for WebSocket
            message = {
                "type": "git_status_update",
                "data": {
                    "branch": status.branch,
                    "files": [
                        {
                            "path": f.path,
                            "status": f.status,
                            "staged": f.staged,
                        }
                        for f in status.files
                    ],
                    "is_clean": status.is_clean,
                },
            }

            await self.broadcast_callback(message)
            logger.info(f"Broadcasted git status update ({len(status.files)} files)")

        except Exception as e:
            logger.error(f"Error broadcasting git status: {e}", exc_info=True)


class GitWatcherService:
    """Service to watch git repository for status changes"""

    def __init__(self):
        """Initialize the git watcher service"""
        self.observer: Optional[Observer] = None
        self.handler: Optional[GitChangeHandler] = None
        self.watching = False
        self.watched_path: Optional[Path] = None

    def __del__(self):
        """Ensure cleanup on garbage collection"""
        self.stop_watching()

    async def start_watching(
        self,
        repo_path: str,
        broadcast_callback: Callable[[dict], Awaitable[None]],
    ) -> None:
        """
        Start watching a git repository for changes

        Args:
            repo_path: Path to the git repository root
            broadcast_callback: Async callback to broadcast status updates
        """
        if self.watching:
            self.stop_watching()

        watch_path = Path(repo_path).resolve()
        if not watch_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")

        git_dir = watch_path / ".git"
        if not git_dir.exists():
            raise ValueError(f"Not a git repository: {repo_path}")

        # Create handler with event loop reference
        self.handler = GitChangeHandler(watch_path)
        self.handler.set_broadcast_callback(
            broadcast_callback, asyncio.get_running_loop()
        )

        # Create observer and start watching
        self.observer = Observer()
        try:
            self.observer.schedule(self.handler, str(watch_path), recursive=True)
            self.observer.start()
        except Exception as e:
            # Clean up on error to prevent resource leaks
            self.observer = None
            self.handler = None
            raise

        self.watching = True
        self.watched_path = watch_path
        logger.info(f"Started watching git repository: {watch_path}")

    def stop_watching(self) -> None:
        """Stop watching for git changes"""
        # Cancel pending broadcasts first
        if self.handler:
            self.handler.cancel()
        
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join(timeout=5)
            except Exception as e:
                logger.warning(f"Error stopping observer: {e}")
            finally:
                self.observer = None
        
        self.handler = None
        self.watching = False
        logger.info("Stopped watching git repository")

    def get_status(self) -> dict:
        """Get current watcher status"""
        return {
            "watching": self.watching,
            "path": str(self.watched_path) if self.watched_path else None,
        }
