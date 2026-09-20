from __future__ import annotations

from typing import Dict, List, Type

from .base import BaseEngine
from .builtin import (
    BaiduEngine,
    ClaudeEngine,
    DeepLEngine,
    GeminiEngine,
    GoogleEngine,
    LibreTranslateEngine,
    MicrosoftEngine,
    NLLBEngine,
    OllamaEngine,
    OpenAIEngine,
)


ENGINE_CLASSES: Dict[str, Type[BaseEngine]] = {
    # LLM
    "openai": OpenAIEngine,
    "deepseek": OpenAIEngine,
    "moonshot": OpenAIEngine,
    "qwen": OpenAIEngine,
    "openrouter": OpenAIEngine,
    "claude": ClaudeEngine,
    "gemini": GeminiEngine,
    "ollama": OllamaEngine,
    # 在线机翻
    "google": GoogleEngine,
    "deepl": DeepLEngine,
    "microsoft": MicrosoftEngine,
    "baidu": BaiduEngine,
    "libretranslate": LibreTranslateEngine,
    # 本地模型
    "nllb": NLLBEngine,
}

ENGINE_NAMES: List[str] = list(ENGINE_CLASSES.keys())


DEFAULT_ENGINE_CONFIGS: Dict[str, Dict] = {
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "moonshot": {"base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini",
    },
    "claude": {"model": "claude-3-5-sonnet-latest", "max_tokens": 2048},
    "gemini": {"model": "gemini-1.5-flash"},
    "ollama": {"base_url": "http://localhost:11434", "model": "qwen2.5:7b"},
    "google": {},
    "deepl": {},
    "microsoft": {"region": "global"},
    "baidu": {},
    "libretranslate": {"base_url": "http://localhost:5000"},
    "nllb": {"model_path": "facebook/nllb-200-distilled-600M", "device": "cpu"},
}


def create_engine(name: str, config: Dict) -> BaseEngine:
    cls = ENGINE_CLASSES.get(name)
    if cls is None:
        raise ValueError(f"未知引擎: {name}")
    merged = dict(DEFAULT_ENGINE_CONFIGS.get(name, {}))
    merged.update(config or {})
    return cls(name, merged)


def list_engines() -> List[str]:
    return ENGINE_NAMES