"""Model Gateway abstraction and providers for LLM inference.

Provides a unified configuration-driven interface for text generation and streaming:
- OllamaProvider: Native Ollama API
- VLLMProvider: vLLM OpenAI-compatible endpoint
- MockModelProvider: In-memory mock for tests and offline execution
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

logger = structlog.stdlib.get_logger(__name__)


@dataclass
class ModelResponse:
    """Standardized response from an LLM model provider."""

    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseModelProvider(ABC):
    """Abstract interface that all model providers must implement."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> ModelResponse:
        """Generate text completion from LLM."""
        raise NotImplementedError

    @abstractmethod
    async def stream(
        self,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream generated text chunks from LLM."""
        raise NotImplementedError
        yield ""  # For generator typing


class OllamaProvider(BaseModelProvider):
    """Provider connecting to local or remote Ollama server."""

    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(
        self,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> ModelResponse:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return ModelResponse(
                text=data.get("response", ""),
                model=model,
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                metadata=data,
            )

    async def stream(
        self,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with (
            httpx.AsyncClient(timeout=self.timeout) as client,
            client.stream("POST", f"{self.base_url}/api/generate", json=payload) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line:
                    chunk = json.loads(line)
                    yield chunk.get("response", "")


class VLLMProvider(BaseModelProvider):
    """Provider connecting to vLLM via OpenAI-compatible API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: str | None = None,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "EMPTY"
        self.timeout = timeout

    async def generate(
        self,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> ModelResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})
            return ModelResponse(
                text=choice["message"]["content"],
                model=model,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                metadata=data,
            )

    async def stream(
        self,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        async with (
            httpx.AsyncClient(timeout=self.timeout) as client,
            client.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and not line.endswith("[DONE]"):
                    chunk = json.loads(line[6:])
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content


class MockModelProvider(BaseModelProvider):
    """In-memory mock provider for testing and deterministic offline responses."""

    def __init__(self, canned_response: str = "Mock response from ModelGateway"):
        self.canned_response = canned_response
        self.last_prompt: str | None = None
        self.last_model: str | None = None
        self.call_count: int = 0

    async def generate(
        self,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> ModelResponse:
        self.last_prompt = prompt
        self.last_model = model
        self.call_count += 1
        return ModelResponse(
            text=self.canned_response,
            model=model,
            prompt_tokens=len(prompt.split()),
            completion_tokens=len(self.canned_response.split()),
            total_tokens=len(prompt.split()) + len(self.canned_response.split()),
        )

    async def stream(
        self,
        prompt: str,
        model: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        self.last_prompt = prompt
        self.last_model = model
        self.call_count += 1
        for word in self.canned_response.split():
            yield word + " "


class ModelGateway:
    """Configuration-driven gateway decoupling agents from concrete LLM backends."""

    def __init__(
        self,
        provider: BaseModelProvider | None = None,
        default_model: str = "llama3.1:8b",
        default_code_model: str = "qwen2.5-coder:7b",
    ):
        self.provider = provider or MockModelProvider()
        self.default_model = default_model
        self.default_code_model = default_code_model

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> ModelResponse:
        """Generate response via configured provider."""
        target_model = model or self.default_model
        logger.debug("model_gateway_generate", model=target_model)
        return await self.provider.generate(
            prompt=prompt,
            model=target_model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    async def stream(
        self,
        prompt: str,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream chunks via configured provider."""
        target_model = model or self.default_model
        logger.debug("model_gateway_stream", model=target_model)
        async for chunk in self.provider.stream(
            prompt=prompt,
            model=target_model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ):
            yield chunk


_model_gateway: ModelGateway | None = None


def get_model_gateway() -> ModelGateway:
    """Return singleton ModelGateway instance configured from application settings."""
    global _model_gateway
    if _model_gateway is None:
        from app.config import get_settings

        settings = get_settings()
        gateway_settings = settings.model_gateway

        provider: BaseModelProvider
        if settings.environment == "test":
            provider = MockModelProvider()
        elif gateway_settings.provider == "ollama":
            provider = OllamaProvider(base_url=gateway_settings.base_url)
        elif gateway_settings.provider in ("vllm", "openai_compatible"):
            api_key = gateway_settings.api_key.get_secret_value() if gateway_settings.api_key else None
            provider = VLLMProvider(base_url=gateway_settings.base_url, api_key=api_key)
        else:
            provider = MockModelProvider()

        _model_gateway = ModelGateway(
            provider=provider,
            default_model=gateway_settings.default_chat_model,
            default_code_model=gateway_settings.default_code_model,
        )
    return _model_gateway


def set_model_gateway(gateway: ModelGateway | None) -> None:
    """Set global ModelGateway instance (useful for test overrides)."""
    global _model_gateway
    _model_gateway = gateway
