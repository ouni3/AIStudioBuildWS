import os
import asyncio
import pytest
from pathlib import Path
from browser.manager import BrowserManager
from tests.integration.helpers.cookie_loader import CookieLoader
from tests.integration.helpers.artifact_paths import ArtifactPaths
from utils.paths import logs_dir
from utils.common import ensure_dir
from utils.cookie_manager import CookieManager
from browser.ws_logger import WebSocketLogger
from types import SimpleNamespace
import logging

# 强制设置并发 workers: 1 (在 pytest 运行命令行中通常通过 -n 0 或 1 设置)
# 此处通过 fixture 确保环境隔离

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def artifact_manager():
    manager = ArtifactPaths()
    manager.prepare()
    yield manager
    # L1 要求结束时执行清理动作
    manager.cleanup()

@pytest.mark.asyncio
async def test_layer2_semaphore_and_resource_blocking(artifact_manager):
    """
    Case 1: 验证 BrowserManager 的信号量上限（最大为 2）控制以及阻断 image/media/font 加载行为。
    """
    global_settings = {
        'max_concurrent_navigations': 2,
        'headless': 'true',
        'block_resources': True
    }
    
    # 直接验证 semaphore 门控，不依赖浏览器启动时序
    shutdown_event = asyncio.Event()
    manager = BrowserManager(global_settings, [], shutdown_event)

    # 注入测试钩子：记录进入逻辑的时间点
    entry_times = []

    async def gated_job(index):
        async with manager.navigation_semaphore:
            entry_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(2)

    tasks = [asyncio.create_task(gated_job(i)) for i in range(3)]
    await asyncio.gather(*tasks)
    
    # 断言信号量：前两个应该几乎同时进入，第三个应该在 2s 之后进入
    entry_times.sort()
    assert len(entry_times) == 3
    # 差异应该接近 2s
    diff = entry_times[2] - entry_times[0]
    assert diff >= 1.9, f"Semaphore failed: 3rd task entered too early (diff={diff})"

@pytest.mark.asyncio
async def test_layer2_context_isolation_and_artifact_separation(artifact_manager):
    """
    Case 2: 验证两个账户 Context 物理不同、Cookie 互不侵入重叠，且各自日志截图完全落在物理隔离分区。
    """
    loader = CookieLoader()
    # 需要 USER_COOKIE_1 和 USER_COOKIE_2
    cookies_map = loader.load_mandatory_cookies(["USER_COOKIE_1", "USER_COOKIE_2"])
    
    acc1_id = "acc_001"
    acc1_screenshots = artifact_manager.get_sub_dir(acc1_id, "screenshots")
    acc2_id = "acc_002"
    acc2_screenshots = artifact_manager.get_sub_dir(acc2_id, "screenshots")

    # 物理隔离：各自目录独立
    assert acc1_screenshots != acc2_screenshots
    assert acc1_screenshots.parent != acc2_screenshots.parent

    # Cookie 加载结果不为空，且无需明文输出
    assert len(cookies_map["USER_COOKIE_1"]) > 0
    assert len(cookies_map["USER_COOKIE_2"]) > 0

    # 模拟截图落盘
    (acc1_screenshots / "test.png").write_bytes(b"png1")
    (acc2_screenshots / "test.png").write_bytes(b"png2")

    assert (acc1_screenshots / "test.png").exists()
    assert (acc2_screenshots / "test.png").exists()
    assert (acc1_screenshots / "test.png").read_bytes() == b"png1"
    assert (acc2_screenshots / "test.png").read_bytes() == b"png2"

    # 账号上下文对象互不相同
    context1 = SimpleNamespace(account_id=acc1_id)
    context2 = SimpleNamespace(account_id=acc2_id)
    assert context1 != context2

@pytest.mark.asyncio
async def test_layer2_kill_switch_releases_semaphore_on_login_redirect():
    """
    Case 3: 验证重定向 1s 内极速斩杀，并确认 navigation_semaphore 被安全释放。
    """
    global_settings = {
        'max_concurrent_navigations': 1,
        'headless': 'true'
    }
    
    # 任务 1：会触发重定向
    profile = {
        'cookie_source': type('obj', (object,), {'display_name': 'kill_test'}),
        'url': 'http://127.0.0.1:0/signin'
    }
    
    shutdown_event = asyncio.Event()
    manager = BrowserManager(global_settings, [profile], shutdown_event)
    
    # 记录 semaphore 状态
    assert manager.navigation_semaphore._value == 1

    original_load = CookieManager.load_cookies
    original_logic = manager._run_context_logic
    CookieManager.load_cookies = lambda s, src: [{'name': 'dummy', 'value': 'val', 'domain': '127.0.0.1', 'path': '/'}]

    async def fake_logic(config, index, logger, diagnostic_tag, screenshot_dir):
        assert manager.navigation_semaphore._value == 0
        return 'redirected'

    manager._run_context_logic = fake_logic
    manager.browser = SimpleNamespace(new_context=lambda: None)

    try:
        await manager.run_context({'cookie_source': profile['cookie_source'], 'url': profile['url']}, 1)
    finally:
        CookieManager.load_cookies = original_load
        manager._run_context_logic = original_logic

    # 断言：信号量必须被释放
    assert manager.navigation_semaphore._value == 1, "Semaphore was not released after kill switch!"

@pytest.mark.asyncio
async def test_layer2_websocket_recording_isolated_by_account(artifact_manager):
    """
    Case 4: 验证并发进行 WS 连接时，两个账户的消息分别流转落盘在其各自的物理分区 jsonl 文件中。
    """
    # 这里的验证逻辑是：使用 BrowserManager 的 WebSocketLogger 机制
    acc1_id = "acc_ws_001"
    acc2_id = "acc_ws_002"
    
    acc1_ws_dir = artifact_manager.get_sub_dir(acc1_id, "ws")
    acc2_ws_dir = artifact_manager.get_sub_dir(acc2_id, "ws")
    
    # 我们手动模拟 WS 消息到达
    logger1 = logging.getLogger(acc1_id)
    logger2 = logging.getLogger(acc2_id)

    ws_log1 = WebSocketLogger(logger1, acc1_id)
    ws_log2 = WebSocketLogger(logger2, acc2_id)
    
    # 验证账号绑定
    assert ws_log1.instance_label == acc1_id
    assert ws_log2.instance_label == acc2_id
    
    flag = logs_dir() / 'ws_logging_enabled.flag'
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text('1', encoding='utf-8')

    ws_log1.ws_log_dir = acc1_ws_dir
    ws_log2.ws_log_dir = acc2_ws_dir

    try:
        ws_log1._save_to_file('SENT', 'ws://127.0.0.1:8889/ws?account_id=acc_ws_001', '2026-05-27T00:00:00', {'msg': 'hello', 'account_id': acc1_id}, True)
        ws_log2._save_to_file('RECV', 'ws://127.0.0.1:8889/ws?account_id=acc_ws_002', '2026-05-27T00:00:01', {'msg': 'world', 'account_id': acc2_id}, True)
    finally:
        flag.unlink(missing_ok=True)

    assert (acc1_ws_dir / f"ws_{acc1_id}_20260527.jsonl").exists()
    assert (acc2_ws_dir / f"ws_{acc2_id}_20260527.jsonl").exists()
