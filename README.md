# Godot-AI-Code

> AI-powered development assistant for Godot Engine with Git integration, intelligent code editing, and multi-language support (GDScript/C#/C++)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Godot 4.x](https://img.shields.io/badge/godot-4.x-blue.svg)](https://godotengine.org/)

---

## Features

### AI-Powered Coding
- **Cmd+K Quick Edit**: Popup AI assistant for instant code modifications
- **AI Chat Panel**: Full conversation mode for complex tasks and explanations
- **Inline Ghost Completions**: Real-time code suggestions as you type (like GitHub Copilot)
- **Multi-File Editing**: AI can suggest changes across multiple files simultaneously

### Git Integration
- **Visual Source Control**: VS Code-style Git panel directly in Godot editor
- **Side-by-Side Diff Viewer**: Review changes with syntax highlighting
- **AI Commit Messages**: Automatically generate meaningful commit messages
- **Branch Management**: Switch branches, stash changes, view history

### Flexible AI Backends
Choose your preferred AI provider:
- **Direct API Mode**: Claude, GPT-4, Gemini (requires API keys)
- **OpenCode Mode**: Use existing ChatGPT+, Copilot, or Claude Pro subscriptions
- **Local Ollama Mode**: Free, private, offline-capable with local models

### Development Tools
- **Polyglot Support**: GDScript, C#, C++ with context-aware assistance
- **Build Integration**: Compile and auto-fix errors with AI suggestions
- **RAG Code Search**: Semantic search through your entire codebase
- **Auto-Sync Indexing**: File watcher keeps code index up-to-date

---

##  Quick Start

### Prerequisites
- Python 3.10+
- Godot 4.x
- Git

### Installation

#### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/godotaiide.git
cd godotaiide
```

#### 2. Setup Python Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys (optional)
```

#### 3. Start the Backend Server
```bash
uvicorn main:app --reload --port 8000
```

#### 4. Install Godot Plugin
1. Copy `addons/godot_minds/` to your Godot project's `addons/` folder
2. Open Godot Editor → Project → Project Settings → Plugins
3. Enable "Godot-Minds"

#### 5. Configure AI Backend
- Open Godot → Editor → Editor Settings → Godot-Minds
- Choose AI mode (Direct API / OpenCode / Ollama)
- Add API keys if using Direct API mode

---

## 📖 Usage

### Quick AI Edit (Cmd+K)
1. Open any script file in Godot
2. Press `Ctrl+K` (or `Cmd+K` on macOS)
3. Type your edit request (e.g., "Add jump mechanic")
4. Review changes in diff window → Accept or Reject

### Git Workflow
1. Make changes to your files
2. Open Source Control dock (bottom panel)
3. Review modified files
4. Click "AI Message" for auto-generated commit message
5. Click "Commit" or press `Ctrl+Enter`

### AI Chat
1. Open AI Chat panel (right dock)
2. Ask questions or request code changes
3. Reference files with `@filename.gd`
4. Click "Apply" on code suggestions to review in diff window

### Inline Completions
1. Start typing code
2. Pause briefly (500ms)
3. Ghost text suggestion appears
4. Press `Tab` to accept, `Escape` to dismiss

---

## Architecture

```
┌─────────────────────────────────┐
│     Godot Plugin (Client)       │  ← UI Layer (GDScript)
│  Cmd+K | Git Dock | Chat | Diff │
└──────────────┬──────────────────┘
               │ HTTP/WebSocket
               ▼
┌─────────────────────────────────┐
│    Python Backend (FastAPI)     │  ← Logic Layer
│  Git | RAG | AI Orchestration   │
└──────────────┬──────────────────┘
               │
      ┌────────┼────────┐
      ▼        ▼        ▼
   Claude   OpenCode  Ollama        ← AI Providers
```

---

## 🔧 Configuration

### Environment Variables (.env)
```bash
# API Keys (Direct Mode)
ANTHROPIC_API_KEY=sk-ant-…
OPENAI_API_KEY=sk-…
GOOGLE_API_KEY=…

# Server Settings
SERVER_PORT=8000
CHROMA_PERSIST_DIR=.godot_minds/index

# AI Settings
DEFAULT_AI_MODE=direct  # direct | opencode | ollama
OLLAMA_URL=http://localhost:11434
```

### Godot Settings
- **AI Backend Mode**: Choose your preferred AI provider
- **Server URL**: Default `http://localhost:8000`
- **Polling Interval**: Git status refresh rate (default: 2s)
- **Diff Colors**: Customize add/remove highlighting

---

## Development

### Run Tests
```bash
cd backend
pytest tests/ -v
pytest tests/ --cov=. --cov-report=html
```

### Linting & Type Checking
```bash
black .
ruff check . --fix
mypy . --strict
```

### GDScript Linting
```bash
gdlint addons/godot_minds/**/*.gd
```

---

## Contributing
We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Powered by [ChromaDB](https://www.trychroma.com/) for RAG
- Inspired by [Cursor](https://cursor.sh/) and [GitHub Copilot](https://github.com/features/copilot)

---

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/godotaiide/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/godotaiide/discussions)
- **Email**: your.email@example.com

---

Made with for the Godot community
