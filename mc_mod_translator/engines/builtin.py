"""内置翻译引擎实现。

分三组：
  - LLM 引擎（OpenAI 兼容 / Claude / Gemini / Ollama）
  - 在线机翻（Google / DeepL / Microsoft / 百度 / LibreTranslate）
  - 本地离线模型（NLLB）
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import re
import threading
from typing import List, Optional

from .base import (
    BaseEngine,
    DEFAULT_SYSTEM_PROMPT,
    EngineResponseError,
    check_http_response,
    wrap_request_error,
)


# ============================================================
# 工具
# ============================================================

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def _parse_json_array(text: str) -> Optional[List[str]]:
    """从 LLM 输出中提取 JSON 数组，失败返回 None。"""
    t = _strip_code_fence(text)
    m = _JSON_ARRAY_RE.search(t)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(arr, list):
        return None
    out: List[str] = []
    for item in arr:
        if isinstance(item, str):
            out.append(item)
        else:
            out.append(str(item))
    return out


# ============================================================
# 一、LLM 引擎
# ============================================================

class OpenAIEngine(BaseEngine):
    """OpenAI 兼容接口，可复用于 OpenAI / DeepSeek / Moonshot / Qwen / OpenRouter 等。"""

    name = "openai"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.config.get('api_key', '')}",
            "Content-Type": "application/json",
        }

    def _endpoint(self) -> str:
        base_url = self.config.get("base_url", "https://api.openai.com/v1")
        return f"{base_url.rstrip('/')}/chat/completions"

    def _require_key(self) -> None:
        if not self.config.get("api_key"):
            raise RuntimeError(f"{self.name}: 缺少 api_key")

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        self._require_key()
        cfg = self.config
        model = cfg.get("model", "gpt-4o-mini")
        system = cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
        client = self._get_client(timeout=90.0)
        try:
            resp = await client.post(
                self._endpoint(),
                headers=self._headers(),
                json={
                    "model": model,
                    "temperature": 0.3,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": text},
                    ],
                },
            )
        except Exception as e:  # noqa: BLE001
            raise wrap_request_error(e, self.name) from e

        check_http_response(resp, self.name)
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise EngineResponseError(f"{self.name}: 响应结构异常: {e}") from e

    async def translate_batch(
        self, texts: List[str], src: str = "en", tgt: str = "zh"
    ) -> List[str]:
        """一次请求翻译多条。失败时回退到逐条。"""
        self._require_key()
        if not texts:
            return []
        if len(texts) == 1:
            return [await self.translate(texts[0], src, tgt)]

        cfg = self.config
        model = cfg.get("model", "gpt-4o-mini")
        system = cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
        system_batch = (
            system
            + "\n\n你将收到一个 JSON 数组，请对每个元素独立翻译，"
            "返回一个与输入等长、顺序一致的 JSON 数组。"
            "只输出 JSON 数组本身，不要任何解释、Markdown 代码块或前后缀。"
        )

        payload_text = json.dumps(texts, ensure_ascii=False)
        client = self._get_client(timeout=120.0)
        try:
            resp = await client.post(
                self._endpoint(),
                headers=self._headers(),
                json={
                    "model": model,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": system_batch},
                        {"role": "user", "content": payload_text},
                    ],
                },
            )
        except Exception as e:  # noqa: BLE001
            raise wrap_request_error(e, self.name) from e

        check_http_response(resp, self.name)
        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise EngineResponseError(f"{self.name}: 响应结构异常: {e}") from e

        arr = _parse_json_array(content)
        if arr is None or len(arr) != len(texts):
            # 回退到逐条
            return await asyncio.gather(
                *(self.translate(t, src, tgt) for t in texts)
            )
        return arr


class ClaudeEngine(BaseEngine):
    name = "claude"

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        cfg = self.config
        api_key = cfg.get("api_key", "")
        model = cfg.get("model", "claude-3-5-sonnet-latest")
        base_url = cfg.get("base_url", "https://api.anthropic.com/v1/messages")
        system = cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
        max_tokens = int(cfg.get("max_tokens", 2048))
        if not api_key:
            raise RuntimeError("claude: 缺少 api_key")

        client = self._get_client(timeout=90.0)
        try:
            resp = await client.post(
                base_url,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": text}],
                },
            )
        except Exception as e:  # noqa: BLE001
            raise wrap_request_error(e, self.name) from e

        check_http_response(resp, self.name)
        data = resp.json()
        try:
            return data["content"][0]["text"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise EngineResponseError(f"claude: 响应结构异常: {e}") from e


class GeminiEngine(BaseEngine):
    name = "gemini"

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        cfg = self.config
        api_key = cfg.get("api_key", "")
        model = cfg.get("model", "gemini-1.5-flash")
        system = cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
        if not api_key:
            raise RuntimeError("gemini: 缺少 api_key")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        client = self._get_client(timeout=90.0)
        try:
            resp = await client.post(
                url,
                params={"key": api_key},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"parts": [{"text": text}]}],
                    "safetySettings": [
                        {
                            "category": "HARM_CATEGORY_HARASSMENT",
                            "threshold": "BLOCK_NONE",
                        },
                        {
                            "category": "HARM_CATEGORY_HATE_SPEECH",
                            "threshold": "BLOCK_NONE",
                        },
                        {
                            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                            "threshold": "BLOCK_NONE",
                        },
                        {
                            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                            "threshold": "BLOCK_NONE",
                        },
                    ],
                },
            )
        except Exception as e:  # noqa: BLE001
            raise wrap_request_error(e, self.name) from e

        check_http_response(resp, self.name)
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise EngineResponseError(
                f"gemini: 响应结构异常（可能被安全策略拦截）: {e}"
            ) from e


class OllamaEngine(BaseEngine):
    name = "ollama"

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        cfg = self.config
        base = cfg.get("base_url", "http://localhost:11434")
        model = cfg.get("model", "qwen2.5:7b")
        system = cfg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT

        client = self._get_client(timeout=180.0)
        try:
            resp = await client.post(
                f"{base.rstrip('/')}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": text},
                    ],
                },
            )
        except Exception as e:  # noqa: BLE001
            raise wrap_request_error(e, self.name) from e

        check_http_response(resp, self.name)
        data = resp.json()
        try:
            return data["message"]["content"].strip()
        except (KeyError, TypeError) as e:
            raise EngineResponseError(f"ollama: 响应结构异常: {e}") from e


# ============================================================
# 二、在线机翻引擎
# ============================================================

class GoogleEngine(BaseEngine):
    name = "google"

    _LANG_MAP = {
        "zh": "zh-CN",
        "zh_cn": "zh-CN",
        "zh-CN": "zh-CN",
        "zh_tw": "zh-TW",
        "en": "en",
    }

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        sl = self._LANG_MAP.get(src.lower(), "en")
        tl = self._LANG_MAP.get(tgt.lower(), "zh-CN")
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": sl, "tl": tl, "dt": "t", "q": text}
        client = self._get_client(timeout=30.0)
        try:
            resp = await client.get(url, params=params)
        except Exception as e:  # noqa: BLE001
            raise wrap_request_error(e, self.name) from e
        check_http_response(resp, self.name)
        data = resp.json()
        try:
            return "".join(seg[0] for seg in data[0] if seg and seg[0])
        except (IndexError, TypeError) as e:
            raise EngineResponseError(f"google: 响应结构异常: {e}") from e


class DeepLEngine(BaseEngine):
    name = "deepl"

    _LANG_MAP = {"zh": "ZH", "zh_cn": "ZH", "zh-CN": "ZH", "zh_tw": "ZH", "en": "EN"}

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        cfg = self.config
        api_key = cfg.get("api_key", "")
        base = cfg.get("base_url") or "https://api-free.deepl.com/v2/translate"
        if not api_key:
            raise RuntimeError("deepl: 缺少 api_key")

        client = self._get_client(timeout=60.0)
        try:
            resp = await client.post(
                base,
                headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
                data={
                    "text": text,
                    "source_lang": self._LANG_MAP.get(src.lower(), "EN"),
                    "target_lang": self._LANG_MAP.get(tgt.lower(), "ZH"),
                },
            )
        except Exception as e:  # noqa: BLE001
            raise wrap_request_error(e, self.name) from e
        check_http_response(resp, self.name)
        data = resp.json()
        try:
            return data["translations"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise EngineResponseError(f"deepl: 响应结构异常: {e}") from e


class MicrosoftEngine(BaseEngine):
    name = "microsoft"

    _LANG_MAP = {
        "zh": "zh-Hans",
        "zh_cn": "zh-Hans",
        "zh-CN": "zh-Hans",
        "zh_tw": "zh-Hant",
        "en": "en",
    }

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        cfg = self.config
        api_key = cfg.get("api_key", "")
        region = cfg.get("region", "global")
        if not api_key:
            raise RuntimeError("microsoft: 缺少 api_key")

        url = "https://api.cognitive.microsofttranslator.com/translate"
        params = {
            "api-version": "3.0",
            "from": self._LANG_MAP.get(src.lower(), "en"),
            "to": self._LANG_MAP.get(tgt.lower(), "zh-Hans"),
        }
        headers = {
            "Ocp-Apim-Subscription-Key": api_key,
            "Ocp-Apim-Subscription-Region": region,
            "Content-Type": "application/json",
        }
        client = self._get_client(timeout=30.0)
        try:
            resp = await client.post(
                url, params=params, headers=headers, json=[{"text": text}]
            )
        except Exception as e:  # noqa: BLE001
            raise wrap_request_error(e, self.name) from e
        check_http_response(resp, self.name)
        data = resp.json()
        try:
            return data[0]["translations"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise EngineResponseError(f"microsoft: 响应结构异常: {e}") from e


class BaiduEngine(BaseEngine):
    name = "baidu"

    _LANG_MAP = {"zh": "zh", "zh_cn": "zh", "zh-CN": "zh", "en": "en"}

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        cfg = self.config
        appid = cfg.get("app_id", "")
        key = cfg.get("app_key", "")
        if not appid or not key:
            raise RuntimeError("baidu: 缺少 app_id / app_key")

        salt = str(random.randint(10000, 99999))
        sign = hashlib.md5((appid + text + salt + key).encode("utf-8")).hexdigest()
        params = {
            "q": text,
            "from": self._LANG_MAP.get(src.lower(), "en"),
            "to": self._LANG_MAP.get(tgt.lower(), "zh"),
            "appid": appid,
            "salt": salt,
            "sign": sign,
        }
        client = self._get_client(timeout=30.0)
        try:
            resp = await client.post(
                "https://fanyi-api.baidu.com/api/trans/vip/translate", params=params
            )
        except Exception as e:  # noqa: BLE001
            raise wrap_request_error(e, self.name) from e
        check_http_response(resp, self.name)
        data = resp.json()
        if "trans_result" not in data:
            raise EngineResponseError(f"baidu 错误: {data}")
        return "\n".join(item["dst"] for item in data["trans_result"])


class LibreTranslateEngine(BaseEngine):
    name = "libretranslate"

    _LANG_MAP = {"zh": "zh", "zh_cn": "zh", "zh-CN": "zh", "zh_tw": "zt", "en": "en"}

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        cfg = self.config
        base = cfg.get("base_url", "http://localhost:5000")
        api_key = cfg.get("api_key", "")

        payload = {
            "q": text,
            "source": self._LANG_MAP.get(src.lower(), "en"),
            "target": self._LANG_MAP.get(tgt.lower(), "zh"),
            "format": "text",
        }
        if api_key:
            payload["api_key"] = api_key

        client = self._get_client(timeout=60.0)
        try:
            resp = await client.post(f"{base.rstrip('/')}/translate", json=payload)
        except Exception as e:  # noqa: BLE001
            raise wrap_request_error(e, self.name) from e
        check_http_response(resp, self.name)
        data = resp.json()
        try:
            return data["translatedText"]
        except (KeyError, TypeError) as e:
            raise EngineResponseError(f"libretranslate: 响应结构异常: {e}") from e


# ============================================================
# 三、本地离线模型
# ============================================================

class NLLBEngine(BaseEngine):
    name = "nllb"

    _LANG_MAP = {
        "en": "eng_Latn",
        "zh": "zho_Hans",
        "zh_cn": "zho_Hans",
        "zh-CN": "zho_Hans",
        "zh_tw": "zho_Hant",
    }

    _model = None
    _tokenizer = None
    _loaded_key: Optional[str] = None
    _lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        # 调用方必须持有 NLLBEngine._lock
        model_path = self.config.get("model_path", "facebook/nllb-200-distilled-600M")
        device = self.config.get("device", "cpu")
        key = f"{model_path}|{device}"
        if NLLBEngine._model is not None and NLLBEngine._loaded_key == key:
            return
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        NLLBEngine._tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_path)
        model.to(device)
        NLLBEngine._model = model
        NLLBEngine._loaded_key = key

    async def translate(self, text: str, src: str = "en", tgt: str = "zh") -> str:
        return await asyncio.to_thread(self._translate_sync, text, src, tgt)

    def _translate_sync(self, text: str, src: str, tgt: str) -> str:
        with NLLBEngine._lock:
            self._ensure_loaded()
            tok = NLLBEngine._tokenizer
            model = NLLBEngine._model
            assert tok is not None and model is not None

            src_code = self._LANG_MAP.get(src.lower(), "eng_Latn")
            tgt_code = self._LANG_MAP.get(tgt.lower(), "zho_Hans")

            tok.src_lang = src_code
            inputs = tok(text, return_tensors="pt", truncation=True, max_length=512)
            inputs = {k: v.to(model.device) for k, v in inputs.items()}
            out = model.generate(
                **inputs,
                forced_bos_token_id=tok.convert_tokens_to_ids(tgt_code),
                max_length=512,
            )
            return tok.batch_decode(out, skip_special_tokens=True)[0]