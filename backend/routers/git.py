"""
Git router - API endpoints for Git operations
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List
import asyncio

from services.git_service import GitService
from models.git_models import (
    GitStatusResponse,
    GitDiffResponse,
    GitAddRequest,
    GitCommitRequest,
    GitCommitResponse,
    GitBranchesResponse,
    GitCheckoutRequest,
    GitLogResponse
)

router = APIRouter()

# Initialize Git service from parent directory (project root)
# The backend is in a subdirectory, so we need to go up one level
try:
    git_service = GitService("..")
except ValueError as e:
    git_service = None
    print(f"Warning: {e}")


@router.get("/status", response_model=GitStatusResponse)
async def get_status():
    """Get working tree status with file changes"""
    if git_service is None:
        raise HTTPException(status_code=500, detail="Git repository not initialized")

    try:
        status = await asyncio.to_thread(git_service.get_status)
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
        return {"status": "ok", "message": f"Staged {len(request.files)} file(s)"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commit", response_model=GitCommitResponse)
async def create_commit(request: GitCommitRequest):
    """Create a commit"""
    if git_service is None:
        raise HTTPException(status_code=500, detail="Git repository not initialized")

    try:
        commit_hash = await asyncio.to_thread(git_service.commit, request.message, request.files)
        return GitCommitResponse(
            commit_hash=commit_hash,
            message=request.message
        )
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
        return GitBranchesResponse(
            branches=branches,
            current_branch=current_branch
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/checkout")
async def checkout_branch(request: GitCheckoutRequest):
    """Checkout a branch"""
    if git_service is None:
        raise HTTPException(status_code=500, detail="Git repository not initialized")

    try:
        await asyncio.to_thread(git_service.checkout, request.branch, request.create_new)
        return {"status": "ok", "branch": request.branch}
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
