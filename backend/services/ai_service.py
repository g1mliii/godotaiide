"""
AI service orchestrator - routes requests to appropriate provider
"""

from typing import Optional, List, Dict
from pathlib import Path
import weakref
import aiofiles
import re

from ai_providers.base import AIProvider
from ai_providers.direct_api import DirectAPIProvider
from ai_providers.ollama import OllamaProvider
from ai_providers.opencode import OpenCodeProvider
from services.indexer_service import CodeIndexer
from services.git_service import GitService
from config import settings


class AIService:
    """Service for AI operations with dual-mode support"""

    def __init__(
        self,
        git_service: Optional[GitService] = None,
        indexer_service: Optional[CodeIndexer] = None,
        watcher_service=None,
    ):
        """Initialize AI service"""
        # Use weak references to avoid circular references
        self._git_service_ref = weakref.ref(git_service) if git_service else None
        self._indexer_service_ref = (
            weakref.ref(indexer_service) if indexer_service else None
        )
        self._watcher_service_ref = (
            weakref.ref(watcher_service) if watcher_service else None
        )

        # Initialize indexer if not provided
        self._indexer: Optional[CodeIndexer] = None
        if not indexer_service:
            self._indexer = CodeIndexer()

        # Initialize git service if not provided
        if not git_service:
            try:
                git_svc = GitService("..")
                self._git_service_ref = weakref.ref(git_svc)
            except Exception:
                pass

        # Provider cache to prevent creating new HTTP clients on every request
        self._provider_cache: Dict[str, AIProvider] = {}

    @property
    def git_service(self) -> Optional[GitService]:
        """Get git service from weak reference"""
        return self._git_service_ref() if self._git_service_ref else None

    @property
    def indexer(self) -> Optional[CodeIndexer]:
        """Get indexer service from weak reference"""
        if self._indexer_service_ref:
            return self._indexer_service_ref()
        # Fallback to local instance if created in __init__
        return getattr(self, "_indexer", None)

    @property
    def watcher_service(self):
        """Get watcher service from weak reference"""
        return self._watcher_service_ref() if self._watcher_service_ref else None

    def _get_provider(self, mode: Optional[str] = None) -> AIProvider:
        """
        Get AI provider based on mode (cached to prevent resource leaks)

        Args:
            mode: Override mode (direct/ollama), or use settings default

        Returns:
            Cached AIProvider instance
        """
        active_mode = mode or settings.ai_mode
        cache_key = f"{active_mode}:{settings.anthropic_api_key[:8] if settings.anthropic_api_key else 'none'}"

        # Return cached provider if available
        if cache_key in self._provider_cache:
            return self._provider_cache[cache_key]

        # Create new provider
        provider = self._create_provider(active_mode)
        self._provider_cache[cache_key] = provider
        return provider

    def _create_provider(self, active_mode: str) -> AIProvider:
        """
        Create a new provider instance

        Args:
            active_mode: AI mode (direct/ollama/opencode)

        Returns:
            New AIProvider instance
        """
        if active_mode == "direct":
            # Default to Anthropic if API key is available
            if settings.anthropic_api_key:
                return DirectAPIProvider("anthropic")
            elif settings.openai_api_key:
                return DirectAPIProvider("openai")
            elif settings.google_api_key:
                return DirectAPIProvider("gemini")
            else:
                raise ValueError("No API keys configured for direct mode")

        elif active_mode == "ollama":
            return OllamaProvider()

        elif active_mode == "opencode":
            return OpenCodeProvider()

        else:
            raise ValueError(f"Unknown AI mode: {active_mode}")

    async def close(self):
        """Close all cached providers to free resources"""
        for provider in self._provider_cache.values():
            await provider.close()
        self._provider_cache.clear()

    async def ask(
        self,
        prompt: str,
        file_path: Optional[str] = None,
        file_content: Optional[str] = None,
        selection: Optional[Dict[str, int]] = None,
        mode: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Ask AI for code assistance (Cmd+K functionality)

        Args:
            prompt: User's request (supports @filename syntax)
            file_path: Path to the file being edited
            file_content: Content of the file
            selection: Selected lines (start_line, end_line)
            mode: Override AI mode

        Returns:
            Dict with response, code, explanation
        """
        provider = self._get_provider(mode)

        # Gather context
        context = await self._gather_context(file_path, file_content, selection)

        # Extract and include @mentioned files
        mentioned_files = self._extract_file_mentions(prompt)
        if mentioned_files:
            file_context = await self._gather_file_context(mentioned_files)
            context = f"{context}\n\n---\n\n{file_context}" if context else file_context

        # Get AI response
        response = await provider.ask(
            prompt,
            context=context,
            system_prompt="You are an expert Godot Engine developer. Provide clear, working code solutions.",
        )

        # Parse response (simplified - in production, you'd extract code blocks)
        return {
            "response": response,
            "code": "",  # TODO: Extract code from response
            "explanation": "",
        }

    async def chat(
        self,
        message: str,
        history: Optional[List[Dict[str, str]]] = None,
        context_files: Optional[List[str]] = None,
        mode: Optional[str] = None,
    ) -> str:
        """
        Chat conversation with AI

        Args:
            message: User's message
            history: Previous chat messages
            context_files: Files to include via @filename
            mode: Override AI mode

        Returns:
            AI's response
        """
        provider = self._get_provider(mode)

        # Extract @filename mentions from message
        mentioned_files = self._extract_file_mentions(message)

        # Combine with explicitly provided context files
        all_context_files = list(set((context_files or []) + mentioned_files))

        # Build message history
        messages = history or []
        messages.append({"role": "user", "content": message})

        # Add context from referenced files
        if all_context_files:
            file_context = await self._gather_file_context(all_context_files)
            # Prepend context to the last user message
            messages[-1]["content"] = f"{file_context}\n\n{message}"

        return await provider.chat(messages)

    async def complete(
        self,
        file_path: str,
        file_content: str,
        cursor_line: int,
        cursor_column: int,
        mode: Optional[str] = None,
    ) -> str:
        """
        Get inline code completion

        Args:
            file_path: Path to file
            file_content: Full file content
            cursor_line: Line number of cursor (0-indexed)
            cursor_column: Column number of cursor
            mode: Override AI mode

        Returns:
            Completion text
        """
        provider = self._get_provider(mode)

        # Split content at cursor
        lines = file_content.split("\n")
        code_before = (
            "\n".join(lines[:cursor_line]) + "\n" + lines[cursor_line][:cursor_column]
        )
        code_after = (
            lines[cursor_line][cursor_column:]
            + "\n"
            + "\n".join(lines[cursor_line + 1 :])
        )

        # Determine language from file extension
        language = Path(file_path).suffix.lstrip(".")
        lang_map = {
            "gd": "gdscript",
            "cs": "csharp",
            "cpp": "cpp",
            "h": "cpp",
            "hpp": "cpp",
        }
        language = lang_map.get(language, language)

        return await provider.complete(code_before, code_after, language)

    async def generate_commit_message(
        self, staged_files: List[str], diff_content: Optional[str] = None
    ) -> str:
        """
        Generate commit message from staged changes

        Args:
            staged_files: List of staged file paths
            diff_content: Optional diff content

        Returns:
            Generated commit message
        """
        provider = self._get_provider()

        # Get diff if not provided
        if not diff_content and self.git_service:
            diffs = []
            for file_path in staged_files:
                try:
                    diff = self.git_service.get_diff(file_path)
                    diffs.append(f"File: {file_path}\n{diff.diff_text}")
                except Exception:
                    pass
            diff_content = "\n\n".join(diffs)

        prompt = f"""Generate a concise git commit message for these changes:

{diff_content}

Provide only the commit message, following conventional commit format (e.g., "feat:", "fix:", "refactor:", etc.)."""

        return await provider.ask(
            prompt,
            system_prompt="You are a git commit message generator. Provide only the commit message, no explanations.",
        )

    async def _gather_context(
        self,
        file_path: Optional[str],
        file_content: Optional[str],
        selection: Optional[Dict[str, int]],
    ) -> str:
        """Gather context for AI request"""
        context_parts = []

        # Add file content
        if file_content:
            if selection:
                lines = file_content.split("\n")
                selected = "\n".join(
                    lines[selection["start_line"] : selection["end_line"] + 1]
                )
                context_parts.append(f"Selected code:\n{selected}")
            else:
                context_parts.append(f"Current file:\n{file_content}")

        # Add header file for C++ files
        if file_path and file_path.endswith(".cpp"):
            header_path = file_path.replace(".cpp", ".h")
            if Path(header_path).exists():
                async with aiofiles.open(header_path, mode="r", encoding="utf-8") as f:
                    header_content = await f.read()
                context_parts.append(f"Header file ({header_path}):\n{header_content}")

        # Add RAG context (relevant code from index)
        # TODO: Search index for relevant chunks

        return "\n\n---\n\n".join(context_parts)

    def _extract_file_mentions(self, message: str) -> List[str]:
        """
        Extract @filename mentions from message

        Supports formats:
        - @filename.gd
        - @path/to/file.cs
        - @"path with spaces/file.cpp"
        - @'path with spaces/file.h'

        Args:
            message: User message with potential @mentions

        Returns:
            List of mentioned file paths
        """
        # Pattern to match @mentions with optional quotes
        pattern = r'@(?:"([^"]+)"|\'([^\']+)\'|([^\s]+))'
        matches = re.findall(pattern, message)

        # Extract non-empty groups (one of the three capture groups will match)
        file_paths = []
        for match in matches:
            # match is a tuple of (quoted_double, quoted_single, unquoted)
            file_path = match[0] or match[1] or match[2]
            if file_path:
                file_paths.append(file_path)

        return file_paths

    async def _gather_file_context(self, file_paths: List[str]) -> str:
        """Gather context from referenced files"""
        context_parts = []

        for file_path in file_paths:
            try:
                full_path = Path(file_path)
                if full_path.exists():
                    async with aiofiles.open(
                        full_path, mode="r", encoding="utf-8"
                    ) as f:
                        content = await f.read()
                    context_parts.append(f"File: {file_path}\n```\n{content}\n```")
            except Exception:
                pass

        return "\n\n".join(context_parts)
