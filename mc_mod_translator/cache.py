from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


class TranslationCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = sqlite3.connect(
            str(self.path), check_same_thread=False
        )
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        conn = self._conn
        if conn is None:
            return
        with self._lock:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS translation_cache (
                    id INTEGER PRIMARY KEY,
                    source_text TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    src_lang TEXT NOT NULL,
                    tgt_lang TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source_text, engine, src_lang, tgt_lang)
                )
                """
            )
            conn.commit()

    # ---------- 读 ----------
    def get(
        self, source: str, engine: str, src_lang: str, tgt_lang: str
    ) -> Optional[str]:
        conn = self._conn
        if conn is None:
            return None
        with self._lock:
            cur = conn.execute(
                "SELECT translated_text FROM translation_cache "
                "WHERE source_text=? AND engine=? AND src_lang=? AND tgt_lang=?",
                (source, engine, src_lang, tgt_lang),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def get_many(
        self,
        sources: Sequence[str],
        engine: str,
        src_lang: str,
        tgt_lang: str,
    ) -> Dict[str, str]:
        """一次查询多条，返回 {source: translated}。"""
        conn = self._conn
        if conn is None or not sources:
            return {}
        result: Dict[str, str] = {}
        BATCH = 500
        with self._lock:
            for i in range(0, len(sources), BATCH):
                chunk = [s for s in sources[i : i + BATCH] if s]
                if not chunk:
                    continue
                placeholders = ",".join("?" * len(chunk))
                cur = conn.execute(
                    "SELECT source_text, translated_text FROM translation_cache "
                    f"WHERE engine=? AND src_lang=? AND tgt_lang=? "
                    f"AND source_text IN ({placeholders})",
                    [engine, src_lang, tgt_lang, *chunk],
                )
                for src, tr in cur.fetchall():
                    result[src] = tr
        return result

    # ---------- 写 ----------
    def put(
        self,
        source: str,
        engine: str,
        src_lang: str,
        tgt_lang: str,
        translated: str,
    ) -> None:
        self.put_many([(source, translated)], engine, src_lang, tgt_lang)

    def put_many(
        self,
        items: Iterable[Tuple[str, str]],
        engine: str,
        src_lang: str,
        tgt_lang: str,
    ) -> None:
        conn = self._conn
        if conn is None:
            return
        rows = [
            (src, engine, src_lang, tgt_lang, trans)
            for src, trans in items
            if src and trans
        ]
        if not rows:
            return
        with self._lock:
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO translation_cache "
                    "(source_text, engine, src_lang, tgt_lang, translated_text) "
                    "VALUES (?, ?, ?, ?, ?)",
                    rows,
                )

    def update(
        self,
        source: str,
        engine: str,
        src_lang: str,
        tgt_lang: str,
        translated: str,
    ) -> None:
        self.put(source, engine, src_lang, tgt_lang, translated)

    # ---------- 生命周期 ----------
    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None