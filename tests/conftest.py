"""
Pytest 配置文件
为 E2E 测试提供共享 fixtures 和配置
"""

import pytest
import sys
import os

# 确保项目根目录在 Python path 中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def pytest_configure(config):
    """Pytest 启动时的全局配置"""
    config.addinivalue_line(
        "markers",
        "asyncio: mark test as an asyncio coroutine"
    )


@pytest.fixture(scope="session")
def proxy_url():
    """获取当前配置的代理 URL"""
    return os.getenv("HTTPS_PROXY", "http://host.docker.internal:7897")


@pytest.fixture(scope="session")
def target_url():
    """获取测试目标 URL"""
    return "https://accounts.google.com"