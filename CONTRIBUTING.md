# 贡献指南

感谢参与 MC Mod Translator。

## 项目定位

让**普通玩家零配置**就能翻译 Minecraft 整合包。任何改动都要以此为最高优先级：

- 玩家第一次打开程序，**不应该**被要求注册账号、填 API Key、看文档
- 新功能默认关闭或隐藏，除非它明显改善玩家体验
- 报错要给玩家看**人话**，不是 Python traceback

## 环境准备

```bash
git clone https://github.com/<your-name>/mc-mod-translator.git
cd mc-mod-translator
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[gui,dev]"
```

国内建议配置 pip 镜像：

```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

本地模型（可选）：

```bash
pip install -e ".[local]"
```

## 开发流程

1. 从 `main` 拉分支：`git checkout -b feat/your-topic`
2. 写代码 + 写测试
3. 本地跑：`pytest -v`
4. 提交 PR

### 分支命名

- `feat/xxx` — 新功能
- `fix/xxx` — 修复
- `docs/xxx` — 文档
- `refactor/xxx` — 重构
- `chore/xxx` — 杂项

## 代码规范

### 通用

- Python 3.10+，所有 Python 文件头 `from __future__ import annotations`
- 类型注解尽量完整，`Optional[X]` 与 `X | None` 单文件保持一致
- 不引入未使用的 import
- 不引入新的重量级依赖（除非有充分理由）

### GUI 代码

- 实例属性一律带 `self.` 前缀
- 不要在 GUI 线程里做网络请求
- 长任务必须放到 `QThread` 里
- 用户可见的错误用 `QMessageBox`，技术细节进日志

### 引擎代码

- 所有异常从 `engines.base` 抛：
  - `EngineConfigError` — 配置缺失
  - `EngineAuthError` — 认证失败
  - `EngineQuotaError` — 额度耗尽
  - `EngineRateLimitError` — 429 限流
  - `EngineTimeoutError` — 网络超时
  - `EngineResponseError` — 响应结构异常
  - `EngineFatalError` — 上述"不可恢复"类的基类
- 网络请求复用 `BaseEngine._get_client()`
- 不要把 `RuntimeError` 直接抛出（Translator 会把它当可重试错误）

### 测试

- 新增功能**必须**带测试
- GUI 相关代码不强求单测，但核心逻辑必须测
- 覆盖率不是目标，**能测出回归**才是

```bash
pytest                     # 全部
pytest tests/test_cache.py # 单文件
pytest -k placeholder      # 按名筛选
```

## 提交信息

格式：`<type>(<scope>): <subject>`

- `feat:` 新功能
- `fix:` 修复
- `docs:` 文档
- `refactor:` 重构
- `test:` 测试
- `chore:` 杂项

例子：

```
fix(scanner): 识别 en_US.lang 大写变体
feat(engines): 新增 auto_free 免费引擎
docs(readme): 主教程改为零配置路径
```

## PR 要求

- 标题简明（推荐用上面同样的格式）
- 描述包含：做了什么、为什么、怎么测
- 如果改了 UI，附上截图
- 如果有 breaking change，明确标注
- CI 必须通过

## 目录约定

```
mc_mod_translator/
├── engines/          # 引擎实现
│   ├── base.py       # 基类 + 异常
│   ├── builtin.py    # 付费引擎
│   ├── free.py       # 免费引擎
│   └── registry.py   # 注册表
├── gui/              # GUI 代码
├── tests/            # 测试
└── *.py              # 核心模块
```

- 脚本放 `scripts/`，不放项目根
- 文档放 `docs/`
- 截图放 `docs/images/`

## 打包测试

改动 `launcher.py` 或 `gui/` 后，**必须**验证 PyInstaller 打包：

```bash
pyinstaller --onefile --windowed --name MCModTranslator ^
  --collect-all PySide6 ^
  --collect-all shiboken6 ^
  --hidden-import PySide6.QtCore ^
  --hidden-import PySide6.QtGui ^
  --hidden-import PySide6.QtWidgets ^
  --hidden-import PySide6.QtSvg ^
  --exclude-module PyQt5 ^
  --exclude-module PyQt6 ^
  --exclude-module tkinter ^
  --exclude-module transformers ^
  --exclude-module torch ^
  --noconfirm --clean ^
  launcher.py
```

**不要**直接打包 `mc_mod_translator/gui/main.py`——相对导入会失败。

## 发布

维护者用：

```bash
python scripts/bump_version.py 0.4.0 --tag
git add -A
git commit -m "chore: release v0.4.0"
git push
git push origin v0.4.0
```

推 tag 后 GitHub Actions 会自动构建三平台产物并创建 Release。

## License

提交的代码默认以 MIT 协议授权。