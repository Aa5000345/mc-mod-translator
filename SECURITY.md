# 安全策略

## 支持的版本

| 版本 | 状态 |
| --- | --- |
| 0.3.x | ✅ 支持 |
| 0.2.x | ⚠️ 仅严重漏洞 |
| 0.1.x | ❌ 不再支持 |

## 报告漏洞

请**不要**在公开 issue 中报告安全漏洞。

优先使用 GitHub 的 [Private vulnerability reporting](https://docs.github.com/zh/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)：

1. 打开仓库的 **Security** 标签页
2. 点击 **Report a vulnerability**
3. 填写复现步骤与影响

如果无法使用 Private reporting，请邮件联系维护者（见仓库主页）。

请在报告中包含：

- 漏洞类型（例如：路径穿越、SQL 注入、敏感信息泄露）
- 完整复现步骤
- 受影响的版本
- 潜在影响范围
- 如果你有修复建议，一并提供

## 响应时间

- 3 个工作日内确认收到
- 30 天内给出修复或缓解方案（视复杂度而定）
- 修复后会在 `CHANGELOG.md` 中致谢（除非你希望匿名）

## 涉及范围

本项目处理的内容包括：

- Minecraft mod 中的语言文件（**不可信输入**）
- 用户填写的 API Key（本地加密存储）
- 用户的整合包目录、mods 目录
- 用户导入/导出的校对 CSV

## 已知攻击面

### 恶意 `.jar` 中的语言文件

- **zip 炸弹**：`META-INF/jarjar/` 中的嵌套 jar 可能嵌套多层
  - 缓解：`scan_jar` 只递归一层，且捕获所有异常
- **路径穿越**：zip 内路径含 `../`
  - 缓解：只读取 `assets/*/lang/*` 形式路径，不写入文件系统
- **超大语言文件**：占用内存
  - 缓解：暂未限制；如需处理，可在 `scan_jar` 中加文件大小上限

### 校对 CSV 的公式注入

校对 CSV 被 Excel 打开时，以 `=`、`+`、`-`、`@` 开头的单元格可能被当作公式执行。

- **缓解**：`SECURITY.md` 提示用户用文本方式打开
- **未彻底解决**：可在 `export_csv` 时加 `'` 前缀，但会破坏正常译文中的 `%` 等字符

### API Key 存储

- 使用 Fernet（`cryptography` 库）加密，密钥在 `key.bin`
- `key.bin` 权限设为 `0600`（仅所有者可读）
- `secrets.enc` 与 `key.bin` 在 `.gitignore` 中排除
- 环境变量优先级高于配置文件

### 网络请求

- 引擎 SSL 验证使用 `certifi` + `truststore`（系统证书存储）
- 提供 `MCMT_INSECURE=1` 环境变量可跳过验证，**仅供排查问题**
- 不建议长期启用 `MCMT_INSECURE`

## 用户建议

- 只翻译来源可信的整合包
- 用 Excel 打开校对 CSV 前，注意以 `=`、`+`、`-`、`@` 开头的单元格可能被当作公式
- 不要把 `secrets.enc`、`key.bin`、`config.yaml` 提交到版本库（`.gitignore` 已默认忽略）
- 定期检查 `~/.mc_mod_translator/` 下的文件权限
- 如果怀疑 API Key 泄露，立即到对应平台**撤销**并**重新创建**

## 依赖安全

- 依赖通过 `pyproject.toml` 声明，锁版本用 `>=` 而非 `==`，便于接收安全更新
- GitHub Actions 每周运行一次（`build-dev.yml` 触发），可及时发现依赖问题
- 建议启用 GitHub 的 **Dependabot alerts** 与 **Dependabot security updates**