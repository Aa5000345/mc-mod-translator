from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

try:
    from cryptography.fernet import Fernet

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


CONFIG_DIR = Path.home() / ".mc_mod_translator"
CONFIG_PATH = CONFIG_DIR / "config.yaml"
SECRETS_PATH = CONFIG_DIR / "secrets.enc"
KEY_PATH = CONFIG_DIR / "key.bin"
CACHE_PATH = CONFIG_DIR / "cache.db"
GLOSSARY_PATH = CONFIG_DIR / "glossary.csv"


# 真正需要加密保存的字段。region 不是秘密。
SECRET_FIELD_NAMES = {"api_key", "app_key", "app_id", "token"}


@dataclass
class Config:
    target_language: str = "zh_cn"
    output_mode: str = "merged"  # merged | per_mod
    output_dir: str = "./output"
    auto_install: bool = False
    resourcepack_name: str = "Mods-zh_cn"
    mc_version: Optional[str] = None
    pack_format: Optional[int] = None
    engine: str = "openai"
    engines: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cache_enabled: bool = True
    glossary_enabled: bool = True
    merge_existing: bool = True
    concurrency: int = 8

    def to_dict(self) -> dict:
        return asdict(self)


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _get_fernet() -> Optional["Fernet"]:
    if not HAS_CRYPTO:
        return None
    _ensure_dir()
    if not KEY_PATH.exists():
        KEY_PATH.write_bytes(Fernet.generate_key())
        try:
            os.chmod(KEY_PATH, 0o600)
        except Exception:
            pass
    return Fernet(KEY_PATH.read_bytes())


def encrypt_secrets(secrets: dict) -> str:
    data = json.dumps(secrets).encode("utf-8")
    f = _get_fernet()
    if f:
        return f.encrypt(data).decode("utf-8")
    return base64.b64encode(data).decode("utf-8")


def decrypt_secrets(token: str) -> dict:
    data = token.encode("utf-8")
    f = _get_fernet()
    if f:
        data = f.decrypt(data)
    else:
        data = base64.b64decode(data)
    return json.loads(data.decode("utf-8"))


def _apply_env_overrides(cfg: Config) -> Config:
    env_map = {
        "OPENAI_API_KEY": ("openai", "api_key"),
        "DEEPSEEK_API_KEY": ("deepseek", "api_key"),
        "DEEPL_API_KEY": ("deepl", "api_key"),
        "ANTHROPIC_API_KEY": ("claude", "api_key"),
        "GEMINI_API_KEY": ("gemini", "api_key"),
        "MICROSOFT_TRANSLATOR_KEY": ("microsoft", "api_key"),
        "BAIDU_APP_ID": ("baidu", "app_id"),
        "BAIDU_APP_KEY": ("baidu", "app_key"),
    }
    for env_name, (engine, field_name) in env_map.items():
        val = os.environ.get(env_name)
        if val:
            cfg.engines.setdefault(engine, {})[field_name] = val
    return cfg


def load_config() -> Config:
    _ensure_dir()
    data: dict = {}
    if CONFIG_PATH.exists():
        try:
            data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    secrets: dict = {}
    if SECRETS_PATH.exists():
        try:
            secrets = decrypt_secrets(SECRETS_PATH.read_text(encoding="utf-8"))
        except Exception:
            secrets = {}

    cfg = Config(**{k: v for k, v in data.items() if k in Config.__dataclass_fields__})
    for engine_name, engine_secrets in secrets.items():
        cfg.engines.setdefault(engine_name, {}).update(engine_secrets)
    return _apply_env_overrides(cfg)


def save_config(cfg: Config) -> None:
    _ensure_dir()
    public_data = cfg.to_dict()
    secrets: dict = {}
    engines = public_data.pop("engines", {}) or {}
    for engine_name, engine_cfg in engines.items():
        engine_cfg = dict(engine_cfg)
        sec: Dict[str, Any] = {}
        for k in list(engine_cfg.keys()):
            if k in SECRET_FIELD_NAMES:
                val = engine_cfg.pop(k)
                if val:
                    sec[k] = val
        if sec:
            secrets.setdefault(engine_name, {}).update(sec)
        public_data.setdefault("engines", {})[engine_name] = engine_cfg

    CONFIG_PATH.write_text(
        yaml.safe_dump(public_data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    SECRETS_PATH.write_text(encrypt_secrets(secrets), encoding="utf-8")