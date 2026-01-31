"""
Git router - API endpoints for Git operations
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Union
import asyncio

from services.git_service import GitService
from services.session_manager import SessionManager
from models.git_models import (
    GitStatusResponse,
    GitDeltaResponse,
    GitDiffResponse,
    GitAddRequest,
    GitRestoreRequest,
    GitCommitRequest,
    GitBranchesResponse,
    GitCheckoutRequest,
    GitLogResponse,
)

router = APIRouter()

# Initialize session manager for delta updates
session_manager = SessionManager()


# Initialize Git service from parent directory (project root)
# The backend is in a subdirectory, so we need to go up one level
try:
    git_service: Optional[GitService] = GitService("..")
except ValueError as e:
    git_service = None
    print(f"Warning: {e}")


@router.get("/status", response_model=Union[GitStatusResponse, GitDeltaResponse])
async def get_status(
    client_id: Optional[str] = Query(None, description="Client ID for delta updates")
):
    """Get working tree status with file changes.

    If client_id is provided, returns delta since last request.
    Otherwise returns full status.
    """
    if git_service is None:
        raise HTTPException(status_code=500, detail="Git repository not initialized")

    try:
        status = await asyncio.to_thread(git_service.get_status)

        # If client_id provided, return delta
        if client_id:
            previous = session_manager.get_cached_status(client_id)
            session_manager.update_cache(client_id, status)

            if previous:
                # Calculate and return delta
                return git_service.calculate_delta(status, previous)
            else:
                # First request or session expired - return full status as delta format
                return GitDeltaResponse(
                    branch=status.branch,
                    added=status.files,
                    removed=[],
                    changed=[],
                    unchanged_count=0,
                    is_full_refresh=True,
                )

        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diff", response_model=GitDiffResponse)
async def get_diff(file: str = Query(..., description="File path to get diff for")):
    """Get diff for a specific file"""
    if git_service is None:
        raise HTTPException(status_code=500, detail="Git repository not initialized")

    try:
        diff = await asyncio.to_thread(git_service.get_diff, file)
        return diff
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add")
async def add_files(request: GitAddRequest):
    """Stage files for commit"""
    if git_service is None:
        raise HTTPException(status_code=500, detail="Git repository not initialized")

    try:
        await asyncio.to_thread(git_service.add_files, request.files)
        return {"success": True, "message": f"Staged {len(request.files)} file(s)"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restore")
async def restore_files(request: GitRestoreRequest):
    """Unstage files (git restore --staged)"""
    if git_service is None:
        raise HTTPException(status_code=500, detail="Git repository not initialized")

    try:
        await asyncio.to_thread(git_service.unstage_files, request.files)
        return {"success": True, "message": f"Unstaged {len(request.files)} file(s)"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commit")
async def create_commit(request: GitCommitRequest):
    """Create a commit"""
    if git_service is None:
        raise HTTPException(status_code=500, detail="Git repository not initialized")

    try:
        commit_hash = await asyncio.to_thread(
            git_service.commit, request.message, request.files
        )
        return {"success": True, "message": commit_hash, "commit_hash": commit_hash}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/branches", response_model=GitBranchesResponse)
async def get_branches():
    """Get list of all branches"""
    if git_service is None:
        raise HTTPException(status_code=500, detail="Git repository not initialized")

    try:
        branches = await asyncio.to_thread(git_service.get_branches)
        current_branch = next((b.name for b in branches if b.is_current), "")
        return GitBranchesResponse(branches=branches, current_branch=current_branch)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/checkout")
async def checkout_branch(request: GitCheckoutRequest):
    """Checkout a branch"""
    if git_service is None:
        raise HTTPException(status_code=500, detail="Git repository not initialized")

    try:
        await asyncio.to_thread(
            git_service.checkout, request.branch, request.create_new
        )
        return {
            "success": True,
            "message": f"Checked out branch: {request.branch}",
            "branch": request.branch,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/log", response_model=GitLogResponse)
async def get_log(max_count: int = Query(20, ge=1, le=100)):
    """Get commit history"""
    if git_service is None:
        raise HTTPException(status_code=500, detail="Git repository not initialized")

    try:
        commits = await asyncio.to_thread(git_service.get_log, max_count)
        return GitLogResponse(commits=commits)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
