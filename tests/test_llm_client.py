# tests/test_llm_client.py
import pytest
from unittest.mock import patch, MagicMock

import openai


def test_llm_client_tries_openai_first():
    """Should call OpenAI first, return result and provider without trying Anthropic."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"result": "test"}'

    with patch.object(client._openai.chat.completions, "create", return_value=mock_response) as mock_oai:
        text, provider = client.complete("Test prompt", model_primary="gpt-4.1-mini")
        mock_oai.assert_called_once()
        assert text == '{"result": "test"}'
        assert provider == "openai"


def test_llm_client_falls_back_to_anthropic():
    """Should fall back to Anthropic when OpenAI fails with retriable error."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    mock_anthropic_response = MagicMock()
    mock_anthropic_response.content = [MagicMock()]
    mock_anthropic_response.content[0].text = '{"fallback": true}'

    with patch.object(
        client._openai.chat.completions, "create",
        side_effect=openai.APIConnectionError(request=MagicMock()),
    ), patch.object(
        client._anthropic.messages, "create", return_value=mock_anthropic_response
    ) as mock_ant:
        text, provider = client.complete(
            "Test prompt",
            model_primary="gpt-4.1-mini",
            model_fallback="claude-haiku-4-5-20251001",
        )
        mock_ant.assert_called_once()
        assert text == '{"fallback": true}'
        assert provider == "anthropic"


def test_llm_client_both_providers_fail():
    """Should raise RuntimeError mentioning both providers when both fail."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    with patch.object(
        client._openai.chat.completions, "create",
        side_effect=openai.APIConnectionError(request=MagicMock()),
    ), patch.object(
        client._anthropic.messages, "create", side_effect=Exception("Anthropic down")
    ):
        with pytest.raises(RuntimeError, match="Both LLM providers failed"):
            client.complete("Test prompt")


def test_llm_client_non_retriable_error_propagates():
    """Non-retriable OpenAI errors (auth, bad request) should propagate without fallback."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    with patch.object(
        client._openai.chat.completions, "create",
        side_effect=openai.AuthenticationError(
            message="bad key", response=MagicMock(status_code=401), body=None
        ),
    ), patch.object(
        client._anthropic.messages, "create"
    ) as mock_ant:
        with pytest.raises(openai.AuthenticationError):
            client.complete("Test prompt")
        mock_ant.assert_not_called()


def test_llm_client_none_content_falls_back_to_anthropic():
    """OpenAI None content should trigger Anthropic fallback (not raise)."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    mock_oai_response = MagicMock()
    mock_oai_response.choices = [MagicMock()]
    mock_oai_response.choices[0].message.content = None

    mock_ant_response = MagicMock()
    mock_ant_response.content = [MagicMock(text="Anthropic response")]

    with patch.object(client._openai.chat.completions, "create", return_value=mock_oai_response):
        with patch.object(client._anthropic.messages, "create", return_value=mock_ant_response):
            text, provider = client.complete("Test prompt")
            assert text == "Anthropic response"
            assert provider == "anthropic"


def test_llm_client_empty_keys_rejected():
    """Should reject empty API keys at construction time."""
    from src.llm_client import LLMClient

    with pytest.raises(ValueError, match="non-empty"):
        LLMClient(openai_key="", anthropic_key="test-key")

    with pytest.raises(ValueError, match="non-empty"):
        LLMClient(openai_key="test-key", anthropic_key="")


def test_llm_client_system_prompt_passed_to_openai():
    """Should include system message in OpenAI messages when system is provided."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "ok"

    with patch.object(client._openai.chat.completions, "create", return_value=mock_response) as mock_oai:
        client.complete("Hello", system="You are a classifier.")
        call_kwargs = mock_oai.call_args
        messages = call_kwargs.kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "You are a classifier."}
        assert messages[1] == {"role": "user", "content": "Hello"}


def test_llm_client_anthropic_empty_content_raises_runtime_error():
    """When both OpenAI fails and Anthropic returns empty content, RuntimeError is raised."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    mock_ant_response = MagicMock()
    mock_ant_response.content = []  # empty content list

    with patch.object(
        client._openai.chat.completions, "create",
        side_effect=openai.APIConnectionError(request=MagicMock()),
    ), patch.object(
        client._anthropic.messages, "create", return_value=mock_ant_response,
    ):
        with pytest.raises(RuntimeError, match="Both LLM providers failed"):
            client.complete("Test prompt")


def test_llm_client_anthropic_receives_correct_params():
    """Should pass correct model, system, and messages to Anthropic on fallback."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    mock_anthropic_response = MagicMock()
    mock_anthropic_response.content = [MagicMock()]
    mock_anthropic_response.content[0].text = "classified"

    with patch.object(
        client._openai.chat.completions, "create",
        side_effect=openai.APIConnectionError(request=MagicMock()),
    ), patch.object(
        client._anthropic.messages, "create", return_value=mock_anthropic_response
    ) as mock_ant:
        client.complete(
            "Classify this",
            model_fallback="claude-haiku-4-5-20251001",
            system="You are a classifier.",
            max_tokens=1024,
        )
        call_kwargs = mock_ant.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
        assert call_kwargs["system"] == "You are a classifier."
        assert call_kwargs["max_tokens"] == 1024
        assert call_kwargs["messages"] == [{"role": "user", "content": "Classify this"}]


def test_llm_client_falls_back_on_rate_limit_error():
    """CC2-H33: RateLimitError should trigger Anthropic fallback."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    mock_anthropic_response = MagicMock()
    mock_anthropic_response.content = [MagicMock()]
    mock_anthropic_response.content[0].text = "fallback on rate limit"

    mock_response_obj = MagicMock()
    mock_response_obj.status_code = 429
    mock_response_obj.headers = {"retry-after": "1"}

    with patch.object(
        client._openai.chat.completions, "create",
        side_effect=openai.RateLimitError(
            message="rate limited", response=mock_response_obj, body=None,
        ),
    ), patch.object(
        client._anthropic.messages, "create", return_value=mock_anthropic_response,
    ) as mock_ant:
        text, provider = client.complete("Test prompt")
        mock_ant.assert_called_once()
        assert text == "fallback on rate limit"
        assert provider == "anthropic"


def test_llm_client_falls_back_on_api_timeout_error():
    """CC2-H33: APITimeoutError should trigger Anthropic fallback."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    mock_anthropic_response = MagicMock()
    mock_anthropic_response.content = [MagicMock()]
    mock_anthropic_response.content[0].text = "fallback on timeout"

    with patch.object(
        client._openai.chat.completions, "create",
        side_effect=openai.APITimeoutError(request=MagicMock()),
    ), patch.object(
        client._anthropic.messages, "create", return_value=mock_anthropic_response,
    ) as mock_ant:
        text, provider = client.complete("Test prompt")
        mock_ant.assert_called_once()
        assert text == "fallback on timeout"
        assert provider == "anthropic"


def test_llm_client_falls_back_on_internal_server_error():
    """CC2-H33: InternalServerError should trigger Anthropic fallback."""
    from src.llm_client import LLMClient

    client = LLMClient(openai_key="test-key", anthropic_key="test-key")

    mock_anthropic_response = MagicMock()
    mock_anthropic_response.content = [MagicMock()]
    mock_anthropic_response.content[0].text = "fallback on 500"

    mock_response_obj = MagicMock()
    mock_response_obj.status_code = 500

    with patch.object(
        client._openai.chat.completions, "create",
        side_effect=openai.InternalServerError(
            message="server error", response=mock_response_obj, body=None,
        ),
    ), patch.object(
        client._anthropic.messages, "create", return_value=mock_anthropic_response,
    ) as mock_ant:
        text, provider = client.complete("Test prompt")
        mock_ant.assert_called_once()
        assert text == "fallback on 500"
        assert provider == "anthropic"
