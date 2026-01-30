"""
WebSocket router - Real-time communication for streaming AI and file changes
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set, Optional
import asyncio
import time
import logging

from services.ai_service import AIService

logger = logging.getLogger(__name__)

router = APIRouter()

# Active WebSocket connections
active_connections: Set[WebSocket] = set()

# Initialize AI service for streaming
try:
    ai_service: Optional[AIService] = AIService()
except Exception as e:
    ai_service = None
    print(f"Warning: Could not initialize AIService for WebSocket: {e}")


class ConnectionManager:
    """Manage WebSocket connections with automatic cleanup"""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()
        self._connection_last_seen: Dict[WebSocket, float] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._connection_timeout = 300  # 5 minute timeout
        self._shutdown = False

    async def start_cleanup_task(self) -> None:
        """Start background task to cleanup stale connections"""
        self._shutdown = False
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self) -> None:
        """Stop the cleanup task gracefully"""
        self._shutdown = True
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self):
        """Background loop to cleanup stale connections"""
        while not self._shutdown:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                if self._shutdown:
                    break
                now = time.time()
                stale = [
                    ws
                    for ws, last_seen in self._connection_last_seen.items()
                    if now - last_seen > self._connection_timeout
                ]
                for ws in stale:
                    logger.warning(
                        f"Cleaning up stale WebSocket connection (idle {int(now - self._connection_last_seen[ws])}s)"
                    )
                    self.disconnect(ws)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in WebSocket cleanup loop: {e}", exc_info=True)

    async def connect(self, websocket: WebSocket):
        """Accept and add new connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        self.update_last_seen(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove connection"""
        self.active_connections.discard(websocket)
        self._connection_last_seen.pop(websocket, None)

    def update_last_seen(self, websocket: WebSocket):
        """Update last activity timestamp for connection"""
        self._connection_last_seen[websocket] = time.time()

    async def send_message(self, websocket: WebSocket, message: Dict):
        """Send message to a specific connection"""
        try:
            await websocket.send_json(message)
            self.update_last_seen(websocket)
        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: Dict):
        """Broadcast message to all connections concurrently"""
        if not self.active_connections:
            return

        # Send to all connections in parallel
        await asyncio.gather(
            *[self.send_message(ws, message) for ws in self.active_connections.copy()],
            return_exceptions=True,
        )


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time communication

    Message types:
    - ai_stream: Streaming AI response
    - file_changed: File modification notification
    - completion_suggestion: Inline completion suggestion
    """
    await manager.connect(websocket)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            manager.update_last_seen(websocket)

            message_type = data.get("type")

            if message_type == "ai_ask":
                # Stream AI response
                await handle_ai_stream(websocket, data)

            elif message_type == "completion":
                # Get inline completion
                await handle_completion(websocket, data)

            elif message_type == "ping":
                # Heartbeat
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Unknown message type: {message_type}",
                    }
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def handle_ai_stream(websocket: WebSocket, data: Dict):
    """Handle streaming AI request"""
    if ai_service is None:
        await websocket.send_json(
            {"type": "error", "message": "AI service not initialized"}
        )
        return

    try:
        prompt = data.get("prompt", "")
        context = data.get("context")

        # Get provider and stream response
        provider = ai_service._get_provider()

        await websocket.send_json(
            {"type": "ai_stream_start", "message": "Starting AI response..."}
        )

        # Stream tokens
        full_response = ""
        async for token in provider.stream_response(prompt, context):
            full_response += token
            await websocket.send_json(
                {"type": "ai_stream", "token": token, "accumulated": full_response}
            )

        await websocket.send_json(
            {"type": "ai_stream_end", "full_response": full_response}
        )

    except Exception as e:
        await websocket.send_json(
            {"type": "error", "message": f"AI streaming failed: {str(e)}"}
        )


async def handle_completion(websocket: WebSocket, data: Dict):
    """Handle inline completion request"""
    if ai_service is None:
        await websocket.send_json(
            {"type": "error", "message": "AI service not initialized"}
        )
        return

    try:
        file_path = data.get("file_path", "")
        file_content = data.get("file_content", "")
        cursor_line = data.get("cursor_line", 0)
        cursor_column = data.get("cursor_column", 0)

        completion = await ai_service.complete(
            file_path=file_path,
            file_content=file_content,
            cursor_line=cursor_line,
            cursor_column=cursor_column,
        )

        await websocket.send_json(
            {
                "type": "completion_suggestion",
                "completion": completion,
                "multi_line": "\n" in completion,
            }
        )

    except Exception as e:
        await websocket.send_json(
            {"type": "error", "message": f"Completion failed: {str(e)}"}
        )


async def broadcast_file_change(file_path: str, chunks_updated: int):
    """
    Broadcast file change notification to all connected clients

    This can be called by the file watcher service
    """
    await manager.broadcast(
        {
            "type": "file_changed",
            "file_path": file_path,
            "chunks_updated": chunks_updated,
        }
    )


# Export function to be used by watcher service
def get_broadcast_callback():
    """Get callback function for file watcher to broadcast changes"""

    async def callback(data: Dict):
        await manager.broadcast(data)

    return callback
