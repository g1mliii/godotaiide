"""
Editor Router - Exposes Godot editor capabilities as REST endpoints.
Commands are forwarded to the Godot plugin via WebSocket.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Optional
import asyncio

router = APIRouter(prefix="/editor", tags=["editor"])

# Reference to the active Godot WebSocket connection
# This will be set by the websocket router when Godot connects
_godot_connection = None
_pending_requests: dict[str, asyncio.Future] = {}
_request_counter = 0
_MAX_REQUEST_COUNTER = 1_000_000  # Reset counter to prevent overflow


def set_godot_connection(ws) -> None:
    """Called by websocket router when Godot connects."""
    global _godot_connection
    _godot_connection = ws


def clear_godot_connection() -> None:
    """Called by websocket router when Godot disconnects."""
    global _godot_connection
    _godot_connection = None
    # Cancel any pending requests since Godot disconnected
    for future in _pending_requests.values():
        if not future.done():
            future.cancel()
    _pending_requests.clear()


async def send_to_godot(action: str, data: dict, timeout: float = 10.0) -> dict:
    """Forward a request to Godot plugin and await response."""
    global _request_counter

    if not _godot_connection:
        raise HTTPException(status_code=503, detail="Godot not connected")

    # Create unique request ID with overflow protection
    _request_counter = (_request_counter + 1) % _MAX_REQUEST_COUNTER
    request_id = f"req_{_request_counter}"

    # Create future for response using running loop (not deprecated)
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    _pending_requests[request_id] = future

    try:
        # Send request to Godot
        await _godot_connection.send_json(
            {
                "type": "editor_action",
                "request_id": request_id,
                "action": action,
                "data": data,
            }
        )

        # Wait for response with timeout
        result = await asyncio.wait_for(future, timeout=timeout)
        return result

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Godot request timed out")
    except asyncio.CancelledError:
        raise HTTPException(
            status_code=503, detail="Request cancelled - Godot disconnected"
        )
    finally:
        _pending_requests.pop(request_id, None)


def handle_godot_response(request_id: str, result: dict) -> None:
    """Called when Godot sends a response to a pending request."""
    future = _pending_requests.get(request_id)
    if future and not future.done():
        future.set_result(result)


# =============================================================================
# REQUEST MODELS
# =============================================================================


class CreateNodeRequest(BaseModel):
    parent_path: str = Field(..., description="Path to parent node, e.g. '/root/Level'")
    node_class: str = Field(..., description="Godot class name, e.g. 'CharacterBody3D'")
    node_name: str = Field(..., description="Name for the new node")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Initial properties"
    )


class DeleteNodeRequest(BaseModel):
    node_path: str = Field(..., description="Path to node to delete")


class RenameNodeRequest(BaseModel):
    node_path: str = Field(..., description="Path to node to rename")
    new_name: str = Field(..., description="New name for the node")


class ReparentNodeRequest(BaseModel):
    node_path: str = Field(..., description="Path to node to reparent")
    new_parent_path: str = Field(..., description="Path to new parent node")


class GetPropertyRequest(BaseModel):
    node_path: str
    property: str


class SetPropertyRequest(BaseModel):
    node_path: str = Field(..., description="Path to node")
    property: str = Field(..., description="Property name")
    value: Any = Field(..., description="Value to set")


class AttachResourceRequest(BaseModel):
    node_path: str = Field(..., description="Path to node")
    property: str = Field(..., description="Property to set, e.g. 'mesh', 'material'")
    resource_path: str = Field(
        ..., description="Resource path, e.g. 'res://models/player.glb'"
    )


class CreateResourceRequest(BaseModel):
    resource_type: str = Field(
        ..., description="Resource class, e.g. 'StandardMaterial3D'"
    )
    properties: dict[str, Any] = Field(default_factory=dict)
    save_path: str = Field(
        ..., description="Path to save, e.g. 'res://materials/red.tres'"
    )


class InstantiateSceneRequest(BaseModel):
    parent_path: str = Field(..., description="Path to parent node")
    scene_path: str = Field(
        ..., description="Scene path, e.g. 'res://prefabs/enemy.tscn'"
    )
    instance_name: str = Field(..., description="Name for the instance")


class AttachScriptRequest(BaseModel):
    node_path: str = Field(..., description="Path to node")
    script_path: str = Field(
        ..., description="Script path, e.g. 'res://scripts/player.gd'"
    )
    script_content: Optional[str] = Field(
        None, description="Content if creating new script"
    )


class ConnectSignalRequest(BaseModel):
    source_path: str = Field(..., description="Path to source node")
    signal_name: str = Field(..., description="Signal name, e.g. 'pressed'")
    target_path: str = Field(..., description="Path to target node")
    method_name: str = Field(
        ..., description="Method to call, e.g. '_on_button_pressed'"
    )


class SetSelectionRequest(BaseModel):
    node_paths: list[str] = Field(..., description="Paths of nodes to select")


# Procedural Placement models
class SpawnGridRequest(BaseModel):
    parent_path: str = Field(..., description="Path to parent node")
    node_class: str = Field(
        ..., description="Godot class name to spawn, e.g. 'MeshInstance3D'"
    )
    rows: int = Field(..., ge=1, le=50, description="Number of rows (1-50)")
    cols: int = Field(..., ge=1, le=50, description="Number of columns (1-50)")
    spacing: list[float] = Field(
        ..., min_length=3, max_length=3, description="Spacing as [x, y, z]"
    )
    name_prefix: str = Field(
        default="Tile", description="Prefix for spawned node names"
    )


class SpawnRandomRequest(BaseModel):
    parent_path: str = Field(..., description="Path to parent node")
    node_class: str = Field(..., description="Godot class name to spawn")
    count: int = Field(
        ..., ge=1, le=500, description="Number of nodes to spawn (1-500)"
    )
    bounds_min: list[float] = Field(
        ..., min_length=3, max_length=3, description="Min bounds [x, y, z]"
    )
    bounds_max: list[float] = Field(
        ..., min_length=3, max_length=3, description="Max bounds [x, y, z]"
    )
    name_prefix: str = Field(
        default="Scatter", description="Prefix for spawned node names"
    )


class SpawnAlongPathRequest(BaseModel):
    parent_path: str = Field(..., description="Path to parent node")
    node_class: str = Field(..., description="Godot class name to spawn")
    points: list[list[float]] = Field(..., description="List of [x, y, z] positions")
    name_prefix: str = Field(
        default="PathPoint", description="Prefix for spawned node names"
    )


# =============================================================================
# NODE ENDPOINTS
# =============================================================================


@router.post("/node/create")
async def create_node(req: CreateNodeRequest) -> dict:
    """Create a new node in the scene tree."""
    return await send_to_godot(
        "create_node",
        {
            "parent_path": req.parent_path,
            "node_class": req.node_class,
            "node_name": req.node_name,
            "properties": req.properties,
        },
    )


@router.post("/node/delete")
async def delete_node(req: DeleteNodeRequest) -> dict:
    """Delete a node from the scene tree."""
    return await send_to_godot("delete_node", {"node_path": req.node_path})


@router.post("/node/rename")
async def rename_node(req: RenameNodeRequest) -> dict:
    """Rename a node."""
    return await send_to_godot(
        "rename_node", {"node_path": req.node_path, "new_name": req.new_name}
    )


@router.post("/node/reparent")
async def reparent_node(req: ReparentNodeRequest) -> dict:
    """Move a node to a new parent."""
    return await send_to_godot(
        "reparent_node",
        {"node_path": req.node_path, "new_parent_path": req.new_parent_path},
    )


# =============================================================================
# PROPERTY ENDPOINTS
# =============================================================================


@router.post("/property/get")
async def get_property(req: GetPropertyRequest) -> dict:
    """Get a property value from a node."""
    return await send_to_godot(
        "get_property", {"node_path": req.node_path, "property": req.property}
    )


@router.post("/property/set")
async def set_property(req: SetPropertyRequest) -> dict:
    """Set a property on a node."""
    return await send_to_godot(
        "set_property",
        {"node_path": req.node_path, "property": req.property, "value": req.value},
    )


# =============================================================================
# RESOURCE ENDPOINTS
# =============================================================================


@router.post("/resource/attach")
async def attach_resource(req: AttachResourceRequest) -> dict:
    """Attach a resource (mesh, material, texture) to a node."""
    return await send_to_godot(
        "attach_resource",
        {
            "node_path": req.node_path,
            "property": req.property,
            "resource_path": req.resource_path,
        },
    )


@router.post("/resource/create")
async def create_resource(req: CreateResourceRequest) -> dict:
    """Create a new resource and save it to disk."""
    return await send_to_godot(
        "create_resource",
        {
            "resource_type": req.resource_type,
            "properties": req.properties,
            "save_path": req.save_path,
        },
    )


# =============================================================================
# PROCEDURAL PLACEMENT ENDPOINTS
# =============================================================================


@router.post("/spawn/grid")
async def spawn_grid(req: SpawnGridRequest) -> dict:
    """Spawn nodes in a grid pattern - great for floors, walls, tilemaps."""
    return await send_to_godot(
        "spawn_grid",
        {
            "parent_path": req.parent_path,
            "node_class": req.node_class,
            "rows": req.rows,
            "cols": req.cols,
            "spacing": req.spacing,
            "name_prefix": req.name_prefix,
        },
    )


@router.post("/spawn/random")
async def spawn_random(req: SpawnRandomRequest) -> dict:
    """Scatter nodes randomly in a 3D area - good for trees, rocks, decorations."""
    return await send_to_godot(
        "spawn_random_in_area",
        {
            "parent_path": req.parent_path,
            "node_class": req.node_class,
            "count": req.count,
            "bounds_min": req.bounds_min,
            "bounds_max": req.bounds_max,
            "name_prefix": req.name_prefix,
        },
    )


@router.post("/spawn/path")
async def spawn_along_path(req: SpawnAlongPathRequest) -> dict:
    """Place nodes along a path - perfect for waypoints, road markers, fences."""
    return await send_to_godot(
        "spawn_along_path",
        {
            "parent_path": req.parent_path,
            "node_class": req.node_class,
            "points": req.points,
            "name_prefix": req.name_prefix,
        },
    )


# =============================================================================
# SCENE ENDPOINTS
# =============================================================================


@router.get("/scene/tree")
async def get_scene_tree() -> dict:
    """Get the current scene's node tree structure."""
    return await send_to_godot("get_scene_tree", {})


@router.post("/scene/instantiate")
async def instantiate_scene(req: InstantiateSceneRequest) -> dict:
    """Instantiate a PackedScene as a child node."""
    return await send_to_godot(
        "instantiate_scene",
        {
            "parent_path": req.parent_path,
            "scene_path": req.scene_path,
            "instance_name": req.instance_name,
        },
    )


@router.post("/scene/save")
async def save_scene() -> dict:
    """Save the current scene."""
    return await send_to_godot("save_scene", {})


# =============================================================================
# SCRIPT ENDPOINTS
# =============================================================================


@router.post("/script/attach")
async def attach_script(req: AttachScriptRequest) -> dict:
    """Attach or create a script for a node."""
    return await send_to_godot(
        "attach_script",
        {
            "node_path": req.node_path,
            "script_path": req.script_path,
            "create_content": req.script_content or "",
        },
    )


@router.post("/signal/connect")
async def connect_signal(req: ConnectSignalRequest) -> dict:
    """Connect a signal between two nodes."""
    return await send_to_godot(
        "connect_signal",
        {
            "source_path": req.source_path,
            "signal_name": req.signal_name,
            "target_path": req.target_path,
            "method_name": req.method_name,
        },
    )


# =============================================================================
# SELECTION ENDPOINTS
# =============================================================================


@router.get("/selection")
async def get_selection() -> dict:
    """Get currently selected nodes."""
    return await send_to_godot("get_selection", {})


@router.post("/selection/set")
async def set_selection(req: SetSelectionRequest) -> dict:
    """Select specific nodes."""
    return await send_to_godot("set_selection", {"node_paths": req.node_paths})


# =============================================================================
# SAFETY ENDPOINTS
# =============================================================================


@router.get("/changes")
async def get_pending_changes() -> dict:
    """Get list of pending AI changes for review."""
    return await send_to_godot("get_pending_changes", {})


@router.post("/undo")
async def undo_last() -> dict:
    """Undo the last AI action."""
    return await send_to_godot("undo_last", {})


@router.post("/clear-changes")
async def clear_changes() -> dict:
    """Clear pending changes (after user accepts)."""
    return await send_to_godot("clear_pending_changes", {})
