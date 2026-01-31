"""
Tool Executor - Handles AI tool calls for Godot editor operations
"""

import json
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)

# Load Godot tools from JSON
_TOOLS_PATH = (
    Path(__file__).parent.parent / "ai_providers" / "tools" / "godot_tools.json"
)
_godot_tools: List[Dict[str, Any]] = []


def load_godot_tools() -> List[Dict[str, Any]]:
    """Load Godot tool definitions from JSON file"""
    global _godot_tools

    if _godot_tools:
        return _godot_tools

    try:
        with open(_TOOLS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            _godot_tools = data.get("tools", [])
            logger.info(f"Loaded {len(_godot_tools)} Godot editor tools")
    except FileNotFoundError:
        logger.warning(f"Godot tools file not found: {_TOOLS_PATH}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Godot tools JSON: {e}")

    return _godot_tools


def get_tools_for_anthropic() -> List[Dict[str, Any]]:
    """Convert tool definitions to Anthropic format"""
    tools = load_godot_tools()
    return [
        {
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["input_schema"],
        }
        for tool in tools
    ]


def get_tools_for_openai() -> List[Dict[str, Any]]:
    """Convert tool definitions to OpenAI function calling format"""
    tools = load_godot_tools()
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in tools
    ]


# Map tool names to editor endpoints
_TOOL_TO_ENDPOINT: Dict[str, tuple[str, str]] = {
    # Node operations
    "godot_create_node": ("POST", "/editor/node/create"),
    "godot_delete_node": ("POST", "/editor/node/delete"),
    "godot_set_property": ("POST", "/editor/property/set"),
    "godot_get_property": ("POST", "/editor/property/get"),
    # Resource operations
    "godot_attach_resource": ("POST", "/editor/resource/attach"),
    "godot_create_resource": ("POST", "/editor/resource/create"),
    # Scene operations
    "godot_get_scene_tree": ("GET", "/editor/scene/tree"),
    "godot_instantiate_scene": ("POST", "/editor/scene/instantiate"),
    "godot_save_scene": ("POST", "/editor/scene/save"),
    # Script operations
    "godot_attach_script": ("POST", "/editor/script/attach"),
    "godot_connect_signal": ("POST", "/editor/signal/connect"),
    # Selection
    "godot_get_selection": ("GET", "/editor/selection"),
    # Undo
    "godot_undo": ("POST", "/editor/undo"),
    # Procedural placement
    "godot_spawn_grid": ("POST", "/editor/spawn/grid"),
    "godot_spawn_random": ("POST", "/editor/spawn/random"),
    "godot_spawn_path": ("POST", "/editor/spawn/path"),
}


class ToolExecutor:
    """Execute AI tool calls by forwarding to editor endpoints"""

    def __init__(self, base_url: str = "http://127.0.0.1:8005"):
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        """Close HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def execute_tool(
        self, tool_name: str, tool_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a tool call by forwarding to the appropriate editor endpoint

        Args:
            tool_name: Name of the tool (e.g., "godot_create_node")
            tool_input: Tool parameters

        Returns:
            Result from the editor endpoint
        """
        if tool_name not in _TOOL_TO_ENDPOINT:
            return {"error": f"Unknown tool: {tool_name}"}

        method, endpoint = _TOOL_TO_ENDPOINT[tool_name]
        url = f"{self.base_url}{endpoint}"

        try:
            client = await self._get_client()

            if method == "GET":
                response = await client.get(url, params=tool_input)
            else:
                response = await client.post(url, json=tool_input)

            response.raise_for_status()
            result = response.json()

            logger.info(f"Tool {tool_name} executed successfully: {result}")
            return result

        except httpx.HTTPStatusError as e:
            error_msg = (
                f"Tool {tool_name} failed: {e.response.status_code} - {e.response.text}"
            )
            logger.error(error_msg)
            return {"error": error_msg}
        except httpx.RequestError as e:
            error_msg = f"Tool {tool_name} request failed: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}

    async def execute_tools(
        self, tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple tool calls in sequence

        Args:
            tool_calls: List of tool call dicts with "name" and "input" keys

        Returns:
            List of results
        """
        results = []
        for call in tool_calls:
            tool_name = call.get("name", "")
            tool_input = call.get("input", {})
            result = await self.execute_tool(tool_name, tool_input)
            results.append(
                {
                    "tool_name": tool_name,
                    "tool_use_id": call.get("id", ""),
                    "result": result,
                }
            )
        return results


# Singleton instance
_tool_executor: Optional[ToolExecutor] = None


def get_tool_executor() -> ToolExecutor:
    """Get singleton tool executor instance"""
    global _tool_executor
    if _tool_executor is None:
        _tool_executor = ToolExecutor()
    return _tool_executor
