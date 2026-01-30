"""
Ollama provider for local AI models
"""
from typing import List, Dict, Optional, AsyncIterator
import httpx

from ai_providers.base import AIProvider
from config import settings


class OllamaProvider(AIProvider):
    """Provider for local Ollama models"""

    def __init__(self, model: str = "codellama"):
        """
        Initialize Ollama provider

        Args:
            model: Ollama model to use (e.g., "codellama", "llama2", "mistral")
        """
        self.base_url = settings.ollama_url
        self.model = model
        # Configure connection pooling to prevent resource leaks
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        self.client = httpx.AsyncClient(timeout=60.0, limits=limits)

    async def ask(
        self,
        prompt: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """Ask AI a question with optional context"""

        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n```\n{context}\n```\n\n{prompt}"

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False
        }

        if system_prompt:
            payload["system"] = system_prompt

        try:
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=payload
            )
            response.raise_for_status()
            return response.json()["response"]
        except Exception as e:
            raise Exception(f"Ollama request failed: {e}")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> str:
        """Have a conversation with AI"""

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json=payload
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except Exception as e:
            raise Exception(f"Ollama chat request failed: {e}")

    async def complete(
        self,
        code_before: str,
        code_after: str,
        language: str
    ) -> str:
        """Get code completion"""

        prompt = f"""<PRE> {code_before} <SUF>{code_after} <MID>"""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "stop": ["<MID>", "</s>"]
            }
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=payload
            )
            response.raise_for_status()
            return response.json()["response"]
        except Exception as e:
            raise Exception(f"Ollama completion failed: {e}")

    async def stream_response(
        self,
        prompt: str,
        context: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream AI response token by token"""

        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n```\n{context}\n```\n\n{prompt}"

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": True
        }

        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if "response" in data:
                            yield data["response"]
        except Exception as e:
            raise Exception(f"Ollama streaming failed: {e}")

    async def close(self):
        """Close HTTP client to free resources"""
        await self.client.aclose()
