"""
Configuration management using Pydantic Settings
"""

from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # Server Configuration
    host: str = "127.0.0.1"
    port: int = 8005
    debug: bool = True

    # AI Provider Mode
    ai_mode: Literal["direct", "opencode", "ollama"] = "direct"

    # Direct API Keys (Mode 1)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # OpenCode Configuration (Mode 2)
    opencode_path: str = "opencode"  # CLI path

    # Ollama Configuration (Mode 3)
    ollama_url: str = "http://localhost:11434"

    # ChromaDB Configuration
    chroma_persist_directory: str = ".godot_minds/index"

    # File Watching
    watch_extensions: list[str] = [".gd", ".cs", ".cpp", ".h", ".hpp"]
    ignore_directories: list[str] = [".git", "addons", ".godot_minds", ".godot"]

    # Git Configuration
    default_branch: str = "main"

    # WebSocket
    ws_heartbeat_interval: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()
