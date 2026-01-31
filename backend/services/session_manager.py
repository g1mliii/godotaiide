"""
Session management for delta updates.

Tracks client sessions and caches last-sent git status per client
to enable delta updates that only send changes since last request.
"""

import time
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models.git_models import GitStatusResponse


class SessionManager:
    """Manages client sessions for delta updates with TTL expiration."""

    SESSION_TTL = 300  # 5 minutes
    MAX_SESSIONS = 1000  # Prevent unbounded memory growth

    def __init__(self) -> None:
        self._sessions: Dict[str, dict] = {}

    def get_cached_status(self, client_id: str) -> Optional["GitStatusResponse"]:
        """
        Get cached status for client.

        Args:
            client_id: Unique identifier for the client

        Returns:
            Cached GitStatusResponse or None if expired/missing
        """
        session = self._sessions.get(client_id)
        if not session:
            return None

        if time.time() - session["timestamp"] > self.SESSION_TTL:
            del self._sessions[client_id]
            return None

        return session.get("status")

    def update_cache(self, client_id: str, status: "GitStatusResponse") -> None:
        """
        Update cached status for client.

        Args:
            client_id: Unique identifier for the client
            status: Current git status to cache
        """
        # Cleanup if approaching limit to prevent memory issues
        if len(self._sessions) >= self.MAX_SESSIONS:
            self.cleanup_expired()
            # If still over limit after cleanup, remove oldest sessions
            if len(self._sessions) >= self.MAX_SESSIONS:
                sorted_sessions = sorted(
                    self._sessions.items(), key=lambda x: x[1]["timestamp"]
                )
                # Remove oldest 10%
                to_remove = max(1, len(sorted_sessions) // 10)
                for key, _ in sorted_sessions[:to_remove]:
                    del self._sessions[key]

        self._sessions[client_id] = {"status": status, "timestamp": time.time()}

    def cleanup_expired(self) -> int:
        """
        Remove expired sessions.

        Returns:
            Count of sessions removed
        """
        now = time.time()
        expired = [
            k
            for k, v in self._sessions.items()
            if now - v["timestamp"] > self.SESSION_TTL
        ]
        for key in expired:
            del self._sessions[key]
        return len(expired)

    def get_session_count(self) -> int:
        """Get current number of active sessions."""
        return len(self._sessions)
