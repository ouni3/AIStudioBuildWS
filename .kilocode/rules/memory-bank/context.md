# AIStudioBuildWS - 当前上下文

## 当前状态
项目已完成架构重构，从多进程模式迁移至**单进程异步模式 (Asyncio)**，显著降低了内存占用（~6GB -> ~1GB）。目前已部署在 Windows 远程服务器上，并应用了 Firefox 后台防冻结补丁以确保长连接稳定性。

## 最近变更
### 架构重构：单进程异步化 (2026-01-16)
- **Abstract**: 使用 `AsyncCamoufox` 和 `asyncio` 重写核心逻辑，所有账号共享一个浏览器实例，通过 `BrowserContext` 隔离。
- **Keywords**: `AsyncCamoufox`, `BrowserManager`, `asyncio`, `Memory Optimization`

### 修复：Firefox 后台冻结问题 (2026-01-16)
- **Abstract**: 注入 Firefox 首选项 (`dom.min_background_timeout_value=4` 等) 以禁用后台标签页的定时器节流，防止 WebSocket 心跳因页面不活跃而断开。
- **Keywords**: `firefox_user_prefs`, `background throttling`, `WebSocket stability`

### 部署优化：Windows Docker 网络 (2026-01-16)
- **Abstract**: 在 Windows Docker 环境下使用 `network_mode: host` 成功打通容器到宿主机 8317 端口的连接。
- **Keywords**: `network_mode: host`, `8317`, `CLIProxyAPI`

### 稳定性：错峰启动 (2026-01-16)
**Abstract**: 实现每个账号间隔 15 秒启动，避免单浏览器实例瞬间 CPU 负载过高导致导航超时。
**Keywords**: `delayed_run_context`, `Staggered Start`

### 修复：Logger 全局单例污染 (2026-01-16)
**Abstract**: 修复了 `setup_logging` 使用固定名称导致所有账号日志前缀都被最后一个启动账号覆盖的问题。
**Keywords**: `logger_name`, `getLogger(prefix)`, `Logger isolation`

### 修复：Mixed Content 拦截 (2026-01-16)
**Abstract**: 通过注入 `security.mixed_content.block_active_content=false` 解决了 HTTPS 页面无法连接本地非加密 WebSocket 的问题。
**Keywords**: `Mixed Content`, `block_active_content`, `HTTPS to WS`

## 当前工作重点
- 验证新架构在长期运行（>24小时）下的稳定性，特别是 WebSocket 连接是否会因未知的浏览器行为而断开。
- 确认为期 24 小时的稳定性测试通过。

### Cookie 验证结果 (2026-02-04)
- **Abstract**: 使用 Playwright (Firefox) 验证了 `.env` 中所有 8 个 `USER_COOKIE_N` 环境变量，并使用 MCP Puppeteer 重点交叉验证了 COOKIE_6 和 COOKIE_8。结果显示所有 Cookie 均有效，成功导航至 AI Studio 目标页面且未触发登录重定向。
- **Keywords**: `Cookie Verification`, `Playwright`, `USER_COOKIE_1-8`, `MCP Puppeteer`, `Success`

### 增强：WebSocket 业务日志 (2026-02-04)
- **Abstract**: 增强了 `WebSocketLogger`，支持从加密的 WebSocket 流量中启发式提取模型名称 (如 `gemini-1.5-flash`) 和响应状态。现在日志能清晰显示哪个 Cookie 实例正在处理特定的 AI 请求。
- **Keywords**: `Heuristic Extraction`, `Model ID`, `WebSocketLogger`, `Business Visibility`

## 已知问题
- **Windows Docker 网络限制**: `network_mode: host` 在 Windows 上的行为特殊，目前仅用于解决 localhost 访问问题。
- **单点故障风险**: 由于共享浏览器实例，若浏览器进程崩溃，所有账号将同时掉线（目前通过 Docker 重启策略缓解）。

## 待办事项
暂无