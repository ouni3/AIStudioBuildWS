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
            "args": [
                "--disable-dev-shm-usage",
                "--no-sandbox"
            ],
            "firefox_user_prefs": {
                # 关键修复：禁用后台标签页的定时器节流，防止 WebSocket 心跳断开
                "dom.min_background_timeout_value": 4, 
                "dom.timeout.enable_budget_timer_throttling": False,
                # 增加 WebSocket 的超时容忍度
                "network.websocket.timeout.ping.request": 20,
                "network.websocket.timeout.ping.response": 20,
                # 确保 HTTP2 WebSocket 启用
                "network.http.http2.websockets": True,
                # 允许 HTTPS 页面连接不安全的 WS (ws://127.0.0.1)
                "security.mixed_content.block_active_content": False,
                "security.mixed_content.block_display_content": False
            }
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
                    # 合并配置
                    config = self.global_settings.copy()
                    config.update(profile)
                    
                    # 错峰启动：每个上下文之间间隔 15 秒，避免单实例浏览器瞬间压力过大
                    start_delay = (i - 1) * 15
                    task = asyncio.create_task(self.delayed_run_context(config, i, start_delay))
                    self.tasks.append(task)
                
                if not self.tasks:
                    self.logger.warning("没有需要运行的任务")
                    return

                self.logger.info(f"已提交 {len(self.tasks)} 个错峰并发上下文任务 (间隔 15s)")

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

    async def delayed_run_context(self, config, index, delay):
        """延迟运行上下文"""
        if delay > 0:
            cookie_source = config.get('cookie_source')
            instance_label = cookie_source.display_name
            logging.getLogger(instance_label).info(f"错峰启动：等待 {delay} 秒后开始初始化上下文...")
            await asyncio.sleep(delay)
        return await self.run_context(config, index)

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
                
                # 显式将页面带到前台，某些重负载应用在后台上下文可能会限流
                await page.bring_to_front()
                
                # 挂载 WebSocket Logger
                ws_logger = WebSocketLogger(logger, instance_label)
                ws_logger.attach_to_page(page) # page.on 是同步注册，兼容

                # 导航逻辑
                logger.info(f"正在导航到: {mask_url_for_logging(expected_url)}")
                
                try:
                    # 增加导航超时时间到 120s
                    response = await page.goto(expected_url, wait_until='domcontentloaded', timeout=120000)
                    
                    if response:
                         if not response.ok:
                             logger.warning(f"HTTP 状态码: {response.status}")
                             # 截图增加超时限制，防止截图本身也挂起
                             try:
                                 await page.screenshot(path=os.path.join(screenshot_dir, f"WARN_status_{response.status}_{diagnostic_tag}.png"), timeout=10000)
                             except: pass
                    
                    # [Iori's Redirection Audit] 鉴权前置防线：探测到非预期的域或路由重定向，直接斩杀
                    current_url = page.url
                    if "accounts.google.com" in current_url or "login" in current_url.lower() or "signin" in current_url.lower():
                        logger.error(f"严重越权: 检测到未预期的重定向页面 ({current_url})，判定 Cookie 失效，斩杀上下文。")
                        try:
                            await page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_redirect_{diagnostic_tag}.png"), timeout=10000)
                        except: pass
                        return

                    # 检查加载指示器
                    try:
                        # [Iori's Strict-Mode Bypass] 规避严格模式：获取所有现存的 spinner 并等待其全部隐藏
                        spinners = await page.locator('mat-spinner').all()
                        for spinner in spinners:
                            await spinner.wait_for(state='hidden', timeout=30000)
                        logger.info("所有加载指示器已消失")
                    except TimeoutError:
                        logger.error("页面加载卡在 Spinner。")
                        try:
                            await page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_spinner_{diagnostic_tag}.png"), timeout=10000)
                        except: pass
                        return

                    # 检查认证错误
                    auth_error_locator = page.get_by_text("authentication error", exact=False)
                    if await auth_error_locator.is_visible(timeout=2000):
                        logger.error("检测到认证错误横幅。Cookie 可能已过期。")
                        try:
                            await page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_auth_{diagnostic_tag}.png"), timeout=10000)
                        except: pass
                        return
                    
                    # 检查登录按钮 (Double check)
                    login_button_cn = page.get_by_role('button', name='登录')
                    login_button_en = page.get_by_role('button', name='Login')
                    
                    if await login_button_cn.is_visible(timeout=1000) or await login_button_en.is_visible(timeout=1000):
                         logger.error("页面显示登录按钮，Cookie 无效。")
                         try:
                             await page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_login_btn_{diagnostic_tag}.png"), timeout=10000)
                         except: pass
                         return

                    # 成功，进入保活循环
                    await handle_successful_navigation(page, logger, instance_label, self.shutdown_event)

                except TimeoutError:
                    logger.error("导航超时。")
                    try:
                        await page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_timeout_{diagnostic_tag}.png"), timeout=10000)
                    except: pass
                except Exception as e:
                    logger.error(f"导航过程中发生错误: {e}")
                    try:
                        await page.screenshot(path=os.path.join(screenshot_dir, f"FAIL_nav_error_{diagnostic_tag}.png"), timeout=10000)
                    except: pass

            finally:
                # 关闭上下文
                await context.close()
                logger.info("Context 已关闭")

        except asyncio.CancelledError:
            logger.info("Context 任务被取消")
        except Exception as e:
            logger.exception(f"Context 运行发生未知错误: {e}")
