# Godot-Minds Plugin

AI-powered Godot plugin with Git integration, Cmd+K editing, and RAG code search.

## Installation

1. Ensure the Python backend is running on `http://127.0.0.1:8005`
2. In Godot editor: **Project > Project Settings > Plugins**
3. Enable "Godot-Minds"

## Configuration

Settings are available in **Editor > Editor Settings > Godot Minds**:

- **server/host**: Backend server host (default: 127.0.0.1)
- **server/port**: Backend server port (default: 8005)
- **ai/mode**: AI provider mode (direct, opencode, ollama)
- **api_keys/anthropic**: Anthropic API key (masked)
- **api_keys/openai**: OpenAI API key (masked)
- **api_keys/opencode**: OpenCode API key (masked)
- **ui/polling_interval**: Git status polling interval in seconds (default: 2.0)

## Architecture

### Autoloads

**GodotMindsSettings** (settings_manager.gd)
- Manages EditorSettings for user preferences
- Provides methods: `get_server_url()`, `get_ai_mode()`, `get_api_key()`
- Emits `settings_changed` signal on modifications

**GodotMindsAPI** (api_client.gd)
- HTTP client for all backend endpoints
- WebSocket support for streaming AI responses
- Signal-based async API
- Request tracking with unique IDs

### Signals

**Git Operations**
- `git_status_received(data: Dictionary)`
- `git_diff_received(data: Dictionary)`
- `git_branches_received(data: Dictionary)`
- `git_log_received(data: Dictionary)`
- `git_operation_completed(operation: String, success: bool, message: String)`

**AI Operations**
- `ai_response_received(data: Dictionary)`
- `ai_chat_received(data: Dictionary)`
- `ai_completion_received(data: Dictionary)`
- `ai_commit_message_received(data: Dictionary)`

**Index Operations**
- `index_completed(data: Dictionary)`
- `search_results_received(data: Dictionary)`
- `index_stats_received(data: Dictionary)`
- `index_cleared(success: bool)`

**WebSocket**
- `websocket_connected()`
- `websocket_disconnected()`
- `ai_stream_token(token: String)`
- `ai_stream_complete()`

**General**
- `api_error(error_message: String)`

## Usage Examples

### Get Git Status

```gdscript
func _ready() -> void:
    GodotMindsAPI.git_status_received.connect(_on_git_status)
    GodotMindsAPI.get_git_status()

func _on_git_status(data: Dictionary) -> void:
    print("Branch: ", data.get("branch"))
    print("Clean: ", data.get("is_clean"))
    for file in data.get("files", []):
        print("  %s: %s" % [file.get("path"), file.get("status")])
```

### Ask AI

```gdscript
func _ready() -> void:
    GodotMindsAPI.ai_response_received.connect(_on_ai_response)

func ask_ai_question() -> void:
    var prompt := "How do I implement double jump in Godot?"
    GodotMindsAPI.ask_ai(prompt)

func _on_ai_response(data: Dictionary) -> void:
    print("Response: ", data.get("response"))
    print("Code: ", data.get("code"))
```

### Search Code

```gdscript
func _ready() -> void:
    GodotMindsAPI.search_results_received.connect(_on_search_results)

func search_for_function() -> void:
    GodotMindsAPI.search_code("player movement", 10)

func _on_search_results(data: Dictionary) -> void:
    var results: Array = data.get("results", [])
    for result in results:
        print("%s: %s" % [result.get("file"), result.get("snippet")])
```

## Testing

Run the test script:

1. Create a new scene in Godot
2. Add a Node and attach `addons/godot_minds/test_api.gd`
3. Ensure backend is running: `cd backend && python main.py`
4. Run the scene (F6)
5. Check Output panel for results

## Backend Requirements

The Python backend must be running with these endpoints:

- **Git**: `/git/status`, `/git/diff`, `/git/add`, `/git/commit`, `/git/branches`, `/git/checkout`, `/git/log`
- **AI**: `/ai/ask`, `/ai/chat`, `/ai/complete`, `/ai/generate/commit-message`
- **Index**: `/index`, `/index/search`, `/index/stats`, `/index/clear`
- **Watcher**: `/watcher/start`, `/watcher/stop`, `/watcher/status`
- **WebSocket**: `ws://127.0.0.1:8005/ws`

## Development Status

**Phase 2: Plugin Structure** (Current)
- ✅ Plugin configuration and entry point
- ✅ Settings manager autoload
- ✅ API client autoload (HTTP + WebSocket)
- ✅ Directory structure

**Phase 3: UI Components** (Next)
- ⏳ Source Control Dock
- ⏳ Cmd+K popup
- ⏳ Chat panel
- ⏳ Settings UI

## License

[Your License Here]
