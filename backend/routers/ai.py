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
    AIEditorCommandRequest,
    AIEditorCommandResponse,
    ToolResult,
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


@router.post("/editor/command", response_model=AIEditorCommandResponse)
async def execute_editor_command(request: AIEditorCommandRequest):
    """
    Execute AI-driven editor commands with tool calling.

    The AI will analyze the prompt and use tools to manipulate the Godot editor:
    - Create nodes, set properties
    - Attach resources and scripts
    - Spawn grids, scatter objects, place along paths

    Example prompts:
    - "Create a 10x10 floor grid using MeshInstance3D"
    - "Scatter 50 trees randomly in the forest area"
    - "Add a Camera3D as a child of the Player node"
    """
    if ai_service is None:
        raise HTTPException(status_code=500, detail="AI service not initialized")

    try:
        from ai_providers.direct_api import DirectAPIProvider

        # Get the provider (must be direct API for tool calling)
        provider = ai_service._get_provider(request.mode)

        if not isinstance(provider, DirectAPIProvider):
            raise HTTPException(
                status_code=400,
                detail="Tool calling requires direct API mode (Claude or GPT)",
            )

        # Build system prompt for Godot editor context
        system_prompt = """You are an AI assistant that helps build Godot game levels.
You have access to tools to directly manipulate the Godot editor.

When the user asks you to create, modify, or arrange nodes:
1. Use the appropriate tools to make the changes
2. Use godot_get_scene_tree first if you need to understand the current scene structure
3. For grids, use godot_spawn_grid
4. For random scattering, use godot_spawn_random
5. For path-based placement, use godot_spawn_path
6. For individual nodes, use godot_create_node

Always confirm what you've done after completing the task."""

        result = await provider.ask_with_tools(
            prompt=request.prompt,
            context=request.context,
            system_prompt=system_prompt,
        )

        # Convert tool results to Pydantic models
        tool_results = [
            ToolResult(tool=tr["tool"], input=tr["input"], result=tr["result"])
            for tr in result.get("tool_results", [])
        ]

        return AIEditorCommandResponse(
            response=result.get("response", ""), tool_results=tool_results
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# AUTH ENDPOINTS (OpenCode Subscription)
# =============================================================================


@router.get("/auth/status")
async def get_auth_status():
    """
    Get authentication status for OpenCode subscription providers.

    Returns which AI backends (Claude, ChatGPT, Copilot) are authenticated.
    """
    try:
        from ai_providers.opencode import OpenCodeProvider

        provider = OpenCodeProvider()
        status = await provider.get_auth_status()
        return {
            "opencode_available": True,
            "providers": status,
        }
    except ValueError as e:
        # OpenCode not installed
        return {
            "opencode_available": False,
            "providers": {"claude": False, "chatgpt": False, "copilot": False},
            "error": str(e),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auth/connect/{provider}")
async def connect_provider(provider: str):
    """
    Trigger OAuth authentication for an OpenCode provider.

    Args:
        provider: Provider to authenticate ('claude', 'chatgpt', 'copilot')

    Returns:
        Status message - auth will complete in browser
    """
    if provider not in ["claude", "chatgpt", "copilot"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider: {provider}. Use 'claude', 'chatgpt', or 'copilot'",
        )

    try:
        from ai_providers.opencode import OpenCodeProvider

        opencode = OpenCodeProvider()
        result = await opencode.trigger_auth(provider)

        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])

        return result

    except ValueError as e:
        raise HTTPException(status_code=503, detail=f"OpenCode not available: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
