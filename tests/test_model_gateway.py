"""Tests for M35 — Model Gateway.

Validates:
- MockModelProvider generate and streaming
- ModelGateway decoupling from concrete providers
- OllamaProvider request formatting
- VLLMProvider request formatting
- Singleton gateway accessor get_model_gateway()
"""

from unittest.mock import patch

from agents.model_gateway import (
    MockModelProvider,
    ModelGateway,
    OllamaProvider,
    VLLMProvider,
    get_model_gateway,
)


class TestModelGateway:
    async def test_mock_provider_generate(self) -> None:
        provider = MockModelProvider(canned_response="def add(a, b): return a + b")
        gateway = ModelGateway(provider=provider, default_model="qwen2.5-coder:7b")

        response = await gateway.generate(
            prompt="Write an addition function in Python",
            system_prompt="You are an expert coder",
        )
        assert response.text == "def add(a, b): return a + b"
        assert response.model == "qwen2.5-coder:7b"
        assert provider.last_prompt == "Write an addition function in Python"
        assert provider.call_count == 1

    async def test_mock_provider_stream(self) -> None:
        provider = MockModelProvider(canned_response="one two three")
        gateway = ModelGateway(provider=provider)

        chunks = []
        async for chunk in gateway.stream(prompt="Count to 3"):
            chunks.append(chunk)

        full_text = "".join(chunks)
        assert "one" in full_text
        assert "two" in full_text
        assert "three" in full_text

    async def test_get_model_gateway_singleton(self) -> None:
        gw = get_model_gateway()
        assert gw is not None
        assert isinstance(gw, ModelGateway)

    async def test_ollama_provider_format(self) -> None:
        provider = OllamaProvider(base_url="http://localhost:11434")

        from unittest.mock import MagicMock

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "response": "Hello from Ollama",
                "prompt_eval_count": 10,
                "eval_count": 5,
            }
            mock_post.return_value = mock_resp

            res = await provider.generate(
                prompt="Say hello",
                model="llama3.1:8b",
                system_prompt="Be polite",
            )
            assert res.text == "Hello from Ollama"
            assert res.prompt_tokens == 10
            assert res.completion_tokens == 5
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"]["model"] == "llama3.1:8b"
            assert call_kwargs["json"]["system"] == "Be polite"

    async def test_vllm_provider_format(self) -> None:
        from unittest.mock import MagicMock

        provider = VLLMProvider(base_url="http://localhost:8000/v1", api_key="secret-key")

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "Hello from vLLM"}}],
                "usage": {"prompt_tokens": 15, "completion_tokens": 8, "total_tokens": 23},
            }
            mock_post.return_value = mock_resp

            res = await provider.generate(
                prompt="Say hello",
                model="llama3.1:8b",
            )
            assert res.text == "Hello from vLLM"
            assert res.total_tokens == 23
            mock_post.assert_called_once()
            headers = mock_post.call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer secret-key"
