extends Node

# Test script for API client
# Usage: Create a scene with a Node, attach this script, and run (F6)


func _ready() -> void:
	print("=== Godot-Minds API Test Suite ===")
	print("")

	# Wait for autoloads to initialize
	await get_tree().process_frame

	# Test 1: Settings Manager
	print("Test 1: Settings Manager")
	print("  Server URL: ", GodotMindsSettings.get_server_url())
	print("  WebSocket URL: ", GodotMindsSettings.get_websocket_url())
	print("  AI Mode: ", GodotMindsSettings.get_ai_mode())
	print("  Polling Interval: ", GodotMindsSettings.get_polling_interval())
	print("")

	# Test 2: Connect API signals
	print("Test 2: Connecting API signals...")
	GodotMindsAPI.git_status_received.connect(_on_git_status)
	GodotMindsAPI.git_diff_received.connect(_on_git_diff)
	GodotMindsAPI.git_branches_received.connect(_on_git_branches)
	GodotMindsAPI.api_error.connect(_on_api_error)
	print("  Signals connected")
	print("")

	# Test 3: Git Status
	print("Test 3: Requesting git status...")
	var request_id := GodotMindsAPI.get_git_status()
	print("  Request ID: %d" % request_id)
	print("")

	# Test 4: Git Branches (after delay)
	await get_tree().create_timer(2.0).timeout
	print("Test 4: Requesting git branches...")
	GodotMindsAPI.get_git_branches()
	print("")

	# Test 5: Index Stats (after delay)
	await get_tree().create_timer(2.0).timeout
	print("Test 5: Requesting index stats...")
	GodotMindsAPI.get_index_stats()
	print("")


func _on_git_status(data: Dictionary) -> void:
	print("Git Status Received:")
	print("  Branch: %s" % data.get("branch", "unknown"))
	print("  Clean: %s" % data.get("is_clean", false))
	print("  Files: %d" % data.get("files", []).size())

	var files: Array = data.get("files", [])
	if files.size() > 0:
		print("  First 3 files:")
		for i in mini(3, files.size()):
			var file: Dictionary = files[i]
			print("    - %s (%s)" % [file.get("path", ""), file.get("status", "")])

		# Test diff on first file
		var first_file: Dictionary = files[0]
		var file_path: String = first_file.get("path", "")
		if not file_path.is_empty():
			print("")
			print("Test 3b: Requesting diff for: %s" % file_path)
			GodotMindsAPI.get_git_diff(file_path)
	print("")


func _on_git_diff(data: Dictionary) -> void:
	print("Git Diff Received:")
	print("  File: %s" % data.get("file_path", "unknown"))
	print("  Original length: %d chars" % data.get("original_content", "").length())
	print("  New length: %d chars" % data.get("new_content", "").length())
	print("  Diff length: %d chars" % data.get("diff_text", "").length())
	print("")


func _on_git_branches(data: Dictionary) -> void:
	print("Git Branches Received:")
	print("  Current: %s" % data.get("current_branch", "unknown"))

	var branches: Array = data.get("branches", [])
	print("  Total branches: %d" % branches.size())

	if branches.size() > 0:
		print("  Branches:")
		for branch in branches:
			var prefix := "  * " if branch == data.get("current_branch") else "    "
			print("%s%s" % [prefix, branch])
	print("")


func _on_api_error(error_message: String) -> void:
	push_error("API Error: %s" % error_message)
	print("ERROR: %s" % error_message)
	print("")
