@tool
class_name SourceControlDock
extends Control

# Signals
signal file_staged(file_path: String)
signal file_unstaged(file_path: String)
signal commit_created(commit_hash: String)
signal status_refreshed(file_count: int)

# Constants
const MIN_COMMIT_MESSAGE_LENGTH := 3
const MAX_FILES := 10000
const DEBOUNCE_DELAY := 0.2  # 200ms debounce prevents UI spam from rapid typing (UX research optimal range: 150-300ms)

# Color constants (prevent allocations)
const COLOR_CATEGORY := Color(0.7, 0.7, 0.7, 1.0)
const COLOR_MODIFIED := Color(0.5, 0.8, 1.0)
const COLOR_ADDED := Color(0.5, 1.0, 0.5)
const COLOR_DELETED := Color(1.0, 0.5, 0.5)
const COLOR_UNTRACKED := Color(0.9, 0.9, 0.5)

# Lucide icons (lazy loaded in _ready to reduce plugin load time)
var ICON_REFRESH: Texture2D
var ICON_SPARKLES: Texture2D
var ICON_FILE: Texture2D
var ICON_FILE_PLUS: Texture2D
var ICON_FILE_MINUS: Texture2D
var ICON_CHECK: Texture2D

# State
var _api_client: Node
var _settings: Node
var _staged_files: Dictionary = {}    # path -> FileStatus
var _unstaged_files: Dictionary = {}  # path -> FileStatus
var _is_operation_pending: bool = false
var _is_polling_active: bool = false

# Optimization state
var _last_status_hash: int = 0        # Hash of last git status to detect changes
var _debounce_timer: Timer = null     # Timer for text change debouncing
var _refresh_debounce_timer: Timer = null  # Timer for refresh debouncing
var _cached_polling_interval: float = 2.0  # Cached settings value
var _last_refresh_time: float = 0.0   # Track last refresh for rate limiting
var _refresh_queued: bool = false     # Track if refresh is queued
var _last_file_set: Dictionary = {}   # Track previous file set for incremental updates
var _tree_item_cache: Dictionary = {}  # Map file_path -> TreeItem for incremental updates

# @onready nodes
@onready var refresh_button: Button = %RefreshButton
@onready var branch_label: Label = %BranchLabel
@onready var ai_message_button: Button = %AIMessageButton
@onready var commit_message_edit: TextEdit = %CommitMessageEdit
@onready var commit_button: Button = %CommitButton
@onready var file_tree: Tree = %FileTree
@onready var file_count_label: Label = %FileCountLabel
@onready var polling_timer: Timer = %PollingTimer


func _ready() -> void:
	await get_tree().process_frame  # Wait for autoloads
	_load_icons()
	_initialize_api_client()
	_setup_icons()
	_setup_debounce_timer()
	_connect_signals()
	_setup_tree()
	_setup_polling()
	refresh_status()


func _exit_tree() -> void:
	# Stop polling
	if polling_timer:
		polling_timer.stop()

	# CRITICAL: Disconnect all API signals to prevent memory leaks
	# The API client is an autoload singleton that persists between plugin reloads
	if _api_client:
		if _api_client.git_status_received.is_connected(_on_git_status_received):
			_api_client.git_status_received.disconnect(_on_git_status_received)
		if _api_client.git_operation_completed.is_connected(_on_git_operation_completed):
			_api_client.git_operation_completed.disconnect(_on_git_operation_completed)
		if _api_client.api_error.is_connected(_on_api_error):
			_api_client.api_error.disconnect(_on_api_error)
		if _api_client.ai_commit_message_received.is_connected(_on_ai_commit_message_received):
			_api_client.ai_commit_message_received.disconnect(_on_ai_commit_message_received)

	# Disconnect UI signals
	if refresh_button and refresh_button.pressed.is_connected(_on_refresh_button_pressed):
		refresh_button.pressed.disconnect(_on_refresh_button_pressed)
	if commit_button and commit_button.pressed.is_connected(_on_commit_button_pressed):
		commit_button.pressed.disconnect(_on_commit_button_pressed)
	if ai_message_button and ai_message_button.pressed.is_connected(_on_ai_message_button_pressed):
		ai_message_button.pressed.disconnect(_on_ai_message_button_pressed)
	if commit_message_edit and commit_message_edit.text_changed.is_connected(_on_commit_message_text_changed):
		commit_message_edit.text_changed.disconnect(_on_commit_message_text_changed)
	if file_tree and file_tree.item_activated.is_connected(_on_file_tree_item_activated):
		file_tree.item_activated.disconnect(_on_file_tree_item_activated)
	if polling_timer and polling_timer.timeout.is_connected(_on_polling_timer_timeout):
		polling_timer.timeout.disconnect(_on_polling_timer_timeout)

	# Clean up debounce timers
	if _debounce_timer:
		_debounce_timer.queue_free()
		_debounce_timer = null
	if _refresh_debounce_timer:
		_refresh_debounce_timer.queue_free()
		_refresh_debounce_timer = null


func _notification(what: int) -> void:
	match what:
		NOTIFICATION_WM_WINDOW_FOCUS_IN:
			if not _is_polling_active and polling_timer:
				_is_polling_active = true
				polling_timer.start()
				refresh_status()

		NOTIFICATION_WM_WINDOW_FOCUS_OUT:
			if _is_polling_active and polling_timer:
				_is_polling_active = false
				polling_timer.stop()


func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed:
		return

	# Ctrl+Enter: Commit
	if event.keycode == KEY_ENTER and event.ctrl_pressed:
		if not commit_button.disabled:
			commit_changes()
		accept_event()

	# F5: Refresh
	elif event.keycode == KEY_F5:
		refresh_status()
		accept_event()

	# Ctrl+G: Generate AI message
	elif event.keycode == KEY_G and event.ctrl_pressed:
		if not ai_message_button.disabled:
			generate_ai_message()
		accept_event()


# Initialization

func _load_icons() -> void:
	"""Lazy load icons on demand instead of preloading at compile time"""
	ICON_REFRESH = load("res://addons/godot_minds/icons/lucide/refresh-cw.svg")
	ICON_SPARKLES = load("res://addons/godot_minds/icons/lucide/sparkles.svg")
	ICON_FILE = load("res://addons/godot_minds/icons/lucide/file.svg")
	ICON_FILE_PLUS = load("res://addons/godot_minds/icons/lucide/file-plus.svg")
	ICON_FILE_MINUS = load("res://addons/godot_minds/icons/lucide/file-minus.svg")
	ICON_CHECK = load("res://addons/godot_minds/icons/lucide/check.svg")


func _initialize_api_client() -> void:
	_api_client = get_node_or_null("/root/GodotMindsAPI")
	_settings = get_node_or_null("/root/GodotMindsSettings")

	if not _api_client:
		push_error("[SourceControlDock] API client not found")
		return

	print("[SourceControlDock] Initialized with API client")


func _setup_icons() -> void:
	# Set Lucide icons for buttons
	refresh_button.icon = ICON_REFRESH
	ai_message_button.icon = ICON_SPARKLES
	commit_button.icon = ICON_CHECK


func _setup_debounce_timer() -> void:
	# Create debounce timer for text changes
	_debounce_timer = Timer.new()
	_debounce_timer.wait_time = DEBOUNCE_DELAY
	_debounce_timer.one_shot = true
	add_child(_debounce_timer)
	_debounce_timer.timeout.connect(_on_debounce_timeout)

	# Create debounce timer for refresh operations
	_refresh_debounce_timer = Timer.new()
	_refresh_debounce_timer.wait_time = 1.0  # 1 second debounce for refreshes
	_refresh_debounce_timer.one_shot = true
	add_child(_refresh_debounce_timer)
	_refresh_debounce_timer.timeout.connect(_on_refresh_debounce_timeout)


func _connect_signals() -> void:
	if not _api_client:
		return

	# API signals
	_api_client.git_status_received.connect(_on_git_status_received)
	_api_client.git_operation_completed.connect(_on_git_operation_completed)
	_api_client.api_error.connect(_on_api_error)
	_api_client.ai_commit_message_received.connect(_on_ai_commit_message_received)

	# UI signals
	refresh_button.pressed.connect(_on_refresh_button_pressed)
	commit_button.pressed.connect(_on_commit_button_pressed)
	ai_message_button.pressed.connect(_on_ai_message_button_pressed)
	commit_message_edit.text_changed.connect(_on_commit_message_text_changed)  # Debounced handler
	file_tree.item_activated.connect(_on_file_tree_item_activated)
	polling_timer.timeout.connect(_on_polling_timer_timeout)


func _setup_tree() -> void:
	file_tree.set_column_expand(0, true)   # File path column
	file_tree.set_column_expand(1, false)  # Status badge column
	file_tree.set_column_custom_minimum_width(1, 50)
	file_tree.hide_root = true


func _setup_polling() -> void:
	# Cache polling interval to avoid repeated settings lookups
	_cached_polling_interval = _settings.get_polling_interval() if _settings and _settings.has_method("get_polling_interval") else 2.0
	polling_timer.wait_time = _cached_polling_interval
	polling_timer.start()
	_is_polling_active = true


# Tree Population

func _on_git_status_received(data: Dictionary) -> void:
	# Validate response structure
	if not data.has("files") or not data.has("branch"):
		push_error("[SourceControlDock] Invalid git status response: missing required fields")
		_on_api_error("Invalid response from backend")
		return

	if not data.files is Array:
		push_error("[SourceControlDock] Invalid git status response: 'files' is not an array")
		_on_api_error("Invalid response from backend")
		return

	_populate_tree(data)


func _clear_tree_metadata() -> void:
	"""Manually clear tree item metadata to prevent memory leaks"""
	var root := file_tree.get_root()
	if not root:
		return

	# Recursively clear metadata from all items
	_clear_item_metadata_recursive(root)


func _clear_item_metadata_recursive(item: TreeItem) -> void:
	"""Recursively clear metadata from tree item and children"""
	if not item:
		return

	# Clear metadata from all columns
	for col in range(file_tree.columns):
		item.set_metadata(col, null)

	# Process children
	var child := item.get_first_child()
	while child:
		_clear_item_metadata_recursive(child)
		child = child.get_next()


func _populate_tree(data: Dictionary) -> void:
	var files: Array = data.get("files", [])
	var original_file_count := files.size()

	# Bounds checking
	if files.size() > MAX_FILES:
		push_warning("[SourceControlDock] Too many files (%d), truncating to %d" % [files.size(), MAX_FILES])
		files = files.slice(0, MAX_FILES)

	# Hash-based change detection - only rebuild if data changed
	# Hash only critical fields instead of entire data structure for performance
	var status_hash := hash("%s:%d" % [data.get("branch", ""), files.size()])
	if status_hash == _last_status_hash:
		return  # No changes, skip rebuild
	_last_status_hash = status_hash

	# Try incremental update first (only if tree already populated)
	var root := file_tree.get_root()
	if root and root.get_child_count() == 2:
		if _try_incremental_tree_update(files, data):
			# Incremental update succeeded
			if data.has("branch"):
				branch_label.text = "Branch: %s" % data.get("branch", "unknown")

			# Show truncation warning in file count label
			if original_file_count > MAX_FILES:
				file_count_label.text = "%d+ files (showing %d)" % [original_file_count, MAX_FILES]
			else:
				file_count_label.text = "%d files" % files.size()

			_update_button_states()
			status_refreshed.emit(files.size())
			return

	# Fall back to full rebuild if incremental update failed or first time
	_populate_tree_full_rebuild(files, data, original_file_count)


func _try_incremental_tree_update(files: Array, data: Dictionary) -> bool:
	"""Try to incrementally update tree instead of full rebuild. Returns true if successful."""
	# Build current file set
	var current_file_set: Dictionary = {}
	for file_data in files:
		var file_path: String = file_data.get("path", "")
		current_file_set[file_path] = file_data

	# Check if changes are minimal (< 20% of files changed)
	var added_count := 0
	var removed_count := 0

	for file_path in current_file_set.keys():
		if not _last_file_set.has(file_path):
			added_count += 1

	for file_path in _last_file_set.keys():
		if not current_file_set.has(file_path):
			removed_count += 1

	var total_changes := added_count + removed_count
	var total_files := max(files.size(), _last_file_set.size())

	# If more than 20% changed, do full rebuild (faster than incremental)
	if total_files > 0 and float(total_changes) / float(total_files) > 0.2:
		_last_file_set = current_file_set
		return false

	# Perform incremental update
	var root := file_tree.get_root()
	var staged_category := root.get_child(0)
	var unstaged_category := root.get_child(1)

	# Remove deleted files
	for file_path in _last_file_set.keys():
		if not current_file_set.has(file_path):
			if _tree_item_cache.has(file_path):
				var item: TreeItem = _tree_item_cache[file_path]
				if item:
					item.free()
				_tree_item_cache.erase(file_path)

	# Add new files or update existing
	_staged_files.clear()
	_unstaged_files.clear()
	var staged_count := 0
	var unstaged_count := 0

	for file_data in files:
		var file_path: String = file_data.get("path", "")
		var staged: bool = file_data.get("staged", false)

		if staged:
			_staged_files[file_path] = file_data
			staged_count += 1
		else:
			_unstaged_files[file_path] = file_data
			unstaged_count += 1

		# Check if file already exists in tree
		if _tree_item_cache.has(file_path):
			var item: TreeItem = _tree_item_cache[file_path]
			# Update checkbox state if changed
			if item and item.is_checked(0) != staged:
				var parent_category := staged_category if staged else unstaged_category
				# Move item to correct category by recreating
				item.free()
				var new_item := _create_file_item(file_data, parent_category, staged)
				_tree_item_cache[file_path] = new_item
		else:
			# Add new file
			var parent_category := staged_category if staged else unstaged_category
			var item := _create_file_item(file_data, parent_category, staged)
			_tree_item_cache[file_path] = item

	# Update category labels
	staged_category.set_text(0, "Staged Changes (%d)" % staged_count)
	unstaged_category.set_text(0, "Unstaged Changes (%d)" % unstaged_count)

	_last_file_set = current_file_set
	return true


func _populate_tree_full_rebuild(files: Array, data: Dictionary, original_file_count: int) -> void:
	"""Perform full tree rebuild (fallback when incremental update not possible)"""
	# Clear tree metadata manually to prevent memory leaks
	_clear_tree_metadata()

	file_tree.clear()
	_tree_item_cache.clear()
	_staged_files.clear()
	_unstaged_files.clear()

	var root := file_tree.create_item()
	var staged_category := _create_category_item("Staged Changes", root)
	var unstaged_category := _create_category_item("Unstaged Changes", root)

	var staged_count := 0
	var unstaged_count := 0

	# Build current file set for next incremental update
	_last_file_set.clear()

	for file_data in files:
		var file_path: String = file_data.get("path", "")
		_last_file_set[file_path] = file_data

		if file_data.get("staged", false):
			var item := _create_file_item(file_data, staged_category, true)
			_tree_item_cache[file_path] = item
			_staged_files[file_path] = file_data
			staged_count += 1
		else:
			var item := _create_file_item(file_data, unstaged_category, false)
			_tree_item_cache[file_path] = item
			_unstaged_files[file_path] = file_data
			unstaged_count += 1

	# Update labels (use format strings to avoid string concatenation allocations)
	staged_category.set_text(0, "Staged Changes (%d)" % staged_count)
	unstaged_category.set_text(0, "Unstaged Changes (%d)" % unstaged_count)

	if data.has("branch"):
		branch_label.text = "Branch: %s" % data.get("branch", "unknown")

	# Show truncation warning in file count label
	if original_file_count > MAX_FILES:
		file_count_label.text = "%d+ files (showing %d)" % [original_file_count, MAX_FILES]
	else:
		file_count_label.text = "%d files" % files.size()

	_update_button_states()
	status_refreshed.emit(files.size())


func _create_category_item(title: String, parent: TreeItem) -> TreeItem:
	var item := file_tree.create_item(parent)
	item.set_text(0, title)
	item.set_selectable(0, false)
	item.set_custom_color(0, COLOR_CATEGORY)  # Use constant to prevent allocation
	return item


func _create_file_item(file_data: Dictionary, parent: TreeItem, staged: bool) -> TreeItem:
	var item := file_tree.create_item(parent)
	var file_path: String = file_data.get("path", "")
	var status: String = file_data.get("status", "M")

	# Get icon and color for status
	var status_display := _get_status_display(status)

	# Column 0: Checkbox + File path + Icon
	item.set_cell_mode(0, TreeItem.CELL_MODE_CHECK)
	item.set_checked(0, staged)
	item.set_editable(0, true)
	item.set_text(0, "  " + file_path)
	item.set_icon(0, status_display.icon)
	item.set_icon_modulate(0, status_display.color)

	# Column 1: Status badge
	item.set_text(1, status)
	item.set_text_alignment(1, HORIZONTAL_ALIGNMENT_CENTER)

	# Store file path for event handlers
	item.set_metadata(0, file_path)

	return item


func _get_status_display(status: String) -> Dictionary:
	"""Get icon and color for a status code (combined to avoid duplication)"""
	match status:
		"M":
			return {"icon": ICON_FILE, "color": COLOR_MODIFIED}
		"A":
			return {"icon": ICON_FILE_PLUS, "color": COLOR_ADDED}
		"D":
			return {"icon": ICON_FILE_MINUS, "color": COLOR_DELETED}
		"??":
			return {"icon": ICON_FILE_PLUS, "color": COLOR_UNTRACKED}
		_:
			return {"icon": ICON_FILE, "color": Color.WHITE}


# File Staging

func _on_file_tree_item_activated() -> void:
	var selected := file_tree.get_selected()
	if not selected or not selected.get_metadata(0):
		return

	var file_path: String = selected.get_metadata(0)
	var is_checked := selected.is_checked(0)

	if is_checked:
		stage_file(file_path)
	else:
		unstage_file(file_path)


func stage_file(file_path: String) -> void:
	if _is_operation_pending:
		return

	_is_operation_pending = true
	var files := PackedStringArray([file_path])
	_api_client.git_add_files(files)


func unstage_file(file_path: String) -> void:
	if _is_operation_pending:
		return

	_is_operation_pending = true
	var files := PackedStringArray([file_path])
	_api_client.git_restore_files(files)


# Commit Workflow

func _on_commit_button_pressed() -> void:
	commit_changes()


func commit_changes() -> void:
	if _is_operation_pending:
		return

	if not _validate_commit_message():
		return

	if not _has_staged_files():
		_show_alert("No files staged for commit", "Cannot Commit")
		return

	var message := commit_message_edit.text.strip_edges()

	# Pause polling during commit
	_is_polling_active = false
	polling_timer.stop()

	_is_operation_pending = true
	commit_button.disabled = true

	# Empty array = commit all staged files
	_api_client.git_commit(message, PackedStringArray())


func _validate_commit_message() -> bool:
	# Strip edges first, then validate the trimmed message
	var message := commit_message_edit.text.strip_edges()

	if message.is_empty():
		_show_alert("Commit message cannot be empty", "Invalid Message")
		commit_message_edit.grab_focus()
		return false

	# Check length AFTER stripping to prevent whitespace-padded short messages
	if message.length() < MIN_COMMIT_MESSAGE_LENGTH:
		_show_alert("Commit message too short (minimum %d characters)" % MIN_COMMIT_MESSAGE_LENGTH, "Invalid Message")
		commit_message_edit.grab_focus()
		return false

	return true


func _has_staged_files() -> bool:
	return _staged_files.size() > 0


func _on_git_operation_completed(operation: String, success: bool, message: String) -> void:
	_is_operation_pending = false

	match operation:
		"git_commit":
			if success:
				_clear_commit_message()
				_show_alert("Commit created successfully", "Success")
				commit_created.emit(message)
			else:
				_show_alert("Failed: %s" % message, "Commit Failed")

			commit_button.disabled = false
			_is_polling_active = true
			polling_timer.start()
			refresh_status()

		"git_add", "git_restore":
			if not success:
				_show_alert("Failed: %s" % message, "Git Operation Failed")
			refresh_status()


func _clear_commit_message() -> void:
	commit_message_edit.text = ""
	commit_message_edit.grab_focus()


# Polling & Refresh

func _on_polling_timer_timeout() -> void:
	# Only trigger if polling is active; refresh_status handles operation check atomically
	if _is_polling_active:
		refresh_status()


func refresh_status() -> void:
	# Atomic check: all conditions checked together to prevent race conditions
	if not _api_client or _is_operation_pending or not _is_polling_active:
		return

	# Debounce refreshes: queue if called too frequently (last call wins)
	var now := Time.get_ticks_msec() / 1000.0
	if now - _last_refresh_time < 1.0:
		# Queue refresh to execute after debounce delay
		_refresh_queued = true
		if _refresh_debounce_timer:
			_refresh_debounce_timer.start()
		return

	# Execute refresh immediately
	_refresh_queued = false
	_last_refresh_time = now
	_api_client.get_git_status()


func _on_refresh_debounce_timeout() -> void:
	# Execute queued refresh after debounce delay
	if _refresh_queued:
		_refresh_queued = false
		_last_refresh_time = Time.get_ticks_msec() / 1000.0
		if _api_client and not _is_operation_pending and _is_polling_active:
			_api_client.get_git_status()


func _on_refresh_button_pressed() -> void:
	refresh_status()


# AI Commit Message

func _on_ai_message_button_pressed() -> void:
	generate_ai_message()


func generate_ai_message() -> void:
	if not _has_staged_files() or _is_operation_pending:
		return

	_is_operation_pending = true
	ai_message_button.disabled = true

	# Use keys directly instead of creating intermediate array
	var staged_file_list: Array = Array(_staged_files.keys())

	_api_client.generate_commit_message(staged_file_list, "")


func _on_ai_commit_message_received(data: Dictionary) -> void:
	_is_operation_pending = false
	ai_message_button.disabled = false

	var message: String = data.get("message", "")
	if not message.is_empty():
		commit_message_edit.text = message
		commit_message_edit.grab_focus()
	else:
		_show_alert("Failed to generate commit message", "AI Error")


# UI State Management

func _update_button_states() -> void:
	var has_staged := _has_staged_files()
	var has_message := not commit_message_edit.text.strip_edges().is_empty()

	commit_button.disabled = not (has_staged and has_message) or _is_operation_pending
	ai_message_button.disabled = not has_staged or _is_operation_pending
	refresh_button.disabled = _is_operation_pending


func _on_commit_message_text_changed() -> void:
	# Debounce text changes to prevent spam (200ms delay)
	if _debounce_timer:
		_debounce_timer.start()


func _on_debounce_timeout() -> void:
	# Called after debounce delay - update button states
	_update_button_states()


# Error Handling

func _on_api_error(error_message: String) -> void:
	_is_operation_pending = false
	push_error("API Error: %s" % error_message)

	if error_message.contains("connection") or error_message.contains("connect"):
		_show_alert("Backend server not running on port 8005", "Connection Error")
	else:
		_show_alert("Error: %s" % error_message, "API Error")

	_update_button_states()

	# Resume polling
	if polling_timer and polling_timer.is_stopped():
		_is_polling_active = true
		polling_timer.start()


# Helper Methods

func _show_alert(text: String, title: String) -> void:
	if OS.has_feature("editor"):
		var dialog := AcceptDialog.new()
		dialog.dialog_text = text
		dialog.title = title
		add_child(dialog)
		dialog.popup_centered()
		# CRITICAL: Prevent memory leak - free dialog on ALL close methods
		dialog.confirmed.connect(dialog.queue_free)
		dialog.close_requested.connect(dialog.queue_free)
		dialog.canceled.connect(dialog.queue_free)  # ESC key
		dialog.popup_hide.connect(dialog.queue_free)  # Click outside
	else:
		print("[Alert] %s: %s" % [title, text])
