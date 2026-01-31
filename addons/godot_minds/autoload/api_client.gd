# gdlint:ignore = max-public-methods
extends Node

# Signals - Git Operations
signal git_status_received(data: Dictionary)
signal git_diff_received(data: Dictionary)
signal git_branches_received(data: Dictionary)
signal git_log_received(data: Dictionary)
signal git_operation_completed(operation: String, success: bool, message: String)

# Signals - AI Operations
signal ai_response_received(data: Dictionary)
signal ai_chat_received(data: Dictionary)
signal ai_completion_received(data: Dictionary)
signal ai_commit_message_received(data: Dictionary)

# Signals - Index Operations
signal index_completed(data: Dictionary)
signal search_results_received(data: Dictionary)
signal index_stats_received(data: Dictionary)
signal index_cleared(success: bool)

# Signals - Watcher Operations
signal watcher_status_received(data: Dictionary)

# Signals - Editor Actions (AI-driven editor manipulation)
signal editor_action_completed(action: String, result: Dictionary)
signal editor_action_failed(action: String, error: String)

# Signals - WebSocket
signal websocket_connected()
signal websocket_disconnected()
signal ai_stream_token(token: String)
signal ai_stream_complete()

# Signals - General
signal api_error(error_message: String)

# Constants
const REQUEST_TIMEOUT := 30.0  # Default timeout for AI operations
const GIT_REQUEST_TIMEOUT := 10.0  # Shorter timeout for git operations
const MAX_ACTIVE_REQUESTS := 100
const MAX_WS_PACKETS_PER_FRAME := 10  # Limit WebSocket packets per frame

# Private variables
var _base_url: String = ""
var _ws_url: String = ""
var _request_id_counter: int = 0
var _active_requests: Dictionary = {}
var _ws_client: WebSocketPeer
var _ws_connected: bool = false

# Cached settings
var _settings_node: Node = null
var _cached_ai_mode: String = "direct"

# Editor actions service (set by plugin when available)
var _editor_actions = null  # EditorActions instance

# Reusable JSON parser to avoid allocations
var _json_parser: JSON


func _ready() -> void:
	_json_parser = JSON.new()  # Reusable parser
	_initialize_settings_cache()
	_initialize_urls()
	_initialize_websocket()
	# Enable process for timeout monitoring
	set_process(true)


func _exit_tree() -> void:
	# Clean up WebSocket properly
	if _ws_client:
		_ws_client.close()
		# Poll a few times to ensure close completes
		for i in range(10):
			_ws_client.poll()
			if _ws_client.get_ready_state() == WebSocketPeer.STATE_CLOSED:
				break
		_ws_client = null

	# Clean up any remaining active requests
	for request_id in _active_requests.keys():
		_cleanup_request(request_id)

	_active_requests.clear()


func _process(_delta: float) -> void:
	_cleanup_timed_out_requests()
	_process_websocket()


# Public Methods - Git Operations

func get_git_status() -> int:
	return _make_get_request("/git/status", "git_status", GIT_REQUEST_TIMEOUT)


func get_git_diff(file_path: String) -> int:
	var trimmed_path := file_path.strip_edges()
	if trimmed_path.is_empty():
		push_error("File path cannot be empty or whitespace-only for git diff")
		return -1

	var query := "?file_path=%s" % trimmed_path.uri_encode()
	return _make_get_request("/git/diff" + query, "git_diff", GIT_REQUEST_TIMEOUT)


func git_add_files(files: PackedStringArray) -> int:
	if files.is_empty():
		push_error("Files array cannot be empty for git add")
		return -1

	var body := {"files": Array(files)}
	return _make_post_request("/git/add", body, "git_add", GIT_REQUEST_TIMEOUT)


func git_restore_files(files: PackedStringArray) -> int:
	if files.is_empty():
		push_error("Files array cannot be empty for git restore")
		return -1

	var body := {"files": Array(files)}
	return _make_post_request("/git/restore", body, "git_restore", GIT_REQUEST_TIMEOUT)


func git_commit(message: String, files: PackedStringArray = []) -> int:
	if message.is_empty():
		push_error("Commit message cannot be empty")
		return -1

	var body := {
		"message": message,
		"files": Array(files) if files.size() > 0 else []
	}
	return _make_post_request("/git/commit", body, "git_commit", GIT_REQUEST_TIMEOUT)


func get_git_branches() -> int:
	return _make_get_request("/git/branches", "git_branches", GIT_REQUEST_TIMEOUT)


func git_checkout(branch: String, create_new: bool = false) -> int:
	if branch.is_empty():
		push_error("Branch name cannot be empty")
		return -1

	var body := {
		"branch": branch,
		"create_new": create_new
	}
	return _make_post_request("/git/checkout", body, "git_checkout", GIT_REQUEST_TIMEOUT)


func get_git_log(max_count: int = 20) -> int:
	var query := "?max_count=%d" % max_count
	return _make_get_request("/git/log" + query, "git_log", GIT_REQUEST_TIMEOUT)


# Public Methods - AI Operations

func ask_ai(
	prompt: String,
	file_path: String = "",
	file_content: String = "",
	selection: Dictionary = {},
	mode: String = ""
) -> int:
	if prompt.is_empty():
		push_error("Prompt cannot be empty")
		return -1

	var body := {
		"prompt": prompt,
		"file_path": file_path,
		"file_content": file_content,
		"selection": selection,
		"mode": mode if not mode.is_empty() else _get_safe_ai_mode()
	}
	return _make_post_request("/ai/ask", body, "ai_ask")


func chat_with_ai(message: String, history: Array = [], context_files: Array = []) -> int:
	if message.is_empty():
		push_error("Message cannot be empty")
		return -1

	var body := {
		"message": message,
		"history": history,
		"context_files": context_files,
		"mode": _get_safe_ai_mode()
	}
	return _make_post_request("/ai/chat", body, "ai_chat")


func get_completion(
	file_path: String,
	file_content: String,
	cursor_line: int,
	cursor_column: int
) -> int:
	if file_path.is_empty() or file_content.is_empty():
		push_error("File path and content are required for completion")
		return -1

	var body := {
		"file_path": file_path,
		"file_content": file_content,
		"cursor_line": cursor_line,
		"cursor_column": cursor_column,
		"mode": _get_safe_ai_mode()
	}
	return _make_post_request("/ai/complete", body, "ai_complete")


func generate_commit_message(staged_files: Array, diff_content: String = "") -> int:
	if staged_files.is_empty():
		push_error("Staged files array cannot be empty")
		return -1

	var body := {
		"staged_files": staged_files,
		"diff_content": diff_content,
		"mode": _get_safe_ai_mode()
	}
	return _make_post_request("/ai/generate/commit-message", body, "ai_commit_message")


# Public Methods - Index Operations

func index_project(project_path: String, force_reindex: bool = false) -> int:
	if project_path.is_empty():
		push_error("Project path cannot be empty")
		return -1

	var body := {
		"project_path": project_path,
		"force_reindex": force_reindex
	}
	return _make_post_request("/index", body, "index")


func search_code(query: String, max_results: int = 5) -> int:
	if query.is_empty():
		push_error("Search query cannot be empty")
		return -1

	var body := {
		"query": query,
		"max_results": max_results
	}
	return _make_post_request("/index/search", body, "search")


func get_index_stats() -> int:
	return _make_get_request("/index/stats", "index_stats")


func clear_index() -> int:
	return _make_post_request("/index/clear", {}, "index_clear")


# Public Methods - Watcher Operations

func start_watcher(path: String) -> int:
	if path.is_empty():
		push_error("Watcher path cannot be empty")
		return -1

	var body := {"path": path}
	return _make_post_request("/watcher/start", body, "watcher_start")


func stop_watcher() -> int:
	return _make_post_request("/watcher/stop", {}, "watcher_stop")


func get_watcher_status() -> int:
	return _make_get_request("/watcher/status", "watcher_status")


# Public Methods - WebSocket

func connect_websocket() -> void:
	if not _ws_client:
		push_error("WebSocket client not initialized")
		return

	if _ws_connected:
		push_warning("WebSocket already connected")
		return

	var error := _ws_client.connect_to_url(_ws_url)
	if error != OK:
		push_error("Failed to connect WebSocket: %d" % error)
		api_error.emit("Failed to connect to WebSocket server")
		return

	# Enable _process() to poll WebSocket
	set_process(true)
	print("[GodotMindsAPI] WebSocket connection initiated")


func disconnect_websocket() -> void:
	if not _ws_client:
		return

	_ws_client.close()
	_ws_connected = false

	# Disable _process() when WebSocket is not needed
	set_process(false)

	websocket_disconnected.emit()


func send_websocket_message(message_type: String, data: Dictionary) -> void:
	if not _ws_connected:
		push_error("WebSocket not connected")
		return

	var message := {
		"type": message_type,
		"data": data
	}

	var json_string := JSON.stringify(message)
	var error := _ws_client.send_text(json_string)

	if error != OK:
		push_error("Failed to send WebSocket message: %d" % error)


func ask_ai_stream(prompt: String, context: String = "") -> void:
	var data := {
		"prompt": prompt,
		"context": context,
		"mode": _get_safe_ai_mode()
	}
	send_websocket_message("ai_ask", data)


# Private Methods - Initialization

func _initialize_settings_cache() -> void:
	"""Cache settings node to avoid repeated lookups"""
	if has_node("/root/GodotMindsSettings"):
		_settings_node = get_node("/root/GodotMindsSettings")
		if _settings_node and _settings_node.has_method("get_ai_mode"):
			_cached_ai_mode = _settings_node.get_ai_mode()
	else:
		push_warning("[GodotMindsAPI] GodotMindsSettings not found, using defaults")


func _initialize_urls() -> void:
	_base_url = _get_safe_server_url()
	_ws_url = _get_safe_websocket_url()

	print("[GodotMindsAPI] Initialized with base URL: %s" % _base_url)


func _initialize_websocket() -> void:
	_ws_client = WebSocketPeer.new()
	print("[GodotMindsAPI] WebSocket client initialized")


# Private Methods - Safe Settings Access

func _get_safe_server_url() -> String:
	"""Get server URL from cached settings"""
	if _settings_node and _settings_node.has_method("get_server_url"):
		return _settings_node.get_server_url()
	return "http://127.0.0.1:8005"


func _get_safe_websocket_url() -> String:
	"""Get WebSocket URL from cached settings"""
	if _settings_node and _settings_node.has_method("get_websocket_url"):
		return _settings_node.get_websocket_url()
	return "ws://127.0.0.1:8005/ws"


func _get_safe_ai_mode() -> String:
	"""Get AI mode from cache (updated in _ready)"""
	return _cached_ai_mode


# Private Methods - HTTP Requests

func _make_get_request(
	endpoint: String, request_type: String, timeout: float = REQUEST_TIMEOUT
) -> int:
	var url := _base_url + endpoint
	return _make_request(url, HTTPClient.METHOD_GET, [], "", request_type, timeout)


func _make_post_request(
	endpoint: String, body: Dictionary, request_type: String,
	timeout: float = REQUEST_TIMEOUT
) -> int:
	var url := _base_url + endpoint
	var headers := ["Content-Type: application/json"]
	var json_body := JSON.stringify(body)
	return _make_request(
		url, HTTPClient.METHOD_POST, headers, json_body, request_type, timeout
	)


func _make_request(
	url: String,
	method: int,
	headers: PackedStringArray,
	body: String,
	request_type: String,
	timeout: float = REQUEST_TIMEOUT
) -> int:
	# Check if we've hit the maximum number of active requests
	if _active_requests.size() >= MAX_ACTIVE_REQUESTS:
		var err_msg := "Maximum active requests reached (%d). Request rejected."
		push_error(err_msg % MAX_ACTIVE_REQUESTS)
		api_error.emit("Too many active requests. Please try again later.")
		return -1

	var http_request := HTTPRequest.new()
	add_child(http_request)

	var request_id := _request_id_counter
	_request_id_counter += 1

	# Wrap counter to avoid overflow (extremely unlikely but safe)
	if _request_id_counter > 1000000:
		_request_id_counter = 0

	http_request.timeout = timeout

	# Make the request FIRST, before adding to active requests
	var error := http_request.request(url, headers, method, body)

	if error != OK:
		push_error("Failed to make request to %s: %d" % [url, error])
		# Clean up immediately - node was never added to active requests
		http_request.queue_free()
		return -1

	# Only connect signal and add to active requests if request succeeded
	http_request.request_completed.connect(
		_on_request_completed.bind(request_id)
	)

	_active_requests[request_id] = {
		"node": http_request,
		"type": request_type,
		"url": url,
		"start_time": Time.get_ticks_msec() / 1000.0  # For timeout tracking
	}

	return request_id


func _on_request_completed(
	result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
	request_id: int
) -> void:
	if not _active_requests.has(request_id):
		push_error("Received response for unknown request ID: %d" % request_id)
		return

	var request_info: Dictionary = _active_requests[request_id]
	var request_type: String = request_info.get("type", "unknown")

	# Check for network errors
	if result != HTTPRequest.RESULT_SUCCESS:
		var error_msg := "Request failed: %s (result=%d)" % [request_info.get("url", ""), result]
		push_error(error_msg)
		api_error.emit(error_msg)
		_cleanup_request(request_id)
		return

	# Check for HTTP errors
	if response_code < 200 or response_code >= 300:
		var error_msg := "HTTP error %d: %s" % [response_code, request_info.get("url", "")]
		push_error(error_msg)
		api_error.emit(error_msg)
		_cleanup_request(request_id)
		return

	# Parse JSON response (use reusable parser to avoid allocations)
	var body_string := body.get_string_from_utf8()
	var parse_error := _json_parser.parse(body_string)

	if parse_error != OK:
		var error_msg := "Failed to parse JSON response: %s" % _json_parser.get_error_message()
		push_error(error_msg)
		api_error.emit(error_msg)
		_cleanup_request(request_id)
		return

	var data: Dictionary = _json_parser.data if _json_parser.data is Dictionary else {}

	# Route to appropriate signal based on request type
	_route_response(request_type, data)

	_cleanup_request(request_id)


func _route_response(request_type: String, data: Dictionary) -> void:
	match request_type:
		# Git operations
		"git_status":
			git_status_received.emit(data)
		"git_diff":
			git_diff_received.emit(data)
		"git_branches":
			git_branches_received.emit(data)
		"git_log":
			git_log_received.emit(data)
		"git_add", "git_restore", "git_commit", "git_checkout":
			var success: bool = data.get("success", false)
			var message: String = data.get("message", "")
			git_operation_completed.emit(request_type, success, message)

		# AI operations
		"ai_ask":
			ai_response_received.emit(data)
		"ai_chat":
			ai_chat_received.emit(data)
		"ai_complete":
			ai_completion_received.emit(data)
		"ai_commit_message":
			ai_commit_message_received.emit(data)

		# Index operations
		"index":
			index_completed.emit(data)
		"search":
			search_results_received.emit(data)
		"index_stats":
			index_stats_received.emit(data)
		"index_clear":
			var success: bool = data.get("success", false)
			index_cleared.emit(success)

		# Watcher operations
		"watcher_start", "watcher_stop", "watcher_status":
			watcher_status_received.emit(data)

		_:
			push_warning("Unknown request type: %s" % request_type)


func _cleanup_timed_out_requests() -> void:
	"""Clean up requests that have exceeded timeout + grace period (5s)"""
	var now := Time.get_ticks_msec() / 1000.0
	var timeout_threshold := REQUEST_TIMEOUT + 5.0  # 35 seconds total

	var timed_out_requests: Array[int] = []

	for request_id in _active_requests.keys():
		var request_info: Dictionary = _active_requests[request_id]
		if request_info.has("start_time"):
			var elapsed := now - request_info.start_time
			if elapsed > timeout_threshold:
				timed_out_requests.append(request_id)
				var msg := "[GodotMindsAPI] Cleaning up timed-out request %d"
				push_warning(msg % request_id)

	# Clean up in separate loop to avoid modifying dict during iteration
	for request_id in timed_out_requests:
		_cleanup_request(request_id)
		api_error.emit("Request timed out")


func _cleanup_request(request_id: int) -> void:
	if not _active_requests.has(request_id):
		return

	var request_info: Dictionary = _active_requests[request_id]
	var http_node: HTTPRequest = request_info.get("node")

	if http_node and is_instance_valid(http_node):
		# Disconnect signal before freeing to prevent memory leaks
		if http_node.request_completed.is_connected(_on_request_completed):
			http_node.request_completed.disconnect(_on_request_completed)

		# Queue the node for deletion
		http_node.queue_free()

	_active_requests.erase(request_id)


# Private Methods - WebSocket

func _process_websocket() -> void:
	if not _ws_client:
		return

	_ws_client.poll()
	var state := _ws_client.get_ready_state()

	match state:
		WebSocketPeer.STATE_CONNECTING:
			# Connection in progress, keep polling
			pass

		WebSocketPeer.STATE_OPEN:
			if not _ws_connected:
				_ws_connected = true
				websocket_connected.emit()
				print("[GodotMindsAPI] WebSocket connected")

			# Process available messages (limit per frame to prevent UI freezing)
			var packets_processed := 0
			var max_packets := MAX_WS_PACKETS_PER_FRAME
			while _ws_client.get_available_packet_count() > 0 and packets_processed < max_packets:
				var packet := _ws_client.get_packet()
				var message := packet.get_string_from_utf8()
				_handle_websocket_message(message)
				packets_processed += 1

		WebSocketPeer.STATE_CLOSING:
			# Connection is closing, keep polling until fully closed
			pass

		WebSocketPeer.STATE_CLOSED:
			if _ws_connected:
				_ws_connected = false
				websocket_disconnected.emit()
				print("[GodotMindsAPI] WebSocket disconnected")

			# Disable _process() since WebSocket is no longer active
			set_process(false)


func _handle_websocket_message(message: String) -> void:
	# Use reusable JSON parser
	var error := _json_parser.parse(message)

	if error != OK:
		push_error("Failed to parse WebSocket message: %s" % _json_parser.get_error_message())
		return

	if not _json_parser.data is Dictionary:
		push_error("WebSocket message is not a dictionary")
		return

	var data: Dictionary = _json_parser.data
	var message_type: String = data.get("type", "")

	match message_type:
		"ai_stream_token":
			var token: String = data.get("token", "")
			ai_stream_token.emit(token)
		"ai_stream_complete":
			ai_stream_complete.emit()
		"editor_action":
			# Handle editor action request from backend
			_handle_editor_action(data)
		"error":
			var error_msg: String = data.get("message", "Unknown WebSocket error")
			api_error.emit(error_msg)
		_:
			push_warning("Unknown WebSocket message type: %s" % message_type)


func set_editor_actions(actions) -> void:
	"""Set the EditorActions instance (called by plugin)"""
	_editor_actions = actions


func _handle_editor_action(data: Dictionary) -> void:
	"""Handle incoming editor action from backend and respond"""
	var request_id: String = data.get("request_id", "")
	var action: String = data.get("action", "")
	var action_data: Dictionary = data.get("data", {})
	
	if not _editor_actions:
		_send_editor_response(request_id, {"error": "EditorActions not initialized"})
		return
	
	var result: Dictionary = {}
	
	# Route to appropriate EditorActions method
	match action:
		"create_node":
			result = _editor_actions.create_node(
				action_data.get("parent_path", ""),
				action_data.get("node_class", ""),
				action_data.get("node_name", ""),
				action_data.get("properties", {})
			)
		"delete_node":
			result = _editor_actions.delete_node(action_data.get("node_path", ""))
		"rename_node":
			result = _editor_actions.rename_node(
				action_data.get("node_path", ""),
				action_data.get("new_name", "")
			)
		"reparent_node":
			result = _editor_actions.reparent_node(
				action_data.get("node_path", ""),
				action_data.get("new_parent_path", "")
			)
		"get_property":
			result = _editor_actions.get_property(
				action_data.get("node_path", ""),
				action_data.get("property", "")
			)
		"set_property":
			result = _editor_actions.set_property(
				action_data.get("node_path", ""),
				action_data.get("property", ""),
				action_data.get("value")
			)
		"attach_resource":
			result = _editor_actions.attach_resource(
				action_data.get("node_path", ""),
				action_data.get("property", ""),
				action_data.get("resource_path", "")
			)
		"create_resource":
			result = _editor_actions.create_resource(
				action_data.get("resource_type", ""),
				action_data.get("properties", {}),
				action_data.get("save_path", "")
			)
		"get_scene_tree":
			result = _editor_actions.get_scene_tree()
		"instantiate_scene":
			result = _editor_actions.instantiate_scene(
				action_data.get("parent_path", ""),
				action_data.get("scene_path", ""),
				action_data.get("instance_name", "")
			)
		"save_scene":
			result = _editor_actions.save_scene()
		"attach_script":
			result = _editor_actions.attach_script(
				action_data.get("node_path", ""),
				action_data.get("script_path", ""),
				action_data.get("create_content", "")
			)
		"connect_signal":
			result = _editor_actions.connect_signal(
				action_data.get("source_path", ""),
				action_data.get("signal_name", ""),
				action_data.get("target_path", ""),
				action_data.get("method_name", "")
			)
		"get_selection":
			result = _editor_actions.get_selection()
		"set_selection":
			result = _editor_actions.set_selection(action_data.get("node_paths", []))
		"spawn_grid":
			var spacing = action_data.get("spacing", [1, 0, 1])
			if spacing is Array and spacing.size() >= 3:
				result = _editor_actions.spawn_grid(
					action_data.get("parent_path", ""),
					action_data.get("node_class", ""),
					action_data.get("rows", 1),
					action_data.get("cols", 1),
					Vector3(spacing[0], spacing[1], spacing[2]),
					action_data.get("name_prefix", "Tile")
				)
			else:
				result = {"error": "Invalid spacing array"}
		"spawn_random_in_area":
			var bounds_min = action_data.get("bounds_min", [0, 0, 0])
			var bounds_max = action_data.get("bounds_max", [10, 0, 10])
			if bounds_min is Array and bounds_min.size() >= 3 and bounds_max is Array and bounds_max.size() >= 3:
				result = _editor_actions.spawn_random_in_area(
					action_data.get("parent_path", ""),
					action_data.get("node_class", ""),
					action_data.get("count", 1),
					Vector3(bounds_min[0], bounds_min[1], bounds_min[2]),
					Vector3(bounds_max[0], bounds_max[1], bounds_max[2]),
					action_data.get("name_prefix", "Scatter")
				)
			else:
				result = {"error": "Invalid bounds arrays"}
		"spawn_along_path":
			result = _editor_actions.spawn_along_path(
				action_data.get("parent_path", ""),
				action_data.get("node_class", ""),
				action_data.get("points", []),
				action_data.get("name_prefix", "PathPoint")
			)
		"get_pending_changes":
			result = {"changes": _editor_actions.get_pending_changes()}
		"clear_pending_changes":
			_editor_actions.clear_pending_changes()
			result = {"success": true}
		"undo_last":
			result = _editor_actions.undo_last()
		_:
			result = {"error": "Unknown action: " + action}
	
	# Send response back to backend
	_send_editor_response(request_id, result)
	
	# Emit signal for local listeners
	if result.get("success", false):
		editor_action_completed.emit(action, result)
	else:
		editor_action_failed.emit(action, result.get("error", "Unknown error"))


func _send_editor_response(request_id: String, result: Dictionary) -> void:
	"""Send editor action response back to backend"""
	if not _ws_connected:
		return
	
	var response := {
		"type": "editor_response",
		"request_id": request_id,
		"result": result
	}
	
	var json_string := JSON.stringify(response)
	_ws_client.send_text(json_string)
