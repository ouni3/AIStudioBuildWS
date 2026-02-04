import os
import json
import asyncio
from playwright.async_api import async_playwright
from utils.cookie_manager import CookieManager
from utils.logger import setup_logging

async def verify_cookies():
    logger = setup_logging("CookieVerifier")
    manager = CookieManager(logger=logger)
    sources = manager.detect_all_sources()
    
    if not sources:
        logger.error("未找到任何 Cookie 来源")
        return

    async with async_playwright() as p:
        # 使用 firefox 因为项目使用的是 Camoufox (基于 Firefox)
        browser = await p.firefox.launch(headless=True)
        
        for source in sources:
            logger.info(f"正在验证 {source.display_name}...")
            
            # 加载并转换 Cookie
            raw_data = None
            if source.type == "env_var":
                raw_data = os.getenv(source.identifier)
            elif source.type == "file":
                from utils.paths import cookies_dir
                file_path = os.path.join(cookies_dir(), source.identifier)
                with open(file_path, 'r', encoding='utf-8') as f:
                    raw_data = f.read()
            
            if not raw_data:
                logger.warning(f"无法读取 {source.display_name} 的内容")
                continue

            from utils.cookie_handler import auto_convert_to_playwright
            playwright_cookies = auto_convert_to_playwright(raw_data, logger=logger)
            
            if not playwright_cookies:
                logger.error(f"{source.display_name} 转换后为空")
                continue

            # 创建上下文并设置 Cookie
            context = await browser.new_context()
            await context.add_cookies(playwright_cookies)
            
            page = await context.new_page()
            
            try:
                # 访问 AI Studio
                url = os.getenv("CAMOUFOX_INSTANCE_URL", "https://aistudio.google.com/")
                logger.info(f"正在导航到 {url}...")
                
                # 设置超时
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # 检查是否包含特定的登录后元素或 URL
                # AI Studio 登录后通常会有 'apps/drive' 或类似路径
                current_url = page.url
                logger.info(f"当前 URL: {current_url}")
                
                # 检查页面标题或内容
                content = await page.content()
                
                # 简单的逻辑：如果 URL 包含 google.com 且页面没有明显的登录按钮/提示，
                # 或者包含 specific app 路径，则认为有效。
                # 也可以检查是否重定向到了登录页 accounts.google.com
                if "accounts.google.com" in current_url:
                    logger.error(f"❌ {source.display_name} 无效：重定向到了登录页面")
                elif "aistudio.google.com" in current_url:
                    # 检查页面是否加载成功（非 403 或登录提示）
                    if "Sign in" in await page.title() or "登录" in await page.title():
                         logger.error(f"❌ {source.display_name} 无效：页面标题显示需要登录")
                    else:
                        logger.info(f"✅ {source.display_name} 看起来是有效的")
                        # 截图保存以供参考
                        from utils.paths import logs_dir
                        os.makedirs(logs_dir(), exist_ok=True)
                        screenshot_path = os.path.join(logs_dir(), f"verify_{source.identifier}.png")
                        await page.screenshot(path=screenshot_path)
                        logger.info(f"已保存截图: {screenshot_path}")
                else:
                    logger.warning(f"⚠️ {source.display_name} 状态不明 (URL: {current_url})")

            except Exception as e:
                logger.error(f"验证 {source.display_name} 时出错: {e}")
            finally:
                await context.close()

        await browser.close()

if __name__ == "__main__":
    # 加载 .env
    from dotenv import load_dotenv
    load_dotenv()
    
    asyncio.run(verify_cookies())
