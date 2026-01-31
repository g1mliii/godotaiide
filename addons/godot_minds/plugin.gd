@tool
class_name GodotMindsPlugin
extends EditorPlugin

# Constants
const API_CLIENT_AUTOLOAD := "GodotMindsAPI"
const SETTINGS_AUTOLOAD := "GodotMindsSettings"

# Preload EditorActions class
const EditorActionsClass := preload("res://addons/godot_minds/scripts/editor_actions.gd")

# References
var _source_control_dock: Control
var _editor_actions = null  # EditorActions instance
var _api_client: Node = null  # API client instance (editor-only)
var _settings_manager: Node = null  # Settings manager instance (editor-only)


func _enter_tree() -> void:
	print("[Godot-Minds] Plugin enabled")

	# Create editor-only instances of services (don't use autoloads for editor functionality)
	_create_services()

	# Defer initialization to after editor is ready
	call_deferred("_initialize_plugin")


func _initialize_plugin() -> void:
	print("[Godot-Minds] Initializing plugin...")

	# Verify services were created
	if not _settings_manager or not _api_client:
		push_error("[Godot-Minds] Services not created!")
		return

	print("[Godot-Minds] Services ready!")
	_complete_initialization()

func _complete_initialization() -> void:
	"""Complete plugin initialization with services ready"""
	print("[Godot-Minds] Completing plugin initialization...")

	print("[Godot-Minds] Server URL: ", _get_server_url())

	# Initialize EditorActions and register with API client
	_editor_actions = EditorActionsClass.new(self)
	if _api_client and _api_client.has_method("set_editor_actions"):
		_api_client.set_editor_actions(_editor_actions)
		print("[Godot-Minds] EditorActions registered with API client")

	# Add Source Control dock and pass service references
	var DockScene := preload("res://addons/godot_minds/scenes/source_control_dock.tscn")
	_source_control_dock = DockScene.instantiate()

	# Inject services into the dock
	if _source_control_dock.has_method("set_services"):
		_source_control_dock.set_services(_api_client, _settings_manager)

	add_control_to_dock(DOCK_SLOT_RIGHT_BL, _source_control_dock)
	print("[Godot-Minds] Source Control dock added")
	print("[Godot-Minds] ✓ Plugin fully initialized!")


func _exit_tree() -> void:
	# Clean up editor actions reference
	if _editor_actions:
		if _api_client and _api_client.has_method("set_editor_actions"):
			_api_client.set_editor_actions(null)
		_editor_actions = null

	# Remove Source Control dock
	if _source_control_dock:
		remove_control_from_docks(_source_control_dock)
		_source_control_dock.queue_free()
		_source_control_dock = null
		print("[Godot-Minds] Source Control dock removed")

	# Clean up services
	if _api_client:
		_api_client.queue_free()
		_api_client = null

	if _settings_manager:
		_settings_manager.queue_free()
		_settings_manager = null

	print("[Godot-Minds] Services cleaned up")
	print("[Godot-Minds] Plugin disabled")


func _get_plugin_name() -> String:
	return "Godot-Minds"


func _create_services() -> void:
	"""Create editor-only instances of API client and settings manager"""
	print("[Godot-Minds] Creating editor services...")

	# Load and instantiate settings manager
	var SettingsScript := preload("res://addons/godot_minds/autoload/settings_manager.gd")
	_settings_manager = SettingsScript.new()
	add_child(_settings_manager)

	# Inject EditorSettings (only available in EditorPlugin context)
	if _settings_manager.has_method("set_editor_settings"):
		_settings_manager.set_editor_settings(get_editor_interface().get_editor_settings())

	# Load and instantiate API client
	var APIScript := preload("res://addons/godot_minds/autoload/api_client.gd")
	_api_client = APIScript.new()
	add_child(_api_client)

	# Inject settings manager into API client
	if _api_client.has_method("set_settings_manager"):
		_api_client.set_settings_manager(_settings_manager)

	print("[Godot-Minds] Services created successfully")




func _get_server_url() -> String:
	# Get server URL from settings manager instance
	if _settings_manager and _settings_manager.has_method("get_server_url"):
		return _settings_manager.get_server_url()

	# Fallback to default
	return "http://127.0.0.1:8005"
