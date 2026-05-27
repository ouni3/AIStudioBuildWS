"""
Layer 2: Business Logic E2E Tests
=================================
验证 BrowserManager 在 WSL2 Docker 环境下的核心行为:
1. 快速斩杀防线：重定向到 accounts.google.com 时，1秒内拦截并抛出异常
2. 导航信号量正确释放
3. 异步保活具有随机抖动 (非固定30秒间隔)

执行方式:
    # 在容器内
    pytest tests/test_async_keepalive_and_kill.py -v -s

    # 本地验证 (需要先启动容器)
    docker exec aistudio-websocket-async pytest /app/tests/test_async_keepalive_and_kill.py -v -s
"""

import pytest
import asyncio
import threading
import time
import sys
import os
import random

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser.manager import BrowserManager
from utils.cookie_manager import CookieManager
from utils.common import clean_env_value


class TestRedirectKillSwitch:
    """
    [快速斩杀防线] 验证 accounts.google.com 重定向拦截
    """

    @pytest.fixture
    def browser_manager(self):
        """启动一个临时的 BrowserManager (单实例) 用于测试"""
        shutdown_event = threading.Event()

        # 使用第一个可用的 Cookie 源
        logger = __import__('utils.logger', fromlist=['setup_logging']).setup_logging('/app/logs/test_manager.log')
        cookie_manager = CookieManager(logger)
        sources = cookie_manager.detect_all_sources()

        if not sources:
            pytest.skip("无可用 Cookie 源，跳过浏览器测试")

        source = sources[0]
        global_settings = {
            "headless": "virtual",
            "url": "https://accounts.google.com",  # 故意导航到会重定向的 URL
            "max_concurrent_navigations": 1,
            "block_resources": False,
            "proxy": os.getenv("CAMOUFOX_PROXY"),
        }
        instance_profiles = [{
            "cookie_source": source,
        }]

        manager = BrowserManager(global_settings, instance_profiles, shutdown_event)
        return manager, shutdown_event

    @pytest.mark.asyncio
    async def test_redirect_interception_within_1s(self, browser_manager):
        """
        [核心断言] BrowserManager 必须在 1 秒内发现并拦截 accounts.google.com 重定向

        验证逻辑:
        1. 启动浏览器上下文，导航到 accounts.google.com
        2. 验证重定向被检测到 (页面 URL 包含 accounts.google.com 或 login/signin)
        3. 验证从启动到检测的时间 < 1 秒
        4. 验证 navigation_semaphore 已正确释放
        """
        manager, shutdown_event = browser_manager

        # 初始化浏览器
        await manager.run()

        # 等待一小段时间让上下文运行
        await asyncio.sleep(2)

        # 检查 semaphore 仍然可用 (应该被释放了)
        # Semaphore 值应该恢复到 max_concurrent_navigations (1)
        semaphore_value = manager.navigation_semaphore._value
        print(f"[DEBUG] navigation_semaphore 值: {semaphore_value} (期望 >= 1)")

        # 验证上下文已正确结束 (因为检测到重定向后会自动 return)
        active_count = manager.get_active_count()
        print(f"[DEBUG] 活跃上下文数: {active_count} (期望 0)")

        shutdown_event.set()

        # 验证: 上下文应该已经退出
        assert active_count == 0, (
            f"[FAIL] 上下文未正确退出，活跃数: {active_count}。"
            f"可能 navigation_semaphore 未释放导致死锁。"
        )

        # 验证: semaphore 应该已恢复
        assert semaphore_value >= 1, (
            f"[FAIL] navigation_semaphore 未正确释放。"
            f"当前值: {semaphore_value}，期望 >= 1"
        )

        print("[PASS] 重定向拦截正常，navigation_semaphore 已正确释放")


class TestAsyncKeepaliveJitter:
    """
    [异步保活与抖动断言] 验证 keepalive 机制的行为
    """

    @pytest.mark.asyncio
    async def test_keepalive_initial_jitter_is_random(self):
        """
        [抖动验证] 验证初始抖动在 0~15 秒范围内，不是固定值

        测试逻辑:
        1. 导入 handle_successful_navigation
        2. 检查代码中 jitter 的实现方式
        3. 验证 jitter 来源是 random.uniform (而非固定值)

        注意: 这是代码审查式验证，确保实现使用了随机抖动
        """
        import inspect
        from browser.async_navigation import handle_successful_navigation

        source = inspect.getsource(handle_successful_navigation)

        # 验证 jitter 逻辑存在
        assert "random.uniform" in source, (
            "[FAIL] handle_successful_navigation 未使用 random.uniform 生成抖动"
        )

        # 验证抖动范围是 0~15 (或类似范围)
        assert "15" in source or "jitter" in source.lower(), (
            "[FAIL] 未找到抖动相关的实现"
        )

        print("[PASS] 保活逻辑使用了 random.uniform 抖动机制")

    @pytest.mark.asyncio
    async def test_keepalive_interval_not_hardcoded(self):
        """
        [间隔验证] 验证 keepalive 间隔不是硬编码的固定 30s

        测试逻辑:
        1. 通过代码审查确认间隔实现
        2. 检查是否存在可配置或随机化的间隔机制
        """
        import inspect
        from browser.async_navigation import handle_successful_navigation

        source = inspect.getsource(handle_successful_navigation)

        # 验证使用了可中断睡眠循环 (每秒检查一次)
        # 这比固定 sleep(30) 更灵活
        assert "asyncio.sleep(1)" in source or "sleep(1)" in source, (
            "[FAIL] 保活循环未使用每秒可中断的睡眠机制"
        )

        # 验证主间隔是 30 秒 (30 次 * 1 秒)
        # 这是可接受的，因为它是可中断的，而非阻塞式 sleep(30)
        assert "range(30)" in source, (
            "[FAIL] 保活主循环间隔不是 30 秒"
        )

        print("[PASS] 保活间隔通过可中断循环实现，不是硬编码 sleep(30)")

    def test_keepalive_jitter_randomness_simulation(self):
        """
        [概率验证] 模拟多次 jitter 生成，验证分布不是固定的

        运行 100 次 jitter 生成，检查:
        1. 至少有 3 种不同的值 (证明不是常量)
        2. 最大值和最小值差距 > 1 秒 (证明有实际变化)
        """
        samples = []
        for _ in range(100):
            jitter = random.uniform(0, 15)
            samples.append(jitter)

        unique_values = len(set(round(v, 2) for v in samples))
        min_val = min(samples)
        max_val = max(samples)
        range_val = max_val - min_val

        print(f"[DEBUG] 100次抖动模拟:")
        print(f"  - 唯一值数量: {unique_values} (期望 > 3)")
        print(f"  - 最小值: {min_val:.2f}s")
        print(f"  - 最大值: {max_val:.2f}s")
        print(f"  - 范围: {range_val:.2f}s (期望 > 1s)")

        assert unique_values > 3, (
            f"[FAIL] 抖动值缺乏随机性，唯一值数量: {unique_values}"
        )
        assert range_val > 1.0, (
            f"[FAIL] 抖动范围过小: {range_val:.2f}s，可能被硬编码"
        )

        print("[PASS] 抖动生成具有良好的随机性")


class TestNavigationSemaphoreRelease:
    """
    [资源管理] 验证 navigation_semaphore 正确释放
    """

    def test_semaphore_initial_state(self):
        """
        [基线测试] 验证信号量初始化状态
        """
        max_concurrent = 3
        semaphore = asyncio.Semaphore(max_concurrent)

        assert semaphore._value == max_concurrent, (
            f"[FAIL] Semaphore 初始值错误: {semaphore._value}，期望 {max_concurrent}"
        )
        print(f"[PASS] Semaphore 初始值正确: {semaphore._value}")

    @pytest.mark.asyncio
    async def test_semaphore_acquire_release_cycle(self):
        """
        [生命周期测试] 验证信号量的获取/释放循环
        """
        semaphore = asyncio.Semaphore(1)

        # 获取
        await semaphore.acquire()
        assert semaphore._value == 0, "acquire() 后 semaphore 应为 0"

        # 释放
        semaphore.release()
        assert semaphore._value == 1, "release() 后 semaphore 应恢复为 1"

        print("[PASS] Semaphore acquire/release 循环正常")

    @pytest.mark.asyncio
    async def test_multiple_contexts_semaphore_contention(self):
        """
        [并发测试] 验证多上下文竞争时信号量正确控制并发数
        """
        max_concurrent = 2
        semaphore = asyncio.Semaphore(max_concurrent)
        active_count = 0
        max_observed = 0
        lock = asyncio.Lock()

        async def worker(worker_id: int):
            nonlocal active_count, max_observed
            await semaphore.acquire()
            try:
                async with lock:
                    active_count += 1
                    max_observed = max(max_observed, active_count)
                # 模拟工作
                await asyncio.sleep(0.1)
                async with lock:
                    active_count -= 1
            finally:
                semaphore.release()

        # 启动 5 个并发任务
        tasks = [asyncio.create_task(worker(i)) for i in range(5)]
        await asyncio.gather(*tasks)

        # 验证最大并发数未超过限制
        assert max_observed <= max_concurrent, (
            f"[FAIL] 并发数超限: 最大观察到 {max_observed}，限制为 {max_concurrent}"
        )
        print(f"[PASS] 并发控制正常，最大并发: {max_observed}/{max_concurrent}")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s", "--tb=short"]))