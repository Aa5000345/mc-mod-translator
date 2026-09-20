from __future__ import annotations

from typing import Dict, List, Type

from .base import BaseEngine, EngineConfigError
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
from .free import AutoFreeEngine, MyMemoryEngine


ENGINE_CLASSES: Dict[str, Type[BaseEngine]] = {
    # 免费自动（推荐给普通玩家，放在最前）
    "auto_free": AutoFreeEngine,
    "mymemory": MyMemoryEngine,
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


# 各引擎的默认配置。真实 key 会与用户配置合并。
DEFAULT_ENGINE_CONFIGS: Dict[str, Dict] = {
    "auto_free": {},
    "mymemory": {},
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


# 每个引擎**必须**由用户填写的字段。空列表 = 无需任何配置。
# 用于 GUI / CLI 前置校验，以及引擎配置对话框决定显示哪些字段。
ENGINE_REQUIRED_FIELDS: Dict[str, List[str]] = {
    # 免费自动
    "auto_free": [],
    "mymemory": [],
    # LLM
    "openai": ["api_key"],
    "deepseek": ["api_key"],
    "moonshot": ["api_key"],
    "qwen": ["api_key"],
    "openrouter": ["api_key"],
    "claude": ["api_key"],
    "gemini": ["api_key"],
    "ollama": [],
    # 在线机翻
    "google": [],
    "deepl": ["api_key"],
    "microsoft": ["api_key"],
    "baidu": ["app_id", "app_key"],
    "libretranslate": [],
    # 本地
    "nllb": [],
}


def missing_required_fields(name: str, config: Dict) -> List[str]:
    """返回 ``config`` 中缺失的非空字段列表。空列表表示配置完整。"""
    required = ENGINE_REQUIRED_FIELDS.get(name, [])
    cfg = config or {}
    return [f for f in required if not cfg.get(f)]


def validate_engine_config(name: str, config: Dict) -> None:
    """若配置不完整则抛 ``EngineConfigError``。"""
    missing = missing_required_fields(name, config)
    if missing:
        raise EngineConfigError(
            f"{name}: 缺少配置项 {', '.join(missing)}"
        )


def create_engine(name: str, config: Dict) -> BaseEngine:
    cls = ENGINE_CLASSES.get(name)
    if cls is None:
        raise ValueError(f"未知引擎: {name}")
    merged = dict(DEFAULT_ENGINE_CONFIGS.get(name, {}))
    merged.update(config or {})
    return cls(name, merged)


def list_engines() -> List[str]:
    return ENGINE_NAMES