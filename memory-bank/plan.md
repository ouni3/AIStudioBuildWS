# Cookie 验证任务计划

## 1. 环境准备
- [x] 安装依赖 (camoufox, playwright, dotenv)
- [x] 确保浏览器二进制文件可用 (playwright install firefox, camoufox fetch)

## 2. 执行验证
- [x] 运行 `verify_env_cookies.py` 扫描 `.env` 中的所有 `USER_COOKIE_N`
- [x] 记录验证结果

## 3. 结果整理
- [ ] 汇总有效和失效的 Cookie
- [ ] 输出报告

## 4. 验证结果 (2026-04-22)
- **有效**: USER_COOKIE_1, USER_COOKIE_2, USER_COOKIE_5, USER_COOKIE_6
- **异常 (界面加载问题)**: USER_COOKIE_3, USER_COOKIE_4, USER_COOKIE_7
- **失效 (登录重定向)**: USER_COOKIE_8, USER_COOKIE_9, USER_COOKIE_10, USER_COOKIE_11, USER_COOKIE_12
