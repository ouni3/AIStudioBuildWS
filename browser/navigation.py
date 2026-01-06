import time
import os
from playwright.sync_api import Page, expect, TimeoutError
from utils.paths import logs_dir
from utils.common import ensure_dir

def handle_untrusted_dialog(page: Page, logger=None):
    """
    检查并处理 "Last modified by..." 的弹窗。
    如果弹窗出现，则点击 "OK" 按钮。
    """
    ok_button_locator = page.get_by_role("button", name="OK")

    try:
        if ok_button_locator.is_visible(timeout=10000): # 等待最多10秒
            logger.info(f"检测到弹窗，正在点击 'OK' 按钮...")
            
            ok_button_locator.click(force=True)
            logger.info(f"'OK' 按钮已点击")
            expect(ok_button_locator).to_be_hidden(timeout=1000)
            logger.info(f"弹窗已确认关闭")
        else:
            logger.info(f"在10秒内未检测到弹窗，继续执行...")
    except Exception as e:
        logger.info(f"检查弹窗时发生意外：{e}，将继续执行...")

def handle_successful_navigation(page: Page, logger, cookie_file_config, shutdown_event=None, cookie_validator=None):
    """
    在成功导航到目标页面后，执行后续操作（处理弹窗、保持运行）。
    """
    logger.info("已成功到达目标页面")
    page.click('body') # 给予页面焦点

    # 检查并处理 "Last modified by..." 的弹窗
    handle_untrusted_dialog(page, logger=logger)

    # if cookie_validator:
    #     logger.info("Cookie验证器已创建，将定期验证Cookie有效性")

    logger.info("实例将保持运行状态。每10秒点击一次页面以保持活动 (已禁用自动Cookie验证)")

    # 等待页面加载和渲染
    time.sleep(15)

    # 添加Cookie验证计数器
    click_counter = 0
    consecutive_errors = 0  # 连续错误计数器

    while True:
        # 检查是否收到关闭信号
        if shutdown_event and shutdown_event.is_set():
            logger.info("收到关闭信号，正在优雅退出保持活动循环...")
            break

        try:
            # 使用较短的超时时间进行保活点击，避免长时间阻塞
            page.click('body', timeout=10000)
            click_counter += 1
            consecutive_errors = 0  # 重置连续错误计数

            # 每360次点击（1小时）执行一次完整的Cookie验证 - 用户要求禁用
            # if cookie_validator and click_counter >= 360:  # 360 * 10秒 = 3600秒 = 1小时
            #     is_valid = cookie_validator.validate_cookies_in_main_thread()
            #
            #     if not is_valid:
            #         cookie_validator.shutdown_instance_on_cookie_failure()
            #         return
            #
            #     click_counter = 0  # 重置计数器

            # 使用可中断的睡眠，每秒检查一次关闭信号
            for _ in range(10):  # 10秒 = 10次1秒检查
                if shutdown_event and shutdown_event.is_set():
                    logger.info("收到关闭信号，正在优雅退出保持活动循环...")
                    return
                time.sleep(1)

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
                page.screenshot(path=screenshot_filename, full_page=True)
                logger.info(f"已在保持活动循环出错时截屏: {screenshot_filename}")
            except Exception as screenshot_e:
                logger.error(f"在保持活动循环出错时截屏失败: {screenshot_e}")
            
            if consecutive_errors >= 5:
                logger.error("连续非超时错误次数过多(>=5)，退出循环")
                break
            
            logger.info("尝试从错误中恢复，继续运行...")
            time.sleep(5)  # 出错后等待一小段时间
