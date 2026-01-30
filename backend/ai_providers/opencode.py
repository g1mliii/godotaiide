"""
OpenCode provider implementation for users with AI subscriptions
Uses OpenCode CLI to access ChatGPT Plus, GitHub Copilot, or Claude Pro
"""

from typing import List, Dict, Optional, AsyncIterator
import asyncio
import logging

from ai_providers.base import AIProvider
from config import settings

logger = logging.getLogger(__name__)


class OpenCodeProvider(AIProvider):
    """Provider for OpenCode CLI (uses existing AI subscriptions)"""

    def __init__(self):
        """
        Initialize OpenCode provider

        Raises:
            ValueError: If OpenCode is not installed or accessible
        """
        self.opencode_path = settings.opencode_path
        self._verify_opencode_installation()

        # OpenCode subprocess management
        self._process: Optional[asyncio.subprocess.Process] = None
        self._session_active = False

    def _verify_opencode_installation(self) -> None:
        """Verify OpenCode is installed and accessible"""
        # Check if opencode command exists
        import shutil

        if not shutil.which(self.opencode_path):
            raise ValueError(
                f"OpenCode not found at '{self.opencode_path}'. "
                "Install from https://github.com/getcursor/opencode or configure OPENCODE_PATH"
            )

    async def _run_opencode_command(
        self, prompt: str, context: Optional[str] = None, stream: bool = False
    ) -> str:
        """
        Run OpenCode command and return response

        Args:
            prompt: User prompt
            context: Additional context
            stream: Whether to stream response

        Returns:
            AI response
        """
        # Build OpenCode command
        cmd = [self.opencode_path, "ask"]

        # Add context if provided
        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion:\n{prompt}"

        # Add prompt as argument
        cmd.extend(["--prompt", full_prompt])

        if stream:
            cmd.append("--stream")

        try:
            # Run OpenCode subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"OpenCode command failed: {error_msg}")
                raise RuntimeError(f"OpenCode error: {error_msg}")

            return stdout.decode().strip()

        except FileNotFoundError:
            raise RuntimeError(f"OpenCode executable not found: {self.opencode_path}")
        except Exception as e:
            logger.error(f"OpenCode execution failed: {e}", exc_info=True)
            raise

    async def ask(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """
        Ask AI a question with optional context

        Args:
            prompt: User's question/request
            context: Additional context (code, files, etc.)
            system_prompt: System prompt (prepended to context if provided)

        Returns:
            AI's response
        """
        # Prepend system prompt to context if provided
        full_context = context
        if system_prompt:
            full_context = f"System: {system_prompt}\n\n{context or ''}"

        response = await self._run_opencode_command(prompt, full_context)
        return response

    async def chat(
        self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None
    ) -> str:
        """
        Have a conversation with AI

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: System prompt to set behavior

        Returns:
            AI's response
        """
        # Convert message history to context
        context_parts = []

        if system_prompt:
            context_parts.append(f"System: {system_prompt}")

        # Build conversation history
        for msg in messages[:-1]:  # All except last message
            role = msg.get("role", "user")
            content = msg.get("content", "")
            context_parts.append(f"{role.capitalize()}: {content}")

        # Last message is the current prompt
        last_msg = messages[-1] if messages else {"content": ""}
        prompt = last_msg.get("content", "")

        context = "\n\n".join(context_parts) if context_parts else None

        return await self.ask(prompt, context)

    async def complete(self, code_before: str, code_after: str, language: str) -> str:
        """
        Get code completion

        Args:
            code_before: Code before cursor
            code_after: Code after cursor
            language: Programming language

        Returns:
            Completion text
        """
        # Build completion prompt
        prompt = f"Complete the following {language} code at the cursor position:"
        context = (
            f"Code before cursor:\n{code_before}\n\nCode after cursor:\n{code_after}"
        )

        response = await self._run_opencode_command(prompt, context)

        # Extract just the completion (OpenCode may return full code)
        # This is a simple heuristic - adjust based on actual OpenCode behavior
        return response.strip()

    async def stream_response(
        self, prompt: str, context: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Stream AI response token by token

        Args:
            prompt: User's question/request
            context: Additional context

        Yields:
            Response tokens
        """
        # Build OpenCode command
        cmd = [self.opencode_path, "ask", "--stream"]

        # Add context if provided
        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n{context}\n\nQuestion:\n{prompt}"

        cmd.extend(["--prompt", full_prompt])

        try:
            # Run OpenCode subprocess with streaming
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            # Read stdout line by line
            if process.stdout:
                async for line in process.stdout:
                    token = line.decode().strip()
                    if token:
                        yield token

            # Wait for process to complete
            await process.wait()

            if process.returncode != 0:
                stderr = await process.stderr.read() if process.stderr else b""
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"OpenCode streaming failed: {error_msg}")

        except Exception as e:
            logger.error(f"OpenCode streaming error: {e}", exc_info=True)
            raise

    async def close(self):
        """Cleanup OpenCode resources"""
        # No persistent connections to close
        pass
