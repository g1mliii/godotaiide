@tool
# gdlint: disable=max-public-methods
class_name EditorActions
extends RefCounted
## EditorActions - Service for AI-driven editor manipulation
## All operations use EditorUndoRedoManager for proper undo/redo support

signal action_completed(action: String, result: Dictionary)
signal action_failed(action: String, error: String)

const MAX_PENDING_CHANGES := 100  # Prevent unbounded memory growth
const MAX_TREE_DEPTH := 50  # Prevent stack overflow on deep scene trees
const MAX_SPAWN_COUNT := 500  # Prevent runaway spawning

var _editor_interface: EditorInterface
var _undo_redo: EditorUndoRedoManager
var _pending_changes: Array[Dictionary] = []


func _init(plugin: EditorPlugin) -> void:
	_editor_interface = plugin.get_editor_interface()
	_undo_redo = plugin.get_undo_redo()


# =============================================================================
# NODE OPERATIONS
# =============================================================================

## Create a new node in the scene tree
func create_node(
	parent_path: String,
	node_class: String,
	node_name: String,
	properties: Dictionary = {}
) -> Dictionary:
	var parent := _get_node_by_path(parent_path)
	if not parent:
		return _error("Parent not found: " + parent_path)

	if not ClassDB.class_exists(node_class):
		return _error("Invalid class: " + node_class)

	var node: Node = ClassDB.instantiate(node_class)
	if not node:
		return _error("Failed to instantiate: " + node_class)

	node.name = node_name

	# Apply initial properties
	for key in properties:
		if key in node:
			node.set(key, _convert_value(properties[key]))

	# Use undo/redo for editor integration
	_undo_redo.create_action("AI: Create " + node_name)
	_undo_redo.add_do_method(parent, "add_child", node, true)
	_undo_redo.add_do_property(node, "owner", _get_scene_root())
	_undo_redo.add_do_reference(node)
	_undo_redo.add_undo_method(parent, "remove_child", node)
	_undo_redo.commit_action()

	_track_change("create_node", {"node_path": str(node.get_path())})
	return _success({"node_path": str(node.get_path())})


## Delete a node from the scene tree
func delete_node(node_path: String) -> Dictionary:
	var node := _get_node_by_path(node_path)
	if not node:
		return _error("Node not found: " + node_path)

	if node == _get_scene_root():
		return _error("Cannot delete scene root")

	var parent := node.get_parent()
	var index := node.get_index()

	_undo_redo.create_action("AI: Delete " + node.name)
	_undo_redo.add_do_method(parent, "remove_child", node)
	_undo_redo.add_undo_method(parent, "add_child", node, true)
	_undo_redo.add_undo_method(parent, "move_child", node, index)
	_undo_redo.add_undo_property(node, "owner", _get_scene_root())
	_undo_redo.add_undo_reference(node)
	_undo_redo.commit_action()

	_track_change("delete_node", {"node_path": node_path})
	return _success({})


## Rename a node
func rename_node(node_path: String, new_name: String) -> Dictionary:
	var node := _get_node_by_path(node_path)
	if not node:
		return _error("Node not found: " + node_path)

	var old_name := node.name

	_undo_redo.create_action("AI: Rename " + old_name + " → " + new_name)
	_undo_redo.add_do_property(node, "name", new_name)
	_undo_redo.add_undo_property(node, "name", old_name)
	_undo_redo.commit_action()

	_track_change("rename_node", {"old_path": node_path, "new_name": new_name})
	return _success({"new_path": str(node.get_path())})


## Reparent a node to a new parent
func reparent_node(node_path: String, new_parent_path: String) -> Dictionary:
	var node := _get_node_by_path(node_path)
	var new_parent := _get_node_by_path(new_parent_path)

	if not node:
		return _error("Node not found: " + node_path)
	if not new_parent:
		return _error("New parent not found: " + new_parent_path)
	if node == _get_scene_root():
		return _error("Cannot reparent scene root")

	var old_parent := node.get_parent()
	var old_index := node.get_index()

	_undo_redo.create_action("AI: Reparent " + node.name)
	_undo_redo.add_do_method(old_parent, "remove_child", node)
	_undo_redo.add_do_method(new_parent, "add_child", node, true)
	_undo_redo.add_do_property(node, "owner", _get_scene_root())
	_undo_redo.add_undo_method(new_parent, "remove_child", node)
	_undo_redo.add_undo_method(old_parent, "add_child", node, true)
	_undo_redo.add_undo_method(old_parent, "move_child", node, old_index)
	_undo_redo.add_undo_property(node, "owner", _get_scene_root())
	_undo_redo.commit_action()

	_track_change("reparent_node", {"node_path": node_path, "new_parent": new_parent_path})
	return _success({"new_path": str(node.get_path())})


# =============================================================================
# PROPERTY OPERATIONS
# =============================================================================

## Get a property value from a node
func get_property(node_path: String, property: String) -> Dictionary:
	var node := _get_node_by_path(node_path)
	if not node:
		return _error("Node not found: " + node_path)

	if not property in node:
		return _error("Property not found: " + property)

	var value = node.get(property)
	return _success({"value": _serialize_value(value)})


## Set a property on a node
func set_property(node_path: String, property: String, value: Variant) -> Dictionary:
	var node := _get_node_by_path(node_path)
	if not node:
		return _error("Node not found: " + node_path)

	if not property in node:
		return _error("Property not found: " + property)

	var old_value = node.get(property)
	var new_value = _convert_value(value)

	_undo_redo.create_action("AI: Set " + property)
	_undo_redo.add_do_property(node, property, new_value)
	_undo_redo.add_undo_property(node, property, old_value)
	_undo_redo.commit_action()

	_track_change("set_property", {"node_path": node_path, "property": property})
	return _success({})


# =============================================================================
# RESOURCE OPERATIONS
# =============================================================================

## Attach a resource to a node property
func attach_resource(
	node_path: String,
	property: String,
	resource_path: String
) -> Dictionary:
	var node := _get_node_by_path(node_path)
	if not node:
		return _error("Node not found: " + node_path)

	if not ResourceLoader.exists(resource_path):
		return _error("Resource not found: " + resource_path)

	var resource := load(resource_path)
	if not resource:
		return _error("Failed to load resource: " + resource_path)

	return set_property(node_path, property, resource)


## Create a new resource and save it
func create_resource(
	resource_type: String,
	properties: Dictionary,
	save_path: String
) -> Dictionary:
	if not ClassDB.class_exists(resource_type):
		return _error("Invalid resource type: " + resource_type)

	var resource: Resource = ClassDB.instantiate(resource_type)
	if not resource:
		return _error("Failed to create resource: " + resource_type)

	# Apply properties
	for key in properties:
		if key in resource:
			resource.set(key, _convert_value(properties[key]))

	# Save to disk
	var err := ResourceSaver.save(resource, save_path)
	if err != OK:
		return _error("Failed to save resource: " + str(err))

	_track_change("create_resource", {"resource_path": save_path})
	return _success({"resource_path": save_path})


# =============================================================================
# PROCEDURAL PLACEMENT (AI-driven level building)
# =============================================================================


## Spawn nodes in a grid pattern - great for floors, walls, tilemaps
func spawn_grid(
	parent_path: String,
	node_class: String,
	rows: int,
	cols: int,
	spacing: Vector3,
	name_prefix: String = "Tile"
) -> Dictionary:
	var parent := _get_node_by_path(parent_path)
	if not parent:
		return _error("Parent not found: " + parent_path)

	if not ClassDB.class_exists(node_class):
		return _error("Invalid class: " + node_class)

	var total := rows * cols
	if total > MAX_SPAWN_COUNT:
		return _error("Grid too large: %d exceeds %d" % [total, MAX_SPAWN_COUNT])

	if rows <= 0 or cols <= 0:
		return _error("Rows and cols must be positive")

	var created_paths: Array[String] = []
	var scene_root := _get_scene_root()

	_undo_redo.create_action("AI: Spawn %dx%d grid" % [rows, cols])

	for row in range(rows):
		for col in range(cols):
			var node: Node = ClassDB.instantiate(node_class)
			if not node:
				continue

			node.name = "%s_%d_%d" % [name_prefix, row, col]

			# Set position if it's a Node3D or Node2D
			var pos := Vector3(col * spacing.x, 0, row * spacing.z)
			if node is Node3D:
				node.position = pos
			elif node is Node2D:
				node.position = Vector2(col * spacing.x, row * spacing.y)

			_undo_redo.add_do_method(parent, "add_child", node, true)
			_undo_redo.add_do_property(node, "owner", scene_root)
			_undo_redo.add_do_reference(node)
			_undo_redo.add_undo_method(parent, "remove_child", node)

			created_paths.append(parent_path + "/" + node.name)

	_undo_redo.commit_action()

	_track_change("spawn_grid", {"parent": parent_path, "count": total})
	return _success({"created": created_paths, "count": total})


## Spawn nodes randomly within a 3D area - good for trees, rocks, decorations
func spawn_random_in_area(
	parent_path: String,
	node_class: String,
	count: int,
	bounds_min: Vector3,
	bounds_max: Vector3,
	name_prefix: String = "Scatter"
) -> Dictionary:
	var parent := _get_node_by_path(parent_path)
	if not parent:
		return _error("Parent not found: " + parent_path)

	if not ClassDB.class_exists(node_class):
		return _error("Invalid class: " + node_class)

	if count > MAX_SPAWN_COUNT:
		return _error("Count %d exceeds limit of %d" % [count, MAX_SPAWN_COUNT])

	if count <= 0:
		return _error("Count must be positive")

	var created_paths: Array[String] = []
	var scene_root := _get_scene_root()

	_undo_redo.create_action("AI: Scatter %d nodes" % count)

	for i in range(count):
		var node: Node = ClassDB.instantiate(node_class)
		if not node:
			continue

		node.name = "%s_%d" % [name_prefix, i]

		# Random position within bounds
		var pos := Vector3(
			randf_range(bounds_min.x, bounds_max.x),
			randf_range(bounds_min.y, bounds_max.y),
			randf_range(bounds_min.z, bounds_max.z)
		)

		if node is Node3D:
			node.position = pos
			# Optional: random Y-axis rotation for variety
			node.rotation.y = randf() * TAU
		elif node is Node2D:
			node.position = Vector2(pos.x, pos.y)

		_undo_redo.add_do_method(parent, "add_child", node, true)
		_undo_redo.add_do_property(node, "owner", scene_root)
		_undo_redo.add_do_reference(node)
		_undo_redo.add_undo_method(parent, "remove_child", node)

		created_paths.append(parent_path + "/" + node.name)

	_undo_redo.commit_action()

	_track_change("spawn_random_in_area", {"parent": parent_path, "count": count})
	return _success({"created": created_paths, "count": count})


## Spawn nodes along a path - perfect for waypoints, road markers, fences
func spawn_along_path(
	parent_path: String,
	node_class: String,
	points: Array,
	name_prefix: String = "PathPoint"
) -> Dictionary:
	var parent := _get_node_by_path(parent_path)
	if not parent:
		return _error("Parent not found: " + parent_path)

	if not ClassDB.class_exists(node_class):
		return _error("Invalid class: " + node_class)

	if points.size() > MAX_SPAWN_COUNT:
		return _error("Too many points: %d exceeds %d" % [points.size(), MAX_SPAWN_COUNT])

	if points.is_empty():
		return _error("Points array is empty")

	var created_paths: Array[String] = []
	var scene_root := _get_scene_root()

	_undo_redo.create_action("AI: Place %d path nodes" % points.size())

	for i in range(points.size()):
		var node: Node = ClassDB.instantiate(node_class)
		if not node:
			continue

		node.name = "%s_%d" % [name_prefix, i]

		# Convert point (could be Array or Vector3)
		var pos: Vector3
		var point = points[i]
		if point is Array and point.size() >= 3:
			pos = Vector3(point[0], point[1], point[2])
		elif point is Vector3:
			pos = point
		else:
			continue  # Skip invalid point

		if node is Node3D:
			node.position = pos

			# Orient towards next point if available
			if i < points.size() - 1:
				var next_point = points[i + 1]
				var next_pos: Vector3
				if next_point is Array and next_point.size() >= 3:
					next_pos = Vector3(next_point[0], next_point[1], next_point[2])
				elif next_point is Vector3:
					next_pos = next_point
				else:
					next_pos = pos

				if next_pos != pos:
					node.look_at(next_pos, Vector3.UP)

		_undo_redo.add_do_method(parent, "add_child", node, true)
		_undo_redo.add_do_property(node, "owner", scene_root)
		_undo_redo.add_do_reference(node)
		_undo_redo.add_undo_method(parent, "remove_child", node)

		created_paths.append(parent_path + "/" + node.name)

	_undo_redo.commit_action()

	_track_change("spawn_along_path", {"parent": parent_path, "count": points.size()})
	return _success({"created": created_paths, "count": points.size()})


# =============================================================================
# SCENE OPERATIONS
# =============================================================================

## Get the current scene's node tree structure
func get_scene_tree() -> Dictionary:
	var root := _get_scene_root()
	if not root:
		return _error("No scene open")

	return _success({"tree": _node_to_dict(root)})


## Instantiate a PackedScene as a child
func instantiate_scene(
	parent_path: String,
	scene_path: String,
	instance_name: String
) -> Dictionary:
	var parent := _get_node_by_path(parent_path)
	if not parent:
		return _error("Parent not found: " + parent_path)

	if not ResourceLoader.exists(scene_path):
		return _error("Scene not found: " + scene_path)

	var scene := load(scene_path) as PackedScene
	if not scene:
		return _error("Failed to load scene: " + scene_path)

	var instance := scene.instantiate()
	instance.name = instance_name

	_undo_redo.create_action("AI: Instantiate " + instance_name)
	_undo_redo.add_do_method(parent, "add_child", instance, true)
	_undo_redo.add_do_property(instance, "owner", _get_scene_root())
	_undo_redo.add_do_reference(instance)
	_undo_redo.add_undo_method(parent, "remove_child", instance)
	_undo_redo.commit_action()

	_track_change(
		"instantiate_scene",
		{"scene_path": scene_path, "node_path": str(instance.get_path())}
	)
	return _success({"node_path": str(instance.get_path())})


## Save the current scene
func save_scene() -> Dictionary:
	var err := _editor_interface.save_scene()
	if err != OK:
		return _error("Failed to save scene: " + str(err))
	return _success({})


# =============================================================================
# SCRIPT OPERATIONS
# =============================================================================

## Attach a script to a node
func attach_script(
	node_path: String,
	script_path: String,
	create_content: String = ""
) -> Dictionary:
	var node := _get_node_by_path(node_path)
	if not node:
		return _error("Node not found: " + node_path)

	var script: GDScript

	if ResourceLoader.exists(script_path):
		script = load(script_path)
	elif create_content != "":
		# Create new script
		script = GDScript.new()
		script.source_code = create_content
		var err := ResourceSaver.save(script, script_path)
		if err != OK:
			return _error("Failed to save script: " + str(err))
		script = load(script_path)  # Reload to get proper resource path
	else:
		return _error("Script not found and no content provided: " + script_path)

	var old_script = node.get_script()

	_undo_redo.create_action("AI: Attach script to " + node.name)
	_undo_redo.add_do_property(node, "script", script)
	_undo_redo.add_undo_property(node, "script", old_script)
	_undo_redo.commit_action()

	_track_change("attach_script", {"node_path": node_path, "script_path": script_path})
	return _success({"script_path": script_path})


## Connect a signal between two nodes
func connect_signal(
	source_path: String,
	signal_name: String,
	target_path: String,
	method_name: String
) -> Dictionary:
	var source := _get_node_by_path(source_path)
	var target := _get_node_by_path(target_path)

	if not source:
		return _error("Source node not found: " + source_path)
	if not target:
		return _error("Target node not found: " + target_path)

	if not source.has_signal(signal_name):
		return _error("Signal not found: " + signal_name)

	if source.is_connected(signal_name, Callable(target, method_name)):
		return _error("Signal already connected")

	_undo_redo.create_action("AI: Connect " + signal_name)
	_undo_redo.add_do_method(source, "connect", signal_name, Callable(target, method_name))
	_undo_redo.add_undo_method(
		source, "disconnect", signal_name, Callable(target, method_name)
	)
	_undo_redo.commit_action()

	_track_change("connect_signal", {
		"source": source_path,
		"signal": signal_name,
		"target": target_path,
		"method": method_name
	})
	return _success({})


# =============================================================================
# SELECTION & CONTEXT
# =============================================================================

## Get currently selected nodes
func get_selection() -> Dictionary:
	var selection := _editor_interface.get_selection()
	var selected: Array[String] = []
	for node in selection.get_selected_nodes():
		selected.append(str(node.get_path()))
	return _success({"selected": selected})


## Select specific nodes
func set_selection(node_paths: Array) -> Dictionary:
	var selection := _editor_interface.get_selection()
	selection.clear()

	for path in node_paths:
		var node := _get_node_by_path(path)
		if node:
			selection.add_node(node)

	return _success({})


# =============================================================================
# CHANGE TRACKING (for safety/rollback)
# =============================================================================

## Get all pending AI changes
func get_pending_changes() -> Array[Dictionary]:
	return _pending_changes


## Clear pending changes (call after user accepts)
func clear_pending_changes() -> void:
	_pending_changes.clear()


## Undo last action
func undo_last() -> Dictionary:
	_undo_redo.undo()
	if not _pending_changes.is_empty():
		_pending_changes.pop_back()
	return _success({})


func _track_change(action: String, data: Dictionary) -> void:
	# Prevent unbounded memory growth
	if _pending_changes.size() >= MAX_PENDING_CHANGES:
		_pending_changes.pop_front()  # Remove oldest

	_pending_changes.append({
		"action": action,
		"data": data,
		"timestamp": Time.get_unix_time_from_system()
	})
	action_completed.emit(action, data)


# =============================================================================
# HELPERS
# =============================================================================

func _get_scene_root() -> Node:
	return _editor_interface.get_edited_scene_root()


func _get_node_by_path(path: String) -> Node:
	var root := _get_scene_root()
	if not root:
		return null

	# Handle various path formats
	if path == "" or path == "/root" or path == root.name:
		return root

	# Strip /root/SceneName prefix if present
	var scene_prefix := "/root/" + root.name
	if path.begins_with(scene_prefix):
		path = path.substr(scene_prefix.length())

	if path == "" or path == "/":
		return root

	# Remove leading slash for get_node
	if path.begins_with("/"):
		path = path.substr(1)

	return root.get_node_or_null(path)


func _node_to_dict(node: Node, depth: int = 0) -> Dictionary:
	var result := {
		"name": node.name,
		"type": node.get_class(),
		"path": str(node.get_path()),
		"children": []
	}

	# Add script info if present
	var script = node.get_script()
	if script:
		result["script"] = script.resource_path

	# Recurse children with depth limit to prevent stack overflow
	if depth < MAX_TREE_DEPTH:
		for child in node.get_children():
			result.children.append(_node_to_dict(child, depth + 1))
	elif node.get_child_count() > 0:
		result["truncated"] = true
		result["child_count"] = node.get_child_count()

	return result


func _convert_value(value: Variant) -> Variant:
	if value is Array:
		return _convert_array_value(value)

	if value is Dictionary:
		return _convert_dict_value(value)

	return value


func _convert_array_value(arr: Array) -> Variant:
	if arr.is_empty():
		return arr

	var all_numbers := true
	for elem in arr:
		if not (elem is float or elem is int):
			all_numbers = false
			break

	if all_numbers:
		match arr.size():
			2: return Vector2(arr[0], arr[1])
			3: return Vector3(arr[0], arr[1], arr[2])
			4: return Color(arr[0], arr[1], arr[2], arr[3])

	return arr


func _convert_dict_value(dict: Dictionary) -> Variant:
	if dict.has("_type"):
		var type = dict.get("_type")
		if type == "Vector2":
			return Vector2(dict.get("x", 0), dict.get("y", 0))
		if type == "Vector3":
			return Vector3(dict.get("x", 0), dict.get("y", 0), dict.get("z", 0))
		if type == "Color":
			return Color(
				dict.get("r", 0),
				dict.get("g", 0),
				dict.get("b", 0),
				dict.get("a", 1)
			)
	return dict


func _serialize_value(value: Variant) -> Variant:
	# Convert Godot types to JSON-serializable
	match typeof(value):
		TYPE_VECTOR2:
			return [value.x, value.y]
		TYPE_VECTOR3:
			return [value.x, value.y, value.z]
		TYPE_COLOR:
			return [value.r, value.g, value.b, value.a]
		TYPE_OBJECT:
			if value is Resource:
				return value.resource_path
			return null
		_:
			return value


func _success(data: Dictionary) -> Dictionary:
	data["success"] = true
	return data


func _error(message: String) -> Dictionary:
	action_failed.emit("", message)
	return {"success": false, "error": message}
