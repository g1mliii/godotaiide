"""
Watcher router - API endpoints for file watching
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.watcher_service import FileWatcherService
from services.indexer_service import CodeIndexer

router = APIRouter()

# Initialize services
try:
    indexer = CodeIndexer()
    watcher_service = FileWatcherService(indexer)
except Exception as e:
    indexer = None
    watcher_service = None
    print(f"Warning: Could not initialize FileWatcherService: {e}")


class WatchRequest(BaseModel):
    """Request to start watching a directory"""

    path: str


@router.post("/start")
async def start_watching(request: WatchRequest):
    """Start watching a directory for code changes"""
    if watcher_service is None:
        raise HTTPException(status_code=500, detail="Watcher service not initialized")

    try:
        await watcher_service.start_watching(request.path)
        return {
            "status": "success",
            "message": f"Started watching {request.path}",
            "watching": True,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_watching():
    """Stop watching for file changes"""
    if watcher_service is None:
        raise HTTPException(status_code=500, detail="Watcher service not initialized")

    try:
        watcher_service.stop_watching()
        return {"status": "success", "message": "Stopped watching", "watching": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_watcher_status():
    """Get current file watcher status"""
    if watcher_service is None:
        raise HTTPException(status_code=500, detail="Watcher service not initialized")

    try:
        return watcher_service.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
