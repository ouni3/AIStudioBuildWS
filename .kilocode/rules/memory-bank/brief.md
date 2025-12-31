# AIStudioBuildWS - 项目简要

## 项目名称
AIStudioBuildWS (AI Studio Build WebSocket)

## 项目定位
一个自动化工具，用于在 HuggingFace Spaces 或 Docker 环境中部署无头浏览器，自动维护 Google AI Studio 的 WebSocket 连接。

## 核心目标
1. 自动化管理 Google AI Studio 的 WebSocket 通信程序
2. 支持多账户 Cookie 管理
3. 实现零成本部署（利用 HuggingFace 免费实例）
4. 与 CLIProxyAPI 项目配合使用

## 关键约束
- 必须与 CLIProxyAPI v6.3.x+ 配合使用
- 需要有效的 Google AI Studio Cookie
- 支持 Docker 和 HuggingFace Spaces 两种部署方式

## 成功标准
- 浏览器实例能够稳定运行
- Cookie 能够正确验证和刷新
- WebSocket 连接保持活跃
- 多账户能够同时工作