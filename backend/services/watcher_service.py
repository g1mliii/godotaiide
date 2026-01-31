"""
File watcher service using Watchdog to monitor code changes
"""

from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
)
from pathlib import Path
from typing import Callable, Optional, Awaitable
import time
import threading
import asyncio
import logging
from collections import OrderedDict
from datetime import datetime

from config import settings
from services.indexer_service import CodeIndexer

logger = logging.getLogger(__name__)


class CodeFileHandler(FileSystemEventHandler):
    """Handler for code file changes"""

    def __init__(self, indexer: CodeIndexer, debounce_seconds: float = 0.5):
        """
        Initialize the file handler

        Args:
            indexer: CodeIndexer instance to update
            debounce_seconds: Seconds to wait before processing changes
        """
        super().__init__()
        self.indexer = indexer
        self.debounce_seconds = debounce_seconds

        # Track pending changes with timestamps (bounded with LRU eviction)
        self.pending_changes: OrderedDict[str, float] = OrderedDict()
        self.max_pending = 1000  # Limit to prevent unbounded growth
        self.lock = threading.Lock()
        self.change_event = threading.Event()

        # Callback for broadcasting changes via WebSocket (async)
        self.broadcast_callback: Optional[Callable[[dict], Awaitable[None]]] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Start debounce processor thread
        self.running = True
        self.processor_thread = threading.Thread(
            target=self._process_pending_changes, daemon=True
        )
        self.processor_thread.start()

    def set_broadcast_callback(self, callback: Callable):
        """Set callback function to broadcast file changes"""
        self.broadcast_callback = callback

    def on_modified(self, event):
        """Handle file modification events"""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if self._should_process_file(file_path):
            self._add_pending_change(str(file_path))

    def on_created(self, event):
        """Handle file creation events"""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if self._should_process_file(file_path):
            self._add_pending_change(str(file_path))

    def on_deleted(self, event):
        """Handle file deletion events"""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if self._should_process_file(file_path):
            # Find project root (simplified for this implementation)
            project_root = file_path.parent
            while project_root.parent != project_root:
                if (project_root / ".git").exists():
                    break
                project_root = project_root.parent

            self.indexer.remove_file(file_path, project_root)

    def _should_process_file(self, file_path: Path) -> bool:
        """
        Check if file should be processed

        Args:
            file_path: Path to the file

        Returns:
            True if file should be processed
        """
        # Check extension
        if file_path.suffix not in settings.watch_extensions:
            return False

        # Check ignored directories
        for ignored in settings.ignore_directories:
            if ignored in file_path.parts:
                return False

        return True

    def _add_pending_change(self, file_path: str):
        """
        Add change with LRU eviction

        Args:
            file_path: Path to file
        """
        with self.lock:
            if file_path in self.pending_changes:
                # Move to end (most recent)
                self.pending_changes.move_to_end(file_path)
                self.pending_changes[file_path] = time.time()
            else:
                # Add new
                self.pending_changes[file_path] = time.time()
                self.change_event.set()

                # Evict oldest if over limit
                if len(self.pending_changes) > self.max_pending:
                    oldest_file, _ = self.pending_changes.popitem(last=False)
                    logger.warning(f"Evicted oldest pending change: {oldest_file}")

    def _process_pending_changes(self):
        """Background thread to process pending changes with debouncing"""
        while self.running:
            # Wait for changes or timeout (to allow checking self.running)
            # using a timeout allows us to check self.running periodically even if no events
            if not self.pending_changes:
                self.change_event.wait(timeout=1.0)
                if not self.running:
                    break
                self.change_event.clear()
            else:
                time.sleep(
                    0.1
                )  # Check every 100ms when we have pending changes for debounce

            current_time = time.time()
            files_to_process = []

            with self.lock:
                # Find files that have been pending long enough
                for file_path, timestamp in list(self.pending_changes.items()):
                    if current_time - timestamp >= self.debounce_seconds:
                        files_to_process.append(file_path)
                        del self.pending_changes[file_path]

            # Process files outside the lock
            for file_path in files_to_process:
                self._reindex_file(file_path)

    def _reindex_file(self, file_path: str):
        """
        Reindex a single file (runs in background thread)

        Args:
            file_path: Path to the file to reindex
        """
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"File no longer exists: {file_path}")
                return

            # Get project root (assuming we're watching from project root)
            # This is simplified - in production you'd track the watched directory
            project_root = path.parent
            while project_root.parent != project_root:
                if (project_root / ".git").exists():
                    break
                project_root = project_root.parent

            # Reindex the file
            chunks = self.indexer._chunk_file(path, project_root)
            if not chunks:
                return

            self.indexer._add_chunks_to_index(chunks)
            logger.info(f"Reindexed: {file_path} ({len(chunks)} chunks)")

            # Broadcast change via WebSocket if callback is set
            if not (self.broadcast_callback and self._loop):
                return

            message = {
                "type": "file_indexed",
                "path": str(path.relative_to(project_root)),
                "chunks": len(chunks),
                "timestamp": datetime.now().isoformat(),
            }
            # Schedule the coroutine in the event loop
            asyncio.run_coroutine_threadsafe(
                self.broadcast_callback(message), self._loop
            )

        except Exception as e:
            logger.error(f"Error reindexing {file_path}: {e}", exc_info=True)

    def stop(self):
        """Stop the processor thread"""
        if self.running:
            self.running = False
            self.change_event.set()  # Wake up thread so it can exit
            if self.processor_thread and self.processor_thread.is_alive():
                self.processor_thread.join(timeout=5)
                if self.processor_thread.is_alive():
                    logger.warning("Processor thread did not stop cleanly")

    def __del__(self):
        """Ensure cleanup on garbage collection"""
        try:
            self.stop()
        except Exception:
            pass  # Ignore errors during cleanup


class FileWatcherService:
    """Service to watch file system for code changes"""

    def __init__(self, indexer: CodeIndexer):
        """
        Initialize the file watcher

        Args:
            indexer: CodeIndexer instance to update on changes
        """
        self.indexer = indexer
        self.observer = Observer()
        self.handler = CodeFileHandler(indexer)
        self.watching = False
        self.watched_path: Optional[Path] = None

    async def start_watching(
        self, path: str, callback: Optional[Callable] = None
    ) -> None:
        """
        Start watching a directory for changes

        Args:
            path: Path to the directory to watch
            callback: Optional async callback for broadcasts
        """
        if self.watching:
            self.stop_watching()

        watch_path = Path(path).resolve()
        if not watch_path.exists():
            raise ValueError(f"Path does not exist: {path}")

        # Create a new Observer instance (observers can't be restarted after stop)
        self.observer = Observer()

        # Store event loop reference for async callback
        self.handler._loop = asyncio.get_running_loop()

        # Set broadcast callback if provided
        if callback:
            self.set_broadcast_callback(callback)

        self.watched_path = watch_path
        self.observer.schedule(self.handler, str(watch_path), recursive=True)
        self.observer.start()
        self.watching = True
        logger.info(f"Started watching: {watch_path}")

    def stop_watching(self) -> None:
        """Stop watching for file changes"""
        if self.watching:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.handler.stop()
            self.watching = False
            logger.info("Stopped watching")

    def stop(self) -> None:
        """Stop the watcher service (for shutdown)"""
        self.stop_watching()

    def set_broadcast_callback(self, callback: Callable):
        """Set callback to broadcast file changes via WebSocket"""
        self.handler.set_broadcast_callback(callback)

    def get_status(self) -> dict:
        """Get current watcher status"""
        return {
            "watching": self.watching,
            "path": str(self.watched_path) if self.watched_path else None,
            "extensions": settings.watch_extensions,
            "ignored_directories": settings.ignore_directories,
        }
