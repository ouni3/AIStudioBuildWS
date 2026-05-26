import asyncio
import os
import random
from playwright.async_api import Page, expect, TimeoutError
from utils.paths import logs_dir
from utils.common import ensure_dir

async def handle_untrusted_dialog(page: Page, logger=None):
    """
    检查并处理 "Last modified by..." 的弹窗。
    如果弹窗出现，则点击 "OK" 按钮。
    """
    ok_button_locator = page.get_by_role("button", name="OK")

    try:
        # is_visible 是同步的还是异步的？在 async_api 中通常是 awaitable
        # 但 is_visible 在 async api 中也是 awaitable
        if await ok_button_locator.is_visible(timeout=10000): # 等待最多10秒
            logger.info(f"检测到弹窗，正在点击 'OK' 按钮...")
            
            await ok_button_locator.click(force=True)
            logger.info(f"'OK' 按钮已点击")
            await expect(ok_button_locator).to_be_hidden(timeout=1000)
            logger.info(f"弹窗已确认关闭")
        else:
            logger.info(f"在10秒内未检测到弹窗，继续执行...")
    except Exception as e:
        logger.info(f"检查弹窗时发生意外：{e}，将继续执行...")

async def handle_successful_navigation(page: Page, logger, cookie_file_config, shutdown_event=None):
    """
    在成功导航到目标页面后，执行后续操作（处理弹窗、保持运行）。
    """
    logger.info("已成功到达目标页面")
    
    # 给予页面焦点 (轻量级)
    await page.evaluate("() => { window.focus(); document.body.focus(); }")

    # 检查并处理 "Last modified by..." 的弹窗
    await handle_untrusted_dialog(page, logger=logger)

    # 随机抖动启动保活，避免所有实例同时触发
    jitter = random.uniform(0, 15)
    logger.info(f"实例进入保活阶段。随机抖动 {jitter:.2f}s 后开始循环...")
    await asyncio.sleep(jitter)

    logger.info("保活循环已启动。每 30 秒执行一次轻量级 JS 活动模拟")

    consecutive_errors = 0  # 连续错误计数器

    while True:
        # 检查是否收到关闭信号
        if shutdown_event and shutdown_event.is_set():
            logger.info("收到关闭信号，正在优雅退出保持活动循环...")
            break

        try:
            # 放弃昂贵的 page.click，改用轻量级 JS 事件触发
            # 模拟鼠标移动和按键按下以维持 WebSocket 和 session 活跃
            await page.evaluate("""() => {
                document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true }));
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Shift' }));
            }""")
            consecutive_errors = 0  # 重置连续错误计数

            # 使用可中断的睡眠，每秒检查一次关闭信号
            # 增加保活间隔到 30 秒以显著降低 CPU 负载
            for _ in range(30):
                if shutdown_event and shutdown_event.is_set():
                    logger.info("收到关闭信号，正在优雅退出保持活动循环...")
                    return
                await asyncio.sleep(1)

        except TimeoutError:
            consecutive_errors += 1
            logger.warning(f"保活点击超时 (连续次数: {consecutive_errors})，忽略此错误继续运行...")
            if consecutive_errors >= 20:
                logger.error("连续超时次数过多(>=20)，判定为实例异常，退出循环")
                break

        except Exception as e:
            consecutive_errors += 1
            logger.error(f"在保持活动循环中出错: {e} (连续错误: {consecutive_errors})")

            # 检查是否是致命错误（页面关闭）
            error_str = str(e)
            if "Target closed" in error_str or "Session closed" in error_str:
                logger.error("检测到页面或会话已关闭，退出循环")
                break

            # 在保持活动循环中出错时截屏
            try:
                screenshot_dir = logs_dir()
                ensure_dir(screenshot_dir)
                screenshot_filename = os.path.join(screenshot_dir, f"FAIL_keep_alive_error_{cookie_file_config}.png")
                await page.screenshot(path=screenshot_filename, full_page=True)
                logger.info(f"已在保持活动循环出错时截屏: {screenshot_filename}")
            except Exception as screenshot_e:
                logger.error(f"在保持活动循环出错时截屏失败: {screenshot_e}")
            
            if consecutive_errors >= 5:
                logger.error("连续非超时错误次数过多(>=5)，退出循环")
                break
            
            logger.info("尝试从错误中恢复，继续运行...")
            await asyncio.sleep(5)  # 出错后等待一小段时间
