from __future__ import annotations

import asyncio
import random
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .cache import TranslationCache
from .engines.base import (
    BaseEngine,
    EngineFatalError,
    EngineRateLimitError,
)
from .glossary import Glossary
from .placeholder import protect, restore, validate_restore
from .scanner import LangEntry


MANUAL_ENGINE = "manual"

_SRC_GLOSSARY = "glossary"
_SRC_MANUAL = "manual"
_SRC_CACHE = "cache"
_SRC_ENGINE = "engine"


@dataclass
class TranslatedEntry:
    entry: LangEntry
    merged: Dict[str, str]
    new_keys: int = 0
    cached_keys: int = 0
    failed_keys: int = 0
    failed_pairs: List[Tuple[str, str]] = field(default_factory=list)


def _clean_llm_output(text: str) -> str:
    """去掉 Markdown 代码块、多余引号、解释性前缀。"""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    for prefix in (
        "翻译：",
        "译文：",
        "中文：",
        "简体中文：",
        "Translation:",
        "translation:",
        "Translated:",
    ):
        if t.startswith(prefix):
            t = t[len(prefix):].strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'", "“", "”", "「", "」"):
        t = t[1:-1].strip()
    return t


class Translator:
    def __init__(
        self,
        engine: BaseEngine,
        cache: Optional[TranslationCache] = None,
        glossary: Optional[Glossary] = None,
        concurrency: int = 8,
        merge_existing: bool = True,
        max_retries: int = 3,
        log_cb: Optional[Callable[[str], None]] = None,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ):
        self.engine = engine
        self.cache = cache
        self.glossary = glossary
        self.concurrency = max(1, concurrency)
        self.merge_existing = merge_existing
        self.max_retries = max(1, max_retries)
        self.log_cb = log_cb or (lambda msg: None)
        self.progress_cb = progress_cb or (lambda done, total: None)
        self.cancel_event = cancel_event

    def _log(self, msg: str) -> None:
        self.log_cb(msg)

    def _is_cancelled(self) -> bool:
        return self.cancel_event is not None and self.cancel_event.is_set()

    async def translate_entries(
        self, entries: List[LangEntry], target_lang: str = "zh_cn"
    ) -> List[TranslatedEntry]:
        # 1. 收集所有需要翻译的文本
        needed: Dict[str, List[Tuple[LangEntry, str]]] = {}
        for e in entries:
            for key, src_text in e.source.items():
                if not src_text or not src_text.strip():
                    continue
                if self.merge_existing and e.existing.get(key):
                    continue
                needed.setdefault(src_text, []).append((e, key))

        unique_texts = list(needed.keys())
        self._log(f"共 {len(unique_texts)} 条唯一文本待处理")

        resolved: Dict[str, str] = {}
        resolved_from: Dict[str, str] = {}

        # 2. 术语表
        from_glossary = 0
        remaining: List[str] = []
        for text in unique_texts:
            hit = self.glossary.lookup(text) if self.glossary else None
            if hit:
                resolved[text] = hit
                resolved_from[text] = _SRC_GLOSSARY
                from_glossary += 1
            else:
                remaining.append(text)
        if from_glossary:
            self._log(f"术语表命中 {from_glossary} 条")

        # 3. 人工校对缓存
        from_manual = 0
        if self.cache and remaining:
            manual_hits = self.cache.get_many(
                remaining, MANUAL_ENGINE, "en", target_lang
            )
            for src, tr in manual_hits.items():
                resolved[src] = tr
                resolved_from[src] = _SRC_MANUAL
                from_manual += 1
            remaining = [t for t in remaining if t not in manual_hits]
            if from_manual:
                self._log(f"人工校对缓存命中 {from_manual} 条")

        # 4. 当前引擎缓存
        from_cache = 0
        if self.cache and remaining:
            engine_hits = self.cache.get_many(
                remaining, self.engine.name, "en", target_lang
            )
            for src, tr in engine_hits.items():
                resolved[src] = tr
                resolved_from[src] = _SRC_CACHE
                from_cache += 1
            remaining = [t for t in remaining if t not in engine_hits]
            if from_cache:
                self._log(f"引擎缓存命中 {from_cache} 条")

        pending = remaining
        self._log(f"需要调用引擎 {len(pending)} 条")

        # 5. 并发翻译
        sem = asyncio.Semaphore(self.concurrency)
        total = len(pending)
        done = 0
        lock = asyncio.Lock()

        abort_event = threading.Event()
        first_fatal: List[Optional[Exception]] = [None]

        async def worker(text: str) -> Tuple[str, Optional[str], Optional[str]]:
            nonlocal done

            async def _tick():
                nonlocal done
                async with lock:
                    done += 1
                    self.progress_cb(done, total)

            async with sem:
                if self._is_cancelled() or abort_event.is_set():
                    await _tick()
                    return text, None, "cancelled"

                protected, placeholders = protect(text)
                out: Optional[str] = None
                last_err: Optional[str] = None

                for attempt in range(self.max_retries):
                    if self._is_cancelled() or abort_event.is_set():
                        last_err = "cancelled"
                        break
                    try:
                        raw = await self.engine.translate(protected, "en", target_lang)
                        candidate = restore(raw, placeholders)
                        if not validate_restore(candidate, placeholders):
                            raise RuntimeError(
                                f"占位符丢失/残留，模型输出={raw!r}"
                            )
                        candidate = _clean_llm_output(candidate)
                        if not candidate:
                            raise RuntimeError("引擎返回空译文")
                        # 引擎返回原文 = 翻译失败（不重试）
                        if candidate.strip() == text.strip():
                            last_err = "引擎返回原文"
                            out = None
                            break
                        out = candidate
                        last_err = None
                        break

                    except EngineFatalError as e:
                        last_err = f"{type(e).__name__}: {e}"
                        if first_fatal[0] is None:
                            first_fatal[0] = e
                        abort_event.set()
                        break

                    except EngineRateLimitError as e:
                        last_err = f"{type(e).__name__}: {e}"
                        if attempt < self.max_retries - 1:
                            if e.retry_after and e.retry_after > 0:
                                delay = float(e.retry_after)
                            else:
                                delay = (2 ** attempt) + random.random()
                            self._log(
                                f"[限流] {text[:40]!r} 第 {attempt + 1} 次失败: "
                                f"{last_err}，{delay:.2f}s 后重试"
                            )
                            await asyncio.sleep(delay)

                    except Exception as e:  # noqa: BLE001
                        last_err = f"{type(e).__name__}: {e}"
                        if attempt < self.max_retries - 1:
                            delay = (2 ** attempt) + random.random()
                            self._log(
                                f"[重试] {text[:40]!r} 第 {attempt + 1} 次失败: "
                                f"{last_err}，{delay:.2f}s 后重试"
                            )
                            await asyncio.sleep(delay)

                await _tick()
                return text, out, last_err

        if pending:
            outcomes = await asyncio.gather(*(worker(t) for t in pending))
            to_cache: List[Tuple[str, str]] = []
            failed: List[Tuple[str, str]] = []
            for text, out, err in outcomes:
                if out is None:
                    failed.append((text, err or "unknown"))
                    continue
                # 双保险：即使 worker 没拦住，这里也再判一次
                if out.strip() == text.strip():
                    failed.append((text, "引擎返回原文"))
                    continue
                resolved[text] = out
                resolved_from[text] = _SRC_ENGINE
                to_cache.append((text, out))

            if self.cache and to_cache:
                self.cache.put_many(to_cache, self.engine.name, "en", target_lang)

            if first_fatal[0] is not None:
                raise first_fatal[0]

            if failed:
                self._log(f"失败 {len(failed)} 条（示例前 5）:")
                for t, err in failed[:5]:
                    self._log(f"  - {t[:60]!r}: {err}")

        # 6. 合并到每个条目
        out_entries: List[TranslatedEntry] = []
        for e in entries:
            merged: Dict[str, str] = dict(e.existing) if self.merge_existing else {}
            new_keys = 0
            cached_keys = 0
            failed_keys = 0
            failed_pairs: List[Tuple[str, str]] = []
            for key, src_text in e.source.items():
                if self.merge_existing and e.existing.get(key):
                    continue
                if not src_text or not src_text.strip():
                    continue
                if src_text in resolved:
                    merged[key] = resolved[src_text]
                    kind = resolved_from.get(src_text, _SRC_ENGINE)
                    if kind == _SRC_ENGINE:
                        new_keys += 1
                    else:
                        cached_keys += 1
                else:
                    merged[key] = src_text
                    failed_keys += 1
                    failed_pairs.append((key, src_text))

            out_entries.append(
                TranslatedEntry(
                    entry=e,
                    merged=merged,
                    new_keys=new_keys,
                    cached_keys=cached_keys,
                    failed_keys=failed_keys,
                    failed_pairs=failed_pairs,
                )
            )
        return out_entries