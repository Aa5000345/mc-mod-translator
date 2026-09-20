# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

（开发中的改动）

## [0.3.0] - 2026-09-20

### Added

- **`auto_free` 引擎（新的默认引擎）**：普通玩家打开即用，无需注册、无需 API Key、无需充值
- **`mymemory` 引擎**：免费翻译服务，匿名每日约 10000 字符，可选填邮箱提升到 50000 字符
- **`truststore` 依赖**：让 Python 使用 Windows/macOS 系统证书存储，从根上解决 `SSL: CERTIFICATE_VERIFY_FAILED`
- `MCMT_INSECURE=1` 环境变量：临时跳过 SSL 验证（仅供排查问题）
- `scripts/bump_version.py`：一键更新版本号（pyproject.toml / \_\_init\_\_.py / README 徽章）
- 免费引擎的"失败不中止"机制：单条翻译失败返回原文，整批翻译继续进行
- `EngineFatalError` / `EngineQuotaError` 异常体系
- `AutoFreeEngine` 的 429 限流自动等待重试
- 大量测试用例（111 个）

### Fixed

- **占位符被引擎塞空格后无法还原**：如 `__PH_0__` 被 MyMemory 变成 `__ PH_0 __`，改用正则匹配所有空格变形
- **auto_free 所有后端失败时抛异常导致整批中止**：改为返回原文，由 Translator 记为失败
- **MyMemory 原样返回被误判为翻译成功**：现在正确识别为失败
- **`ENGINE_REQUIRED_FIELDS` 缺失 `auto_free` / `mymemory`**：修复导入错误
- **MyMemory 的 `html.unescape` 顺序错误**：先判断原样返回，再 unescape
- **免费引擎 SSL 证书验证失败**：显式使用 certifi + truststore 注入
- **`registry.py` 与 `engine_dialog.py` 版本不一致**：统一字段收集逻辑
- **PyInstaller 打包入口相对导入失败**：新增顶层 `launcher.py`
- **`QThread: Destroyed while thread is still running`**：`closeEvent` 中等待线程退出

### Changed

- 默认引擎从 `openai` 改为 `auto_free`
- 默认并发数从 `8` 改为 `1`（免费服务限速）
- 引擎下拉框把 `auto_free` 排到第一位
- 切换到免费/低 QPS 引擎时，并发数自动降到 1
- `EngineConfigDialog` 顶部显示每个引擎的获取方式/官方地址
- GUI 弹窗不再显示完整 traceback，改为友好信息（traceback 保留在日志里）
- `README.md` 主教程改为"零配置路径"，"申请 API Key"移到进阶用法

### Removed

- `pytest-asyncio` 依赖（当前没有 async 测试）
- `asyncio_mode = "auto"` 配置（消除 pytest 警告）

## [0.2.0] - 2026-09-19

### Added

- **`langfile.py`**：语言码规范化（`normalize_lang_code` / `target_lang_filename` / `lang_filename_candidates`）
- 老版本 `.lang` 资源包现在正确写出 `zh_CN.lang`（大写下划线）而非 `zh_cn.lang`
- 扫描器识别源文件 `en_us.json` / `en_US.lang` / `en_us.lang`；已有翻译识别 `zh_cn.json` / `zh_CN.lang` / `zh_cn.lang`
- **jar-in-jar 扫描**：递归读取 `META-INF/jarjar/*.jar`
- 目标语言选择：GUI 下拉框、CLI `--target-lang`
- **人工校对统一引擎名 `manual`**：Translator 查找顺序：术语表 → `manual` 缓存 → 当前引擎缓存
- `TranslationCache.put_many` / `get_many`，SQLite 开启 WAL + `synchronous=NORMAL`
- 翻译重试：3 次指数退避（`2 ** attempt + random.random()`）
- 占位符还原校验 `validate_restore`，失败判定为翻译失败并重试
- 取消翻译：GUI“取消翻译”按钮、`Translator(cancel_event=...)`
- 失败 key 汇总列表
- 校对窗口：分页、搜索、按 Mod 过滤、批量替换、占位符校验、草稿自动保存
- GUI 拖拽整合包根目录 / mods 文件夹（`DropLineEdit`）
- GUI 记忆上次目录与窗口几何（`gui_state.json`）
- 翻译前预览：jar 数、语言文件数、已有/缺失 key、唯一待翻译文本
- 双进度条（文件 / 文本）
- 日志时间戳，导出 `.log`
- 双击结果表格行，只打开该 mod 的校对窗口
- CLI `SimpleProgress` 进度条（无依赖）
- CLI `--log-file`、`--gui`
- CLI `proofread export` 真正实现
- 引擎统一异常体系
- 429 限流识别（`Retry-After` 解析）
- 复用 httpx.AsyncClient
- OpenAI 兼容引擎 `translate_batch`
- Gemini safety settings
- Claude `max_tokens` 可配置
- NLLB 引擎加全局线程锁
- `pack.mcmeta` 支持 `supported_formats`
- 完整测试套件 + CI 工作流（`build-dev.yml` / `release.yml`）

### Fixed

- `versions/1.20.1-forge-47.2.0` 形式目录无法被识别
- 引擎配置对话框切换引擎丢失未保存字段
- `region` 不再被当作秘密
- 空值可以清空配置
- `system_prompt` 改为 `QPlainTextEdit`
- 同一 mod 同一 fmt 的多个 `LangEntry` 打包时互相覆盖
- `proofread.import_csv` 默认写入 `proofread` 引擎名导致缓存查不到
- `TranslationCache.close()` 重复调用抛异常
- `parse_version("1.13")` 返回 `(1, 13)` 与 `PACK_FORMAT_TABLE` 三元组不一致

### Changed

- `region` 从加密字段中移除
- 校对 CSV 导入需要显式传目标语言
- NLLB 引擎加载走 `threading.Lock`

## [0.1.0] - 2026-09-01

### Added

- 初始版本
- 项目骨架
- GUI（PySide6）+ CLI（Typer）
- 支持 `.json` / `.lang` 两种语言文件
- 支持合并资源包 / 每个 mod 单独资源包
- 多引擎支持：OpenAI、DeepSeek、Claude、Gemini、DeepL、Google、Microsoft、百度、Ollama、LibreTranslate、NLLB
- 翻译缓存 + 术语表
- 占位符保护（`%s`、`{0}`、`§a` 等）
- 已有 `zh_cn` 自动保留，仅补全缺失 key
- 可选自动安装到整合包 `resourcepacks`

[Unreleased]: https://github.com/<your-name>/mc-mod-translator/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/<your-name>/mc-mod-translator/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/<your-name>/mc-mod-translator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/<your-name>/mc-mod-translator/releases/tag/v0.1.0