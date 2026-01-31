"""
Git watcher router - API endpoints for git status watching
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.git_watcher_service import GitWatcherService
from routers.websocket import manager

router = APIRouter()

# Initialize git watcher service
git_watcher_service: Optional[GitWatcherService] = None
try:
    git_watcher_service = GitWatcherService()
except Exception as e:
    print(f"Warning: Could not initialize GitWatcherService: {e}")


class GitWatchRequest(BaseModel):
    """Request to start watching a git repository"""

    path: str


@router.post("/start")
async def start_git_watching(request: GitWatchRequest):
    """Start watching a git repository for status changes"""
    if git_watcher_service is None:
        raise HTTPException(
            status_code=500, detail="Git watcher service not initialized"
        )

    try:
        # Use WebSocket manager's broadcast method
        await git_watcher_service.start_watching(
            request.path, broadcast_callback=manager.broadcast
        )

        return {
            "status": "success",
            "message": f"Started watching git repository: {request.path}",
            "watching": True,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_git_watching():
    """Stop watching for git changes"""
    if git_watcher_service is None:
        raise HTTPException(
            status_code=500, detail="Git watcher service not initialized"
        )

    try:
        git_watcher_service.stop_watching()
        return {
            "status": "success",
            "message": "Stopped watching git repository",
            "watching": False,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_git_watcher_status():
    """Get current git watcher status"""
    if git_watcher_service is None:
        raise HTTPException(
            status_code=500, detail="Git watcher service not initialized"
        )

    try:
        return git_watcher_service.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
