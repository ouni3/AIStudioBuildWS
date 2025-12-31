# AIStudioBuildWS - 技术文档

## 技术栈

### 核心语言
- **Python 3.11** - 主要开发语言

### 浏览器自动化
- **Camoufox 0.4.11** - 反检测浏览器（基于 Firefox）
- **Playwright 1.52.0** - 浏览器自动化框架

### Web 框架
- **Flask 3.0.0** - 用于 HuggingFace Spaces 健康检查端点

### 容器化
- **Docker** - 基于 `python:3.11-slim-bookworm`
- **Docker Compose** - 容器编排

## 开发环境设置

### 本地开发
```bash
# 克隆仓库
git clone https://github.com/hkfires/AIStudioBuildWS.git
cd AIStudioBuildWS

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 下载 Camoufox 浏览器
camoufox fetch

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件

# 运行
python main.py
```

### Docker 开发
```bash
# 构建并启动
docker compose up -d --build

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

## 环境变量

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `CAMOUFOX_INSTANCE_URL` | ✅ | - | AIStudio 应用程序 URL |
| `CAMOUFOX_HEADLESS` | ❌ | `virtual` | 浏览器模式：`true`/`false`/`virtual` |
| `CAMOUFOX_PROXY` | ❌ | - | 代理服务器地址 |
| `INSTANCE_START_DELAY` | ❌ | `30` | 实例启动间隔（秒） |
| `CAMOUFOX_PROJECT_ROOT` | ❌ | - | 项目根目录（自动检测） |
| `HG` | ❌ | - | 设为 `true` 启用服务器模式 |
| `USER_COOKIE_1` | ✅* | - | 第一个账户的 Cookie |
| `USER_COOKIE_2` | ❌ | - | 第二个账户的 Cookie |
| ... | ... | ... | 支持更多 USER_COOKIE_N |

*至少需要一个 Cookie 来源（环境变量或 cookies/ 目录下的 JSON 文件）

## 技术约束

### 浏览器运行模式
1. **headless=true**：完全无头模式，无图形界面
2. **headless=false**：正常模式，显示浏览器窗口
3. **headless=virtual**（默认）：虚拟显示模式，使用 Xvfb

### Cookie 格式支持
1. **Cookie-Editor JSON 格式**：
```json
[{"name": "__Secure-1PSID", "value": "...", "domain": ".google.com", ...}]
```

2. **KV 字符串格式**：
```
__Secure-1PSID=...; __Secure-1PAPISID=...; ...
```

### 进程管理
- 使用 `multiprocessing.Process` 创建子进程
- 通过 `multiprocessing.Event` 实现跨进程信号
- 支持 SIGTERM/SIGINT 优雅关闭

## 依赖说明

### 核心依赖
| 包名 | 版本 | 用途 |
|------|------|------|
| camoufox | 0.4.11 | 反检测浏览器 |
| playwright | 1.52.0 | 浏览器自动化 |
| flask | 3.0.0 | Web 服务器 |
| requests | 2.32.4 | HTTP 客户端 |

### 系统依赖（Docker 中安装）
- libgtk-3-0, libgbm1, libnss3 等 - 浏览器运行依赖
- xvfb - 虚拟帧缓冲区
- socat - 端口转发（用于绕过 Mixed Content 限制）

## 工具使用模式

### 日志
- 统一使用 `utils/logger.py` 中的 `setup_logging()` 函数
- 日志同时输出到控制台和文件
- 支持进程前缀标识

### 路径管理
- 使用 `utils/paths.py` 中的函数获取路径
- `logs_dir()` - 日志和截图目录
- `cookies_dir()` - Cookie 文件目录

### 错误处理
- 导航错误时自动截图保存
- 详细的错误日志和诊断信息
- Cookie 失效时自动关闭实例

## 部署注意事项

### HuggingFace Spaces
- 需要设置 `HG=true` 启用服务器模式
- 端口暴露为 7860
- Cookie 必须存储在 Secrets 中（非 Variables）

### Docker 本地部署
- 使用 `docker-compose.override.yml` 进行本地开发配置
- 日志和截图挂载到宿主机
- 内置 socat 端口转发