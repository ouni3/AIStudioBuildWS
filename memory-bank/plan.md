# Cookie 验证与 Layer 2 集成 E2E 验证计划

## 1. 环境准备
- [x] 安装依赖 (camoufox, playwright, dotenv)
- [x] 确保浏览器二进制文件可用 (playwright install firefox, camoufox fetch)

## 2. 执行验证
- [x] 运行 `verify_env_cookies.py` 扫描 `.env` 中的所有 `USER_COOKIE_N`
- [x] 记录验证结果

## 3. L2 集成验证规划与实施 (2026-05-26)
- [ ] 创建隔离的测试辅助模块 `tests/integration/helpers/` (Cookie 加载与路径生成)
- [ ] 为 `BrowserManager` 提供最小化观察者/测试钩子
- [ ] 编写 4 个核心测试用例 (`test_layer2_integration.py`):
  - [ ] Semaphore 限制与资源阻断
  - [ ] Context 隔离与物理路径规整
  - [ ] 登录重定向 1s 内快速斩杀
  - [ ] WebSocket 各自独立落盘
- [ ] WSL2 环境资源防爆调优 (单 worker, no-sandbox)
- [ ] 清理临时日志与 artifacts 产物，完成合规审计

## 4. 验证结果 (2026-04-22 / 2026-05-26)
- **有效**: USER_COOKIE_1, USER_COOKIE_2, USER_COOKIE_5, USER_COOKIE_6
- **异常 (界面加载问题)**: USER_COOKIE_3, USER_COOKIE_4, USER_COOKIE_7
- **失效 (登录重定向)**: USER_COOKIE_8, USER_COOKIE_9, USER_COOKIE_10, USER_COOKIE_11, USER_COOKIE_12

> [!IMPORTANT]
> 由于权限熔断限制，无法更新 `systemPatterns.md`。WebSocket 隧道原理已记录至 `docs/ws_tunnel_architecture.md`。
