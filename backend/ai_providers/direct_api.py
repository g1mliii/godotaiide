"""
Direct API provider implementation for Claude, GPT-4, and Gemini
"""

from typing import List, Dict, Optional, AsyncIterator, Union, Any
import anthropic
from openai import AsyncOpenAI
import google.generativeai as genai
import asyncio
import logging
import json

from ai_providers.base import AIProvider
from config import settings
from services.tool_executor import (
    get_tools_for_anthropic,
    get_tools_for_openai,
    get_tool_executor,
)

logger = logging.getLogger(__name__)


class DirectAPIProvider(AIProvider):
    """Provider for direct API access (Anthropic, OpenAI, Google)"""

    client: Union[anthropic.AsyncAnthropic, AsyncOpenAI, None]
    model: Any  # Can be string or GenerativeModel

    def __init__(self, provider: str = "anthropic"):
        """
        Initialize direct API provider

        Args:
            provider: Which API to use ("anthropic", "openai", "gemini")
        """
        self.provider = provider.lower()
        self.client = None

        if self.provider == "anthropic":
            if not settings.anthropic_api_key:
                raise ValueError("Anthropic API key not configured")
            # Configure with retries and timeout
            self.client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key, max_retries=3, timeout=60.0
            )
            self.model = "claude-sonnet-4-20250514"

        elif self.provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("OpenAI API key not configured")
            # Configure with timeout
            self.client = AsyncOpenAI(
                api_key=settings.openai_api_key, timeout=60.0, max_retries=3
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
        system_prompt: Optional[str] = None,
    ) -> str:
        """Ask AI a question with optional context"""

        # Build the full prompt
        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n```\n{context}\n```\n\n{prompt}"

        if self.provider == "anthropic" and isinstance(
            self.client, anthropic.AsyncAnthropic
        ):
            message = await self.client.messages.create(  # type: ignore[attr-defined]
                model=self.model,
                max_tokens=4096,
                system=system_prompt
                or "You are a helpful AI coding assistant for Godot Engine development.",
                messages=[{"role": "user", "content": full_prompt}],
            )
            return message.content[0].text

        elif self.provider == "openai" and isinstance(self.client, AsyncOpenAI):
            messages: List[Dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": full_prompt})

            response = await self.client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=4096  # type: ignore
            )
            return response.choices[0].message.content or ""

        elif self.provider == "gemini":
            # Wrap blocking call to prevent blocking event loop
            response = await asyncio.to_thread(self.model.generate_content, full_prompt)
            return response.text  # type: ignore[attr-defined]

        return ""

    async def ask_with_tools(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tool_iterations: int = 5,
    ) -> Dict[str, Any]:
        """
        Ask AI with tool calling support for Godot editor operations.

        Args:
            prompt: User's request
            context: Optional context
            system_prompt: System prompt
            max_tool_iterations: Max rounds of tool calling

        Returns:
            Dict with 'response' text and 'tool_results' list
        """
        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n```\n{context}\n```\n\n{prompt}"

        tool_results: List[Dict[str, Any]] = []
        executor = get_tool_executor()

        if self.provider == "anthropic" and isinstance(
            self.client, anthropic.AsyncAnthropic
        ):
            tools = get_tools_for_anthropic()
            messages: List[Dict[str, Any]] = [{"role": "user", "content": full_prompt}]

            for iteration in range(max_tool_iterations):
                response = await self.client.messages.create(  # type: ignore[attr-defined]
                    model=self.model,
                    max_tokens=4096,
                    system=system_prompt
                    or "You are a helpful AI assistant for Godot Engine development. You have access to tools to manipulate the Godot editor directly.",
                    messages=messages,
                    tools=tools,
                )

                # Check for tool use
                tool_use_blocks = [
                    block for block in response.content if block.type == "tool_use"
                ]

                if not tool_use_blocks:
                    # No more tool calls, extract final text
                    text_blocks = [
                        block.text
                        for block in response.content
                        if hasattr(block, "text")
                    ]
                    return {
                        "response": "\n".join(text_blocks),
                        "tool_results": tool_results,
                    }

                # Execute tool calls
                tool_call_results = []
                for block in tool_use_blocks:
                    result = await executor.execute_tool(block.name, block.input)
                    tool_results.append(
                        {"tool": block.name, "input": block.input, "result": result}
                    )
                    tool_call_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result),
                        }
                    )

                # Add assistant response and tool results to messages
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_call_results})

            # Max iterations reached
            return {
                "response": "Tool execution completed (max iterations reached)",
                "tool_results": tool_results,
            }

        elif self.provider == "openai" and isinstance(self.client, AsyncOpenAI):
            tools = get_tools_for_openai()
            openai_messages: List[Dict[str, Any]] = []
            if system_prompt:
                openai_messages.append({"role": "system", "content": system_prompt})
            openai_messages.append({"role": "user", "content": full_prompt})

            for iteration in range(max_tool_iterations):
                response = await self.client.chat.completions.create(  # type: ignore[call-overload]
                    model=self.model,
                    messages=openai_messages,
                    max_tokens=4096,
                    tools=tools,
                    tool_choice="auto",
                )

                choice = response.choices[0]

                if not choice.message.tool_calls:
                    return {
                        "response": choice.message.content or "",
                        "tool_results": tool_results,
                    }

                # Execute tool calls
                openai_messages.append(choice.message)

                for tool_call in choice.message.tool_calls:
                    args = json.loads(tool_call.function.arguments)
                    result = await executor.execute_tool(tool_call.function.name, args)
                    tool_results.append(
                        {
                            "tool": tool_call.function.name,
                            "input": args,
                            "result": result,
                        }
                    )
                    openai_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": str(result),
                        }
                    )

            return {
                "response": "Tool execution completed (max iterations reached)",
                "tool_results": tool_results,
            }

        # Fallback for providers without tool support
        response = await self.ask(prompt, context, system_prompt)
        return {"response": response, "tool_results": []}

    async def chat(
        self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None
    ) -> str:
        """Have a conversation with AI"""

        if self.provider == "anthropic" and isinstance(
            self.client, anthropic.AsyncAnthropic
        ):
            # Convert messages to Anthropic format
            anthropic_messages: List[Dict[str, str]] = []
            for msg in messages:
                anthropic_messages.append(
                    {"role": msg["role"], "content": msg["content"]}
                )

            message = await self.client.messages.create(  # type: ignore[attr-defined]
                model=self.model,
                max_tokens=4096,
                system=system_prompt
                or "You are a helpful AI coding assistant for Godot Engine development.",
                messages=anthropic_messages,
            )
            return message.content[0].text

        elif self.provider == "openai" and isinstance(self.client, AsyncOpenAI):
            openai_messages: List[Dict[str, str]] = []
            if system_prompt:
                openai_messages.append({"role": "system", "content": system_prompt})

            for msg in messages:
                openai_messages.append({"role": msg["role"], "content": msg["content"]})

            response = await self.client.chat.completions.create(
                model=self.model, messages=openai_messages, max_tokens=4096  # type: ignore
            )
            return response.choices[0].message.content or ""

        elif self.provider == "gemini":
            # Gemini uses a different conversation format
            # For now, just use the last message
            last_message = messages[-1]["content"] if messages else ""
            # Wrap blocking call to prevent blocking event loop
            response = await asyncio.to_thread(
                self.model.generate_content, last_message
            )
            return response.text  # type: ignore[attr-defined]

        return ""

    async def complete(self, code_before: str, code_after: str, language: str) -> str:
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

        return await self.ask(
            prompt,
            system_prompt="You are a code completion AI. Provide only the completion code, no explanations.",
        )

    async def stream_response(
        self, prompt: str, context: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream AI response token by token"""

        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n```\n{context}\n```\n\n{prompt}"

        if self.provider == "anthropic":
            async with self.client.messages.stream(  # type: ignore[union-attr]
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": full_prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text

        elif self.provider == "openai":
            stream = await self.client.chat.completions.create(  # type: ignore[union-attr]
                model=self.model,
                messages=[{"role": "user", "content": full_prompt}],
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        elif self.provider == "gemini":
            # Gemini doesn't support streaming in the same way
            # Return full response (wrapped to prevent blocking)
            response = await asyncio.to_thread(self.model.generate_content, full_prompt)
            yield response.text

    async def close(self):
        """Close HTTP client to free resources"""
        if hasattr(self.client, "close"):
            await self.client.close()
