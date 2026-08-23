"""OpenRouter client backends for the agent runner."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from agent_experiment.config import OPENROUTER_BASE_URL, TEMPERATURE, get_api_key


class ChatCompletionClient(Protocol):
    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = TEMPERATURE,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Return (response_dict, usage_dict)."""


@dataclass
class OpenAICompatUsage:
    prompt_tokens: int
    completion_tokens: int
    model_extra: dict[str, Any] | None = None


@dataclass
class OpenAICompatMessage:
    role: str
    content: str | None
    tool_calls: list[Any] | None = None


@dataclass
class OpenAICompatChoice:
    finish_reason: str | None
    message: OpenAICompatMessage


@dataclass
class OpenAICompatResponse:
    choices: list[OpenAICompatChoice]
    usage: OpenAICompatUsage | None


@dataclass
class _ToolCallFunction:
    name: str
    arguments: str


@dataclass
class _ToolCall:
    id: str
    type: str
    function: _ToolCallFunction


def _parse_openrouter_response(data: dict[str, Any]) -> OpenAICompatResponse:
    choices = []
    for choice in data.get("choices", []):
        msg = choice.get("message", {})
        tool_calls = None
        if msg.get("tool_calls"):
            tool_calls = [
                _ToolCall(
                    id=tc.get("id", ""),
                    type=tc.get("type", "function"),
                    function=_ToolCallFunction(
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    ),
                )
                for tc in msg["tool_calls"]
            ]
        content = msg.get("content")
        if not content and msg.get("reasoning"):
            content = msg["reasoning"]
        choices.append(
            OpenAICompatChoice(
                finish_reason=choice.get("finish_reason"),
                message=OpenAICompatMessage(
                    role=msg.get("role", "assistant"),
                    content=content,
                    tool_calls=tool_calls,
                ),
            )
        )
    usage_data = data.get("usage") or {}
    usage = OpenAICompatUsage(
        prompt_tokens=usage_data.get("prompt_tokens", 0),
        completion_tokens=usage_data.get("completion_tokens", 0),
        model_extra={"cost": usage_data.get("cost")},
    )
    return OpenAICompatResponse(choices=choices, usage=usage)


class DirectOpenRouterClient:
    """Uses OpenAI SDK with OPENROUTER_API_KEY."""

    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=get_api_key(),
            default_headers={
                "HTTP-Referer": "https://github.com/agent-experiment",
                "X-Title": "Lightweight vs Frontier Agent Experiment",
            },
        )

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = TEMPERATURE,
    ) -> OpenAICompatResponse:
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
        )
        return OpenAICompatResponse(
            choices=[
                OpenAICompatChoice(
                    finish_reason=c.finish_reason,
                    message=OpenAICompatMessage(
                        role=c.message.role,
                        content=c.message.content,
                        tool_calls=c.message.tool_calls,
                    ),
                )
                for c in response.choices
            ],
            usage=OpenAICompatUsage(
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
                model_extra=getattr(response.usage, "model_extra", None) if response.usage else None,
            )
            if response.usage
            else None,
        )


class ComposioProxyClient:
    """Calls OpenRouter via Composio proxy_execute (requires composio CLI bridge)."""

    def __init__(self, composio_session_id: str | None = None) -> None:
        self.session_id = composio_session_id or os.environ.get("COMPOSIO_SESSION_ID", "")

    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = TEMPERATURE,
    ) -> OpenAICompatResponse:
        from agent_experiment.composio_bridge import composio_proxy_chat

        data = composio_proxy_chat(
            model=model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            session_id=self.session_id,
        )
        return _parse_openrouter_response(data)


def get_client(backend: str | None = None) -> ChatCompletionClient:
    backend = backend or os.environ.get("OPENROUTER_BACKEND", "auto")
    if backend == "composio":
        return ComposioProxyClient()
    if backend == "direct":
        return DirectOpenRouterClient()
    # auto: prefer direct if key exists, else composio
    try:
        get_api_key()
        return DirectOpenRouterClient()
    except RuntimeError:
        return ComposioProxyClient()
