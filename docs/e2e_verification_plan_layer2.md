# Layer 2 Integration E2E Verification Plan (L1 Designed)

## 1. 验证目标与不变量 (System Invariants)
验证 `BrowserManager` (Layer 2 调度层) 的核心控制与防御机制，不依赖具体站点的 DOM，确保高健壮性与隔离度。
- **并发与资源控制 (Semaphore)**：验证 `max_concurrent_navigations = 2` 下信号量的获取与精确释放，无泄漏。
- **环境隔离性 (Isolation)**：确保两个账户的 Session、Cookie 互不干扰，其各自产生的日志、截图和 WebSocket 记录在物理目录中隔离。
- **快速自愈斩杀 (Kill Switch)**：验证重定向到登录界面 (`accounts.google.com`, `signin`, `login`) 时在 1 秒内强制杀死上下文，安全回收信号量。
- **WebSocket 消息分流录制**：验证两个账户产生的 WS 消息由各自的 `ws_logger` 隔离记录落盘，不交叉。

## 2. 隔离文件与目录结构
测试套件的所有产物将归于隔离路径，不交叉污染。
```text
artifacts/layer2/<run_id>/
  user_1/
    logs/browser.log
    screenshots/final.png
    ws/ws.jsonl
  user_2/
    logs/browser.log
    screenshots/final.png
    ws/ws.jsonl
```

## 3. 测试用例总矩阵 (Pytest)
测试脚本存放在 `tests/integration/test_layer2_integration.py` 目录下。

| 测试函数 | 目标 | 验证逻辑与核心断言 |
|:---|:---|:---|
| `test_layer2_semaphore_and_resource_blocking` | 并发与资源阻断 | 1. 2 个账户同时并发执行 `navigate_with_account`。<br>2. 验证观察者信号量：`max_in_flight <= 2`，`current_in_flight == 0`。<br>3. 验证图片/媒体/字体类型的请求被 Abort。 |
| `test_layer2_context_isolation_and_artifact_separation` | 会话与产物隔离 | 1. 同时打开两个账户 Session。<br>2. 验证其 `context_id` 与 `page_id` 物理不同。<br>3. 验证 Cookie 散列指纹不重合，无重叠 Cookie。<br>4. 验证各自生成的 log、screenshot 在物理分区中隔离。 |
| `test_layer2_kill_switch_releases_semaphore_on_login_redirect` | 登录重定向斩杀 | 1. 使用 redirect 路由/fixture（模式匹配：`accounts.google.com`, `signin`）。<br>2. 验证 `elapsed_ms <= 1000` 内关闭 page，并释放信号量。 |
| `test_layer2_websocket_recording_isolated_by_account` | WebSocket 录制分流 | 1. 并发导航至 WS 真实/模拟路由。<br>2. 两个账户各自生成对应的 `.jsonl`。<br>3. 消息中的 `account_id` 字段完全对应，无交叉混淆。 |

## 4. WSL2 资源控制与运行限制
- **浏览器额外参数 (WSL2 防爆)**:
  - `--no-sandbox`
  - `--disable-dev-shm-usage`
  - `--disable-gpu`
- **运行资源阻断**: 拦截 `image`, `media`, `font` 请求。
- **并发数限制**: pytest `workers: 1` (-n 0), `max_concurrent_navigations = 2`。

## 5. 熔断与防错规则
- 缺少 `.env` 中的 `USER_COOKIE_1` 或 `USER_COOKIE_2` 时，测试套件必须优雅跳过 (`pytest.skip`)。
- 禁止任何 Cookie 原文输出到 stdout/stderr/logs 中。
