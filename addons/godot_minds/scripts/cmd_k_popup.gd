@tool
class_name CmdKPopup
extends Window

# Signals
signal ai_request_submitted(prompt: String, result: Dictionary)
signal ai_request_cancelled()

# Constants
const OPEN_DEBOUNCE_MS := 300

# State
var _api_client: Node = null
var _editor_interface: EditorInterface = null
var _is_loading: bool = false
var _last_open_time: int = 0
var _is_closing: bool = false  # Guard against double-close

# Captured editor context
var _current_file_path: String = ""
var _current_file_content: String = ""
var _current_selection: Dictionary = {}

# @onready nodes
@onready var context_label: Label = %ContextLabel
@onready var prompt_line_edit: LineEdit = %PromptLineEdit
@onready var loading_indicator: Label = %LoadingIndicator
@onready var error_label: Label = %ErrorLabel
@onready var cancel_button: Button = %CancelButton


func _ready() -> void:
	# Connect window signals
	close_requested.connect(_on_close_requested)

	# Connect UI signals (with null checks for safety)
	if prompt_line_edit:
		prompt_line_edit.text_submitted.connect(_on_prompt_submitted)
	if cancel_button:
		cancel_button.pressed.connect(_close_popup)


func _unhandled_key_input(event: InputEvent) -> void:
	# Close on Escape key
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		_close_popup()
		get_viewport().set_input_as_handled()


func _exit_tree() -> void:
	# Disconnect API signals to prevent memory leaks
	_disconnect_api_signals()

	# Clear large data and references
	_current_file_content = ""
	_current_selection = {}
	_api_client = null
	_editor_interface = null


func setup(api_client: Node, editor_interface: EditorInterface) -> void:
	"""Initialize the popup with dependencies."""
	_api_client = api_client
	_editor_interface = editor_interface

	# Connect API signals (with instance validity check)
	if _api_client and is_instance_valid(_api_client):
		if not _api_client.ai_response_received.is_connected(_on_ai_response_received):
			_api_client.ai_response_received.connect(_on_ai_response_received)
		if not _api_client.api_error.is_connected(_on_api_error):
			_api_client.api_error.connect(_on_api_error)


func show_popup() -> void:
	"""Capture context and show the popup window."""
	# Debounce rapid opens (300ms guard)
	var now := Time.get_ticks_msec()
	if now - _last_open_time < OPEN_DEBOUNCE_MS:
		return
	_last_open_time = now

	# Capture editor context before showing
	_capture_editor_context()

	# Update context label
	if context_label:
		if _current_file_path.is_empty():
			context_label.text = "No file open"
		else:
			# Show filename only for brevity
			var filename := _current_file_path.get_file()
			if not _current_selection.is_empty():
				context_label.text = "%s (selection)" % filename
			else:
				context_label.text = filename

	# Reset UI state
	_reset_ui()

	# Show the window
	popup_centered()

	# Focus the input field
	if prompt_line_edit:
		prompt_line_edit.grab_focus()


func _capture_editor_context() -> void:
	"""Capture the current file, content, and selection from the script editor."""
	_current_file_path = ""
	_current_file_content = ""
	_current_selection = {}

	if not _editor_interface:
		return

	var script_editor := _editor_interface.get_script_editor()
	if not script_editor:
		return

	var current_script := script_editor.get_current_script()
	if not current_script:
		return

	# Get file path
	_current_file_path = current_script.resource_path
	if _current_file_path.begins_with("res://"):
		_current_file_path = _current_file_path.substr(6)  # Remove "res://" prefix

	# Get the CodeEdit from the current editor
	var current_editor := script_editor.get_current_editor()
	if not current_editor:
		return

	# Find the CodeEdit child (script editor uses TextEdit/CodeEdit)
	var code_edit := _find_code_edit(current_editor)
	if not code_edit:
		return

	# Get full content
	_current_file_content = code_edit.text

	# Check for selection
	if code_edit.has_selection():
		var from_line := code_edit.get_selection_from_line()
		var from_col := code_edit.get_selection_from_column()
		var to_line := code_edit.get_selection_to_line()
		var to_col := code_edit.get_selection_to_column()
		var selected_text := code_edit.get_selected_text()

		_current_selection = {
			"from_line": from_line,
			"from_column": from_col,
			"to_line": to_line,
			"to_column": to_col,
			"text": selected_text
		}


func _find_code_edit(node: Node) -> CodeEdit:
	"""Find CodeEdit in node tree using iterative BFS (avoids stack overflow on deep trees)."""
	if node is CodeEdit:
		return node

	# Use iterative BFS instead of recursion for safety
	var queue: Array[Node] = [node]
	while not queue.is_empty():
		var current := queue.pop_front()
		if current is CodeEdit:
			return current
		queue.append_array(current.get_children())

	return null


func _on_prompt_submitted(prompt: String) -> void:
	"""Handle prompt submission."""
	if prompt.strip_edges().is_empty():
		_show_error("Please enter a prompt")
		return

	if not _api_client or not is_instance_valid(_api_client):
		_show_error("API client not available")
		return

	if _current_file_path.is_empty():
		_show_error("No file open in script editor")
		return

	# Show loading state
	_set_loading(true)

	# Call the AI API
	_api_client.ask_ai(
		prompt,
		_current_file_path,
		_current_file_content,
		_current_selection
	)


func _on_ai_response_received(data: Dictionary) -> void:
	"""Handle AI response from API."""
	# Guard: Popup may have been closed while waiting for response
	if not is_instance_valid(self) or not is_inside_tree():
		return

	_set_loading(false)

	# Check for errors in response
	var error_msg: String = data.get("error", "")
	if not error_msg.is_empty():
		_show_error(error_msg)
		return

	# Get the AI-generated content
	var ai_response: String = data.get("response", "")
	if ai_response.is_empty():
		_show_error("AI returned empty response")
		return

	# Build result dictionary for the diff window
	var result := {
		"file_path": _current_file_path,
		"original_content": _current_file_content,
		"new_content": ai_response,
		"selection": _current_selection,
		"prompt": prompt_line_edit.text if prompt_line_edit else ""
	}

	# Emit signal with result
	ai_request_submitted.emit(prompt_line_edit.text if prompt_line_edit else "", result)

	# Close the popup
	_close_popup()


func _on_api_error(error_message: String) -> void:
	"""Handle API errors."""
	# Guard: Popup may have been closed while waiting for response
	if not is_instance_valid(self) or not is_inside_tree():
		return

	_set_loading(false)
	_show_error(error_message)


func _set_loading(loading: bool) -> void:
	"""Update loading state and UI."""
	_is_loading = loading

	if loading_indicator:
		loading_indicator.visible = loading

	if error_label:
		error_label.visible = false

	if prompt_line_edit:
		prompt_line_edit.editable = not loading

	if cancel_button:
		cancel_button.disabled = loading


func _show_error(message: String) -> void:
	"""Display an error message."""
	if error_label:
		error_label.text = message
		error_label.visible = true

	if loading_indicator:
		loading_indicator.visible = false


func _reset_ui() -> void:
	"""Reset UI to initial state."""
	if prompt_line_edit:
		prompt_line_edit.text = ""
		prompt_line_edit.editable = true

	if loading_indicator:
		loading_indicator.visible = false

	if error_label:
		error_label.visible = false

	if cancel_button:
		cancel_button.disabled = false

	_is_loading = false


func _on_close_requested() -> void:
	"""Handle window close button."""
	_close_popup()


func _close_popup() -> void:
	"""Clean up and close the popup."""
	# Guard against double-close
	if _is_closing:
		return
	_is_closing = true

	# Disconnect signals before closing
	_disconnect_api_signals()

	# Emit cancelled signal if we're not loading (user cancelled)
	if not _is_loading:
		ai_request_cancelled.emit()

	# Clear large data to help GC (optional but good practice)
	_current_file_content = ""
	_current_selection = {}

	# Clear references
	_api_client = null
	_editor_interface = null

	hide()
	queue_free()


func _disconnect_api_signals() -> void:
	"""Safely disconnect all API signals."""
	if _api_client and is_instance_valid(_api_client):
		if _api_client.ai_response_received.is_connected(_on_ai_response_received):
			_api_client.ai_response_received.disconnect(_on_ai_response_received)
		if _api_client.api_error.is_connected(_on_api_error):
			_api_client.api_error.disconnect(_on_api_error)
