"""
AI router - API endpoints for AI operations
"""

from fastapi import APIRouter, HTTPException
from typing import Optional

from services.ai_service import AIService
from models.ai_models import (
    AIAskRequest,
    AIAskResponse,
    AIChatRequest,
    AIChatResponse,
    AICompleteRequest,
    AICompleteResponse,
    CommitMessageRequest,
    CommitMessageResponse,
)

router = APIRouter()

# Initialize AI service
try:
    ai_service: Optional[AIService] = AIService()
except Exception as e:
    ai_service = None
    print(f"Warning: Could not initialize AIService: {e}")


@router.post("/ask", response_model=AIAskResponse)
async def ask_ai(request: AIAskRequest):
    """Ask AI for code assistance (Cmd+K functionality)"""
    if ai_service is None:
        raise HTTPException(status_code=500, detail="AI service not initialized")

    try:
        result = await ai_service.ask(
            prompt=request.prompt,
            file_path=request.file_path,
            file_content=request.file_content,
            selection=request.selection,
            mode=request.mode,
        )

        return AIAskResponse(
            response=result["response"],
            code=result.get("code"),
            explanation=result.get("explanation"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=AIChatResponse)
async def chat_with_ai(request: AIChatRequest):
    """Chat conversation with AI"""
    if ai_service is None:
        raise HTTPException(status_code=500, detail="AI service not initialized")

    try:
        # Convert Pydantic models to dicts
        history = [msg.dict() for msg in request.history] if request.history else None

        response = await ai_service.chat(
            message=request.message,
            history=history,
            context_files=request.context_files,
            mode=request.mode,
        )

        return AIChatResponse(
            message=response,
            code_blocks=None,  # TODO: Extract code blocks from response
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/complete", response_model=AICompleteResponse)
async def get_completion(request: AICompleteRequest):
    """Get inline code completion"""
    if ai_service is None:
        raise HTTPException(status_code=500, detail="AI service not initialized")

    try:
        completion = await ai_service.complete(
            file_path=request.file_path,
            file_content=request.file_content,
            cursor_line=request.cursor_line,
            cursor_column=request.cursor_column,
            mode=request.mode,
        )

        # Determine if multi-line completion
        multi_line = "\n" in completion

        return AICompleteResponse(completion=completion, multi_line=multi_line)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate/commit-message", response_model=CommitMessageResponse)
async def generate_commit_message(request: CommitMessageRequest):
    """Generate commit message from staged changes"""
    if ai_service is None:
        raise HTTPException(status_code=500, detail="AI service not initialized")

    try:
        message = await ai_service.generate_commit_message(
            staged_files=request.staged_files, diff_content=request.diff_content
        )

        return CommitMessageResponse(message=message, explanation=None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
