"""MC Mod Translator.

包加载时尽早让 Python 使用系统证书存储（Windows / macOS），
以避免 httpx / requests 等库因缺少中间证书而报
SSL: CERTIFICATE_VERIFY_FAILED。

必须在任何 SSL 连接建立之前调用，因此放在包的 __init__ 里。
"""

from __future__ import annotations

__version__ = "0.2.0"


def _inject_truststore() -> None:
    try:
        import truststore  # type: ignore

        truststore.inject_into_ssl()
    except Exception:
        # truststore 未安装 / 注入失败：退回到 certifi（httpx 默认）
        pass


_inject_truststore()