extends Node

# Signals
signal settings_changed(setting_name: String, new_value: Variant)

# Constants
const SETTINGS_PREFIX := "godot_minds/"
const DEFAULT_SERVER_HOST := "127.0.0.1"
const DEFAULT_SERVER_PORT := 8005
const DEFAULT_AI_MODE := "direct"
const DEFAULT_POLLING_INTERVAL := 2.0

# Server settings paths
const SETTING_SERVER_HOST := SETTINGS_PREFIX + "server/host"
const SETTING_SERVER_PORT := SETTINGS_PREFIX + "server/port"

# AI settings paths
const SETTING_AI_MODE := SETTINGS_PREFIX + "ai/mode"
const SETTING_API_KEY_ANTHROPIC := SETTINGS_PREFIX + "api_keys/anthropic"
const SETTING_API_KEY_OPENAI := SETTINGS_PREFIX + "api_keys/openai"
const SETTING_API_KEY_OPENCODE := SETTINGS_PREFIX + "api_keys/opencode"

# UI settings paths
const SETTING_POLLING_INTERVAL := SETTINGS_PREFIX + "ui/polling_interval"

# Private variables
var _editor_settings = null  # EditorSettings (injected by plugin)


func _ready() -> void:
	# Don't initialize editor settings here - EditorInterface isn't available yet
	# Will be initialized lazily when first accessed
	print("[GodotMindsSettings] _ready() called - autoload is initializing")


func _exit_tree() -> void:
	# Clean up editor settings reference
	_editor_settings = null


# Public Methods

func get_server_url() -> String:
	var host: String = get_setting(SETTING_SERVER_HOST, DEFAULT_SERVER_HOST)
	var port: int = get_setting(SETTING_SERVER_PORT, DEFAULT_SERVER_PORT)
	return "http://%s:%d" % [host, port]


func get_websocket_url() -> String:
	var host: String = get_setting(SETTING_SERVER_HOST, DEFAULT_SERVER_HOST)
	var port: int = get_setting(SETTING_SERVER_PORT, DEFAULT_SERVER_PORT)
	return "ws://%s:%d/ws" % [host, port]


func get_ai_mode() -> String:
	return get_setting(SETTING_AI_MODE, DEFAULT_AI_MODE)


func set_ai_mode(mode: String) -> void:
	if mode not in ["direct", "opencode", "ollama"]:
		push_error("Invalid AI mode: %s" % mode)
		return

	set_setting(SETTING_AI_MODE, mode)


func get_api_key(provider: String) -> String:
	var setting_path := ""

	match provider.to_lower():
		"anthropic":
			setting_path = SETTING_API_KEY_ANTHROPIC
		"openai":
			setting_path = SETTING_API_KEY_OPENAI
		"opencode":
			setting_path = SETTING_API_KEY_OPENCODE
		_:
			push_error("Unknown API key provider: %s" % provider)
			return ""

	return get_setting(setting_path, "")


func set_api_key(provider: String, api_key: String) -> void:
	var setting_path := ""

	match provider.to_lower():
		"anthropic":
			setting_path = SETTING_API_KEY_ANTHROPIC
		"openai":
			setting_path = SETTING_API_KEY_OPENAI
		"opencode":
			setting_path = SETTING_API_KEY_OPENCODE
		_:
			push_error("Unknown API key provider: %s" % provider)
			return

	set_setting(setting_path, api_key)


func get_polling_interval() -> float:
	return get_setting(SETTING_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)


func set_polling_interval(interval: float) -> void:
	if interval < 0.5:
		push_error("Polling interval too small: %f (minimum: 0.5)" % interval)
		return

	if interval > 60.0:
		push_error("Polling interval too large: %f (maximum: 60.0)" % interval)
		return

	set_setting(SETTING_POLLING_INTERVAL, interval)


func get_setting(setting_path: String, default_value: Variant) -> Variant:
	_ensure_editor_settings()

	if not _editor_settings:
		# EditorSettings still not available, return default
		return default_value

	if _editor_settings.has_setting(setting_path):
		return _editor_settings.get_setting(setting_path)

	return default_value


func set_setting(setting_path: String, value: Variant) -> void:
	_ensure_editor_settings()

	if not _editor_settings:
		push_error("EditorSettings not available")
		return

	_editor_settings.set_setting(setting_path, value)
	settings_changed.emit(setting_path, value)


# Private Methods

func set_editor_settings(editor_settings) -> void:
	"""Called by plugin to inject EditorSettings (EditorInterface not accessible from autoloads)"""
	_editor_settings = editor_settings
	if _editor_settings:
		_initialize_settings()
		print("[GodotMindsSettings] EditorSettings initialized")


func _ensure_editor_settings() -> void:
	"""Lazy initialization of editor settings - call this before accessing settings"""
	if _editor_settings:
		return  # Already initialized

	# EditorSettings will be injected by the plugin
	# If not available, we'll just use defaults


func _initialize_editor_settings() -> void:
	# Deprecated - use _ensure_editor_settings() instead
	_ensure_editor_settings()


func _initialize_settings() -> void:
	if not _editor_settings:
		return

	# Server settings
	_create_setting_if_missing(
		SETTING_SERVER_HOST,
		DEFAULT_SERVER_HOST,
		TYPE_STRING,
		PROPERTY_HINT_NONE
	)

	_create_setting_if_missing(
		SETTING_SERVER_PORT,
		DEFAULT_SERVER_PORT,
		TYPE_INT,
		PROPERTY_HINT_RANGE,
		"1024,65535,1"
	)

	# AI settings
	_create_setting_if_missing(
		SETTING_AI_MODE,
		DEFAULT_AI_MODE,
		TYPE_STRING,
		PROPERTY_HINT_ENUM,
		"direct,opencode,ollama"
	)

	# API keys (masked with password hint)
	_create_setting_if_missing(
		SETTING_API_KEY_ANTHROPIC,
		"",
		TYPE_STRING,
		PROPERTY_HINT_PASSWORD
	)

	_create_setting_if_missing(
		SETTING_API_KEY_OPENAI,
		"",
		TYPE_STRING,
		PROPERTY_HINT_PASSWORD
	)

	_create_setting_if_missing(
		SETTING_API_KEY_OPENCODE,
		"",
		TYPE_STRING,
		PROPERTY_HINT_PASSWORD
	)

	# UI settings
	_create_setting_if_missing(
		SETTING_POLLING_INTERVAL,
		DEFAULT_POLLING_INTERVAL,
		TYPE_FLOAT,
		PROPERTY_HINT_RANGE,
		"0.5,60.0,0.5"
	)


func _create_setting_if_missing(
	setting_path: String,
	default_value: Variant,
	_type: int,
	_hint: int = PROPERTY_HINT_NONE,
	_hint_string: String = ""
) -> void:
	if _editor_settings.has_setting(setting_path):
		return

	_editor_settings.set_setting(setting_path, default_value)
	_editor_settings.set_initial_value(setting_path, default_value, false)

	# Note: EditorSettings automatically handles type hints for standard types
	# (String, int, float, bool) based on the default_value provided
