@tool
class_name GodotMindsPlugin
extends EditorPlugin

# Constants
const API_CLIENT_AUTOLOAD := "GodotMindsAPI"
const SETTINGS_AUTOLOAD := "GodotMindsSettings"

# Dock reference
var _source_control_dock: Control


func _enter_tree() -> void:
	# Register autoloads (settings manager first, then API client)
	add_autoload_singleton(
		SETTINGS_AUTOLOAD,
		"res://addons/godot_minds/autoload/settings_manager.gd"
	)

	add_autoload_singleton(
		API_CLIENT_AUTOLOAD,
		"res://addons/godot_minds/autoload/api_client.gd"
	)

	print("[Godot-Minds] Plugin enabled")

	# Wait a frame for autoloads to initialize
	await get_tree().process_frame

	# Verify autoloads were registered successfully
	if not _verify_autoloads_registered():
		push_error("[Godot-Minds] Failed to register autoloads. Plugin may not function correctly.")
		return

	print("[Godot-Minds] Autoloads registered successfully: %s, %s" % [SETTINGS_AUTOLOAD, API_CLIENT_AUTOLOAD])
	print("[Godot-Minds] Server URL: ", _get_server_url())

	# Add Source Control dock
	var dock_scene := preload("res://addons/godot_minds/scenes/source_control_dock.tscn")
	_source_control_dock = dock_scene.instantiate()
	add_control_to_dock(DOCK_SLOT_RIGHT_BL, _source_control_dock)
	print("[Godot-Minds] Source Control dock added")


func _exit_tree() -> void:
	# Remove Source Control dock
	if _source_control_dock:
		remove_control_from_docks(_source_control_dock)
		_source_control_dock.queue_free()
		_source_control_dock = null
		print("[Godot-Minds] Source Control dock removed")

	# Remove autoloads in reverse order
	remove_autoload_singleton(API_CLIENT_AUTOLOAD)
	remove_autoload_singleton(SETTINGS_AUTOLOAD)

	# Verify autoloads were removed successfully
	await get_tree().process_frame

	if _verify_autoloads_registered():
		push_warning("[Godot-Minds] Autoloads may not have been removed completely")
	else:
		print("[Godot-Minds] Autoloads removed successfully")

	print("[Godot-Minds] Plugin disabled")


func _get_plugin_name() -> String:
	return "Godot-Minds"


func _verify_autoloads_registered() -> bool:
	# Check if both autoloads exist in the scene tree
	var settings_path := "/root/" + SETTINGS_AUTOLOAD
	var api_path := "/root/" + API_CLIENT_AUTOLOAD

	var settings_exists := has_node(settings_path)
	var api_exists := has_node(api_path)

	if not settings_exists:
		push_error("[Godot-Minds] Settings autoload not found at: %s" % settings_path)

	if not api_exists:
		push_error("[Godot-Minds] API client autoload not found at: %s" % api_path)

	return settings_exists and api_exists


func _get_server_url() -> String:
	# Try to get server URL from settings manager if available
	var autoload_path := "/root/" + SETTINGS_AUTOLOAD

	if has_node(autoload_path):
		var settings := get_node(autoload_path)
		if settings and settings.has_method("get_server_url"):
			return settings.get_server_url()

	# Fallback to default if autoload is not ready yet
	return "http://127.0.0.1:8005"
