"""
Godot-Minds Backend Server
FastAPI + WebSocket server for AI-powered Godot plugin
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import logging

from config import settings
from routers import git as git_router
from routers import index as index_router
from routers import watcher as watcher_router
from routers import ai as ai_router
from routers import websocket as websocket_router

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Godot-Minds Backend",
    description="AI-powered backend for Godot editor plugin with Git integration",
    version="0.1.0",
    debug=settings.debug
)

# Configure CORS for Godot HTTP requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Godot editor makes local requests
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse(
        content={
            "status": "ok",
            "version": "0.1.0",
            "ai_mode": settings.ai_mode
        }
    )


@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "name": "Godot-Minds Backend",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health"
    }


# Include routers
app.include_router(git_router.router, prefix="/git", tags=["git"])
app.include_router(index_router.router, prefix="/index", tags=["index"])
app.include_router(watcher_router.router, prefix="/watcher", tags=["watcher"])
app.include_router(ai_router.router, prefix="/ai", tags=["ai"])
app.include_router(websocket_router.router, tags=["websocket"])


@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup"""
    logger.info("Starting Godot-Minds backend server...")

    # Start WebSocket cleanup task
    await websocket_router.manager.start_cleanup_task()

    logger.info("Application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources on shutdown"""
    logger.info("Shutting down Godot-Minds backend server...")

    # Close AI service providers
    if hasattr(ai_router, 'ai_service') and ai_router.ai_service:
        await ai_router.ai_service.close()

    # Stop file watcher
    if hasattr(watcher_router, 'watcher_service') and watcher_router.watcher_service:
        watcher_router.watcher_service.stop()

    logger.info("Application shutdown complete")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )
