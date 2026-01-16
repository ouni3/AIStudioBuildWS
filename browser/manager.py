import asyncio
import os
import logging
from playwright.async_api import TimeoutError
from camoufox.async_api import AsyncCamoufox
from browser.async_navigation import handle_successful_navigation
from browser.ws_logger import WebSocketLogger
from utils.logger import setup_logging
from utils.paths import logs_dir
from utils.common import parse_headless_mode, ensure_dir
from utils.url_helper import mask_url_for_logging, mask_path_for_logging, extract_url_path
from utils.cookie_manager import CookieManager

class BrowserManager:
    """
    统一的浏览器管理器 (异步版本)
    使用单个浏览器实例管理多个隔离的 BrowserContext，显著降低资源消耗。
    """

    def __init__(self, global_settings, instance_profiles, shutdown_event):
        self.global_settings = global_settings
        self.instance_profiles = instance_profiles
        self.shutdown_event = shutdown_event
        self.logger = setup_logging(str(logs_dir() / 'manager.log'), prefix="Manager")
        self.browser = None
        self.tasks = []

    def get_total_count(self):
        """获取配置的总实例数"""
        return len(self.instance_profiles)

    def get_active_count(self):
        """获取当前正在运行的任务数"""
        return len([t for t in self.tasks if not t.done()])

    async def run(self):
        """BrowserManager 主运行循环"""
        self.logger.info("正在启动 BrowserManager (异步模式)")
        
        headless_setting = self.global_settings.get('headless', 'virtual')
        headless_mode = parse_headless_mode(headless_setting)
        
        launch_options = {
            "headless": headless_mode,
            "args": ["--disable-gpu"] # 禁用 GPU 以节省资源
        }
        
        # 全局代理设置
        if self.global_settings.get('proxy'):
             launch_options["proxy"] = {"server": self.global_settings['proxy'], "bypass": "localhost, 127.0.0.1"}

        self.logger.info(f"正在启动 AsyncCamoufox, 配置: headless={headless_mode}, proxy={launch_options.get('proxy')}")

        try:
            # 启动浏览器实例
            async with AsyncCamoufox(**launch_options) as browser:
                self.browser = browser
                self.logger.info("浏览器实例启动成功。正在创建用户上下文...")

                self.tasks = []
                for i, profile in enumerate(self.instance_profiles, 1):
                    # 合并配置 (目前主要是 url 和 proxy，但 proxy 已在全局设置)
                    config = self.global_settings.copy()
                    config.update(profile)
                    
                    # 为每个配置文件创建一个异步任务
                    task = asyncio.create_task(self.run_context(config, i))
                    self.tasks.append(task)
                
                if not self.tasks:
                    self.logger.warning("没有需要运行的任务")
                    return

                self.logger.info(f"已启动 {len(self.tasks)} 个并发上下文任务")

                # 主循环：监控 shutdown_event
                while not self.shutdown_event.is_set():
                    # 检查是否所有任务都已结束（意外退出）
                    if all(t.done() for t in self.tasks):
                        self.logger.info("所有浏览器上下文任务已结束。")
                        break
                    await asyncio.sleep(1)
                
                if self.shutdown_event.is_set():
                    self.logger.info("收到 shutdown_event，正在关闭...")

                # 取消所有正在运行的任务
                for task in self.tasks:
                    if not task.done():
                        task.cancel()
                
                # 等待任务取消完成
                if self.tasks:
                    await asyncio.gather(*self.tasks, return_exceptions=True)
                
                self.logger.info("BrowserManager 关闭完成。")

        except Exception as e:
            self.logger.exception(f"BrowserManager 发生严重错误: {e}")
        finally:
            self.logger.info("BrowserManager 退出。")

    async def run_context(self, config, index):
        """运行单个浏览器上下文 (Tab/Session)"""
        cookie_source = config.get('cookie_source')
        instance_label = cookie_source.display_name
        
        # 为每个上下文设置独立的 logger
        logger = setup_logging(str(logs_dir() / 'app.log'), prefix=instance_label)
        
        diagnostic_tag = instance_label.replace(os.sep, "_")
        screenshot_dir = logs_dir()
        ensure_dir(screenshot_dir)

        logger.info(f"Context #{index} 初始化中...")
        
        # 加载 Cookie
        try:
             cookie_manager = CookieManager(logger)
             # load_cookies 是同步方法，但在初始化阶段调用一次影响不大
             cookies = cookie_manager.load_cookies(cookie_source)
             if not cookies:
                 logger.error("未找到 Cookie，Context 退出。")
                 return
        except Exception as e:
            logger.error(f"加载 Cookie 失败: {e}")
            return

        expected_url = config.get('url')

        try:
            # 创建新的 BrowserContext
            # 这实现了数据隔离（Cookie, Storage 等）
            context = await self.browser.new_context()
            
            try:
                await context.add_cookies(cookies)
                page = await context.new_page()
                
                # 挂载 WebSocket Logger
                ws_logger = WebSocketLogger(logger, instance_label)
                ws_logger.attach_to_page(page) # page.on 是同步注册，兼容

                # 导航逻辑
                logger.info(f"正在导航到: {mask_url_for_logging(expected_url)}")
                
                try:
                    response = await page.goto(expected_url, wait_until='domcontentloaded', timeout=90000)
                    
                    if response:
                         if not response.ok:
                             logger.warning(f"HTTP 状态码: {response.status}")
                             await page.screenshot(path=os.path.join(screenshot_dir, f"WARN_status_{response.status}_{diagnostic_tag}.png"))
                    
                    # 检查加载指示器
                    spinner_locator = page.locator('mat-spinner')
                    try:
                        # 等待 spinner 消失
                        await spinner_locator.wait_for(state='hidden', timeout=30000)
                        logger.info("加载指示器已消失")
                    except TimeoutError:
                        logger.error("页面加载卡在 Spinner。")
                        await page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_spinner_{diagnostic_tag}.png"))
                        return

                    # 检查认证错误
                    auth_error_locator = page.get_by_text("authentication error", exact=False)
                    if await auth_error_locator.is_visible(timeout=2000):
                        logger.error("检测到认证错误横幅。Cookie 可能已过期。")
                        await page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_auth_{diagnostic_tag}.png"))
                        return
                    
                    # 检查登录按钮 (Double check)
                    login_button_cn = page.get_by_role('button', name='登录')
                    login_button_en = page.get_by_role('button', name='Login')
                    
                    if await login_button_cn.is_visible(timeout=1000) or await login_button_en.is_visible(timeout=1000):
                         logger.error("页面显示登录按钮，Cookie 无效。")
                         await page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_login_btn_{diagnostic_tag}.png"))
                         return

                    # 成功，进入保活循环
                    await handle_successful_navigation(page, logger, instance_label, self.shutdown_event)

                except TimeoutError:
                    logger.error("导航超时。")
                    await page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_timeout_{diagnostic_tag}.png"))
                except Exception as e:
                    logger.error(f"导航过程中发生错误: {e}")
                    await page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_nav_error_{diagnostic_tag}.png"))

            finally:
                # 关闭上下文
                await context.close()
                logger.info("Context 已关闭")

        except asyncio.CancelledError:
            logger.info("Context 任务被取消")
        except Exception as e:
            logger.exception(f"Context 运行发生未知错误: {e}")
