"""
Base class for AI providers
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, AsyncIterator


class AIProvider(ABC):
    """Abstract base class for AI providers"""

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    async def close(self):
        """
        Override in subclasses to cleanup resources (HTTP clients, etc.)
        Default implementation does nothing.
        """
        pass

    @abstractmethod
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
            system_prompt: System prompt to set behavior

        Returns:
            AI's response
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass
