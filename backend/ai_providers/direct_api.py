"""
Direct API provider implementation for Claude, GPT-4, and Gemini
"""
from typing import List, Dict, Optional, AsyncIterator
import anthropic
import openai
from openai import AsyncOpenAI
import google.generativeai as genai

from ai_providers.base import AIProvider
from config import settings


class DirectAPIProvider(AIProvider):
    """Provider for direct API access (Anthropic, OpenAI, Google)"""

    def __init__(self, provider: str = "anthropic"):
        """
        Initialize direct API provider

        Args:
            provider: Which API to use ("anthropic", "openai", "gemini")
        """
        self.provider = provider.lower()

        if self.provider == "anthropic":
            if not settings.anthropic_api_key:
                raise ValueError("Anthropic API key not configured")
            # Configure with retries and timeout
            self.client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                max_retries=3,
                timeout=60.0
            )
            self.model = "claude-sonnet-4-20250514"

        elif self.provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("OpenAI API key not configured")
            # Configure with timeout
            self.client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=60.0,
                max_retries=3
            )
            self.model = "gpt-4-turbo-preview"

        elif self.provider == "gemini":
            if not settings.google_api_key:
                raise ValueError("Google API key not configured")
            genai.configure(api_key=settings.google_api_key)
            self.model = genai.GenerativeModel("gemini-pro")

        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def ask(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """Ask AI a question with optional context"""

        # Build the full prompt
        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n```\n{context}\n```\n\n{prompt}"

        if self.provider == "anthropic":
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt or "You are a helpful AI coding assistant for Godot Engine development.",
                messages=[{"role": "user", "content": full_prompt}]
            )
            return message.content[0].text

        elif self.provider == "openai":
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": full_prompt})

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4096
            )
            return response.choices[0].message.content

        elif self.provider == "gemini":
            response = self.model.generate_content(full_prompt)
            return response.text

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> str:
        """Have a conversation with AI"""

        if self.provider == "anthropic":
            # Convert messages to Anthropic format
            anthropic_messages = []
            for msg in messages:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

            message = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt or "You are a helpful AI coding assistant for Godot Engine development.",
                messages=anthropic_messages
            )
            return message.content[0].text

        elif self.provider == "openai":
            openai_messages = []
            if system_prompt:
                openai_messages.append({"role": "system", "content": system_prompt})

            for msg in messages:
                openai_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                max_tokens=4096
            )
            return response.choices[0].message.content

        elif self.provider == "gemini":
            # Gemini uses a different conversation format
            # For now, just use the last message
            last_message = messages[-1]["content"] if messages else ""
            response = self.model.generate_content(last_message)
            return response.text

    async def complete(
        self,
        code_before: str,
        code_after: str,
        language: str
    ) -> str:
        """Get code completion"""

        prompt = f"""Complete the code at the cursor position.

Language: {language}

Code before cursor:
```
{code_before}
```

Code after cursor:
```
{code_after}
```

Provide only the completion text that should be inserted at the cursor. Do not include explanations."""

        return await self.ask(prompt, system_prompt="You are a code completion AI. Provide only the completion code, no explanations.")

    async def stream_response(
        self,
        prompt: str,
        context: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream AI response token by token"""

        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n```\n{context}\n```\n\n{prompt}"

        if self.provider == "anthropic":
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": full_prompt}]
            ) as stream:
                async for text in stream.text_stream:
                    yield text

        elif self.provider == "openai":
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": full_prompt}],
                stream=True
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        elif self.provider == "gemini":
            # Gemini doesn't support streaming in the same way
            # Return full response
            response = self.model.generate_content(full_prompt)
            yield response.text

    async def close(self):
        """Close HTTP client to free resources"""
        if hasattr(self.client, 'close'):
            await self.client.close()
