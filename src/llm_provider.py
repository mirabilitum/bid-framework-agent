# -*- coding: utf-8 -*-
"""
LLM Provider Interface
Pluggable backends for any LLM service.

Built-in providers:
  - claude    : Anthropic Claude (with vision)
  - openai    : OpenAI GPT series
  - openai-compatible : Any OpenAI-compatible API (Kimi, DeepSeek, Gemini, local models, etc.)
  - qwen      : Alibaba Qwen via DashScope
  - mock      : Canned responses for testing without API

To add a custom provider, subclass BaseLLMProvider and register via register_provider().
"""

import os
import json
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class BaseLLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 4096, **kwargs) -> str:
        """Send a text prompt and return the model response."""

    def generate_with_images(
        self, prompt: str, images: Optional[List[dict]] = None, max_tokens: int = 4096, **kwargs
    ) -> str:
        """Send a prompt with images (vision). Falls back to text-only by default."""
        return self.generate(prompt, max_tokens=max_tokens, **kwargs)


# --------------------------------------------------------------------------- #
#  Claude (Anthropic)
# --------------------------------------------------------------------------- #

class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude provider with vision support."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Claude API key not found.\n"
                "  Set env var: export ANTHROPIC_API_KEY=sk-ant-...\n"
                "  Or pass:     --api-key sk-ant-..."
            )
        self.model = model

    def generate(self, prompt: str, max_tokens: int = 4096, **kwargs) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        resp = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    def generate_with_images(
        self, prompt: str, images: Optional[List[dict]] = None, max_tokens: int = 4096, **kwargs
    ) -> str:
        if not images:
            return self.generate(prompt, max_tokens=max_tokens)

        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        content: List[Dict[str, Any]] = []
        for img in images:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": img["media_type"], "data": img["data"]},
            })
        content.append({"type": "text", "text": prompt})

        resp = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
        )
        return resp.content[0].text


# --------------------------------------------------------------------------- #
#  OpenAI
# --------------------------------------------------------------------------- #

class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found.\n"
                "  Set env var: export OPENAI_API_KEY=sk-...\n"
                "  Or pass:     --api-key sk-..."
            )
        self.model = model

    def generate(self, prompt: str, max_tokens: int = 4096, **kwargs) -> str:
        import openai

        client = openai.OpenAI(api_key=self.api_key)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content


# --------------------------------------------------------------------------- #
#  OpenAI-Compatible (Kimi, DeepSeek, Gemini, local Ollama, etc.)
# --------------------------------------------------------------------------- #

class OpenAICompatibleProvider(BaseLLMProvider):
    """
    Any service that exposes an OpenAI-compatible /v1/chat/completions endpoint.

    Covers: Kimi (Moonshot), DeepSeek, Google Gemini (via OpenAI compat),
            Ollama, LM Studio, vLLM, Together AI, Groq, etc.

    Usage:
        --provider openai-compatible --api-key KEY
        Plus env vars:
            OPENAI_COMPATIBLE_API_BASE  (required)  e.g. https://api.moonshot.cn/v1
            OPENAI_COMPATIBLE_MODEL     (optional)  e.g. moonshot-v1-128k
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_COMPATIBLE_API_KEY") or os.getenv("LLM_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_COMPATIBLE_API_BASE") or os.getenv("LLM_API_BASE")
        self.model = model or os.getenv("OPENAI_COMPATIBLE_MODEL") or os.getenv("LLM_MODEL") or "default"

        if not self.base_url:
            raise ValueError(
                "OpenAI-compatible provider requires a base URL.\n"
                "  Set env var: export OPENAI_COMPATIBLE_API_BASE=https://api.moonshot.cn/v1\n"
                "  Common endpoints:\n"
                "    Kimi:     https://api.moonshot.cn/v1\n"
                "    DeepSeek: https://api.deepseek.com/v1\n"
                "    Ollama:   http://localhost:11434/v1\n"
                "    Gemini:   https://generativelanguage.googleapis.com/v1beta/openai"
            )

    def generate(self, prompt: str, max_tokens: int = 4096, **kwargs) -> str:
        import openai

        client = openai.OpenAI(api_key=self.api_key or "not-needed", base_url=self.base_url)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content


# --------------------------------------------------------------------------- #
#  Qwen (Alibaba 通义千问)
# --------------------------------------------------------------------------- #

class QwenProvider(BaseLLMProvider):
    """Alibaba Qwen provider via DashScope-compatible API."""

    def __init__(self, api_key: Optional[str] = None, endpoint: Optional[str] = None):
        self.api_key = api_key or os.getenv("QWEN_API_KEY")
        self.endpoint = endpoint or os.getenv("QWEN_API_ENDPOINT", "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation")

        if not self.api_key:
            raise ValueError(
                "Qwen API key not found.\n"
                "  Set env var: export QWEN_API_KEY=sk-...\n"
                "  Or pass:     --api-key sk-..."
            )

    def generate(self, prompt: str, max_tokens: int = 4096, **kwargs) -> str:
        import requests

        resp = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": "qwen-max",
                "input": {"messages": [{"role": "user", "content": prompt}]},
                "parameters": {"max_tokens": max_tokens},
            },
        )
        resp.raise_for_status()
        return resp.json()["output"]["text"]


# --------------------------------------------------------------------------- #
#  Mock (for testing without an API key)
# --------------------------------------------------------------------------- #

class MockProvider(BaseLLMProvider):
    """Returns canned JSON so you can test the full pipeline without burning tokens."""

    def generate(self, prompt: str, max_tokens: int = 4096, **kwargs) -> str:
        if "分析任务" in prompt or "提取关键信息" in prompt:
            return json.dumps(self._mock_analysis(), ensure_ascii=False, indent=2)
        return json.dumps(self._mock_framework(), ensure_ascii=False, indent=2)

    @staticmethod
    def _mock_analysis() -> dict:
        return {
            "project_info": {"name": "测试项目", "procurement_type": "公开招标", "budget": "100万元"},
            "packages": [],
            "scoring_factors": [
                {"name": "投标报价", "score": 20.0, "category": "price", "description": "价格评分", "sub_items": []},
                {"name": "培训服务方案", "score": 25.0, "category": "technical", "description": "培训服务方案评分",
                 "sub_items": ["培训目标", "培训对象", "培训内容"]},
            ],
            "response_format": {"skeleton": ["一、经济部分", "二、服务部分", "三、商务部分"], "requirements": "宋体小四，1.5倍行距"},
            "requirements": {"training_objectives": {"title": "培训目标", "content": "培训目标详细内容"}},
        }

    @staticmethod
    def _mock_framework() -> dict:
        return {
            "has_chapter_covers": False,
            "framework": [
                {"level": 1, "title": "一、经济部分", "content": "", "children": [
                    {"level": 2, "title": "（一）投标报价", "content": "", "children": []},
                ]},
                {"level": 1, "title": "二、服务部分", "content": "", "children": [
                    {"level": 2, "title": "（一）培训服务方案", "content": "", "children": [
                        {"level": 3, "title": "1. 培训目标", "content": "", "children": []},
                        {"level": 3, "title": "2. 培训对象", "content": "", "children": []},
                        {"level": 3, "title": "3. 培训内容", "content": "", "children": []},
                    ]},
                ]},
            ],
        }


# --------------------------------------------------------------------------- #
#  Provider Registry & Factory
# --------------------------------------------------------------------------- #

_PROVIDERS: Dict[str, type] = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "openai-compatible": OpenAICompatibleProvider,
    "qwen": QwenProvider,
    "mock": MockProvider,
}

# Aliases for convenience
_ALIASES: Dict[str, str] = {
    "anthropic": "claude",
    "gpt": "openai",
    "kimi": "openai-compatible",
    "moonshot": "openai-compatible",
    "deepseek": "openai-compatible",
    "gemini": "openai-compatible",
    "ollama": "openai-compatible",
    "local": "openai-compatible",
}

# Default env vars for aliased providers (auto-set base_url)
_ALIAS_DEFAULTS: Dict[str, Dict[str, str]] = {
    "kimi": {"base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-128k"},
    "moonshot": {"base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-128k"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.0-flash"},
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "llama3"},
}


def register_provider(name: str, cls: type) -> None:
    """Register a custom provider class."""
    _PROVIDERS[name.lower()] = cls


def list_providers() -> List[str]:
    """List all available provider names (including aliases)."""
    return sorted(set(list(_PROVIDERS.keys()) + list(_ALIASES.keys())))


def create_llm_provider(name: str, api_key: Optional[str] = None, **kwargs) -> BaseLLMProvider:
    """
    Create an LLM provider by name.

    Supports direct names (claude, openai, qwen, mock, openai-compatible)
    and aliases (kimi, deepseek, gemini, ollama, local).
    """
    original_name = name.lower()

    # Resolve alias
    resolved = _ALIASES.get(original_name, original_name)

    cls = _PROVIDERS.get(resolved)
    if cls is None:
        available = ", ".join(list_providers())
        raise ValueError(f"Unknown provider '{name}'. Available: {available}")

    if resolved == "mock":
        return cls()

    # For aliased openai-compatible providers, inject default base_url/model
    if original_name in _ALIAS_DEFAULTS and resolved == "openai-compatible":
        defaults = _ALIAS_DEFAULTS[original_name]
        kwargs.setdefault("base_url", defaults.get("base_url"))
        kwargs.setdefault("model", defaults.get("model"))

    return cls(api_key=api_key, **kwargs)
