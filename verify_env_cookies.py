import asyncio
import os
from dotenv import load_dotenv
from camoufox.async_api import AsyncCamoufox
from utils.cookie_handler import auto_convert_to_playwright

async def check_cookie(name, cookie_str):
    print(f"\n[终极验证 V2] {name}...")
    try:
        cookies = auto_convert_to_playwright(cookie_str)
        if not cookies:
            print(f"❌ {name}: 无效的 Cookie 格式")
            return False

        async with AsyncCamoufox(headless=True) as browser:
            context = await browser.new_context()
            await context.add_cookies(cookies)
            page = await context.new_page()
            
            # 访问 AI Studio 主页
            url = "https://aistudio.google.com/"
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # 检查重定向
            current_url = page.url
            if "signin" in current_url or "login" in current_url:
                print(f"❌ {name}: Cookie 已完全失效 (重定向到登录页)")
                return False
            
            # 等待页面加载
            await asyncio.sleep(5)
            
            # 获取页面文本内容用于辅助判断
            content_text = await page.evaluate("() => document.body.innerText")
            lower_content = content_text.lower()
            
            # 1. 检查明显的账号封禁/受限提示
            restrict_keywords = [
                "not authorized", 
                "not have access", 
                "account is disabled", 
                "verify your identity",
                "something went wrong"
            ]
            for kw in restrict_keywords:
                if kw in lower_content:
                    print(f"❌ {name}: 账号受限/异常 (检测到关键词: '{kw}')")
                    os.makedirs("logs", exist_ok=True)
                    await page.screenshot(path=f"logs/restrict_{name}.png")
                    return False

            # 2. 检查核心 UI 元素 (使用更通用的 selector)
            # Google AI Studio 的 UI 可能包含 mat-button, mat-icon 等
            selectors = [
                'button:has-text("Create new")',
                'button:has-text("Chat")',
                'button:has-text("Prompt")',
                '.model-selector',
                'header',
                'mat-drawer-container'
            ]
            
            # 尝试获取账户名 (通常在头像或下拉菜单中)
            account_name = "Unknown"
            try:
                # 注入脚本查找包含邮箱的文本
                account_name = await page.evaluate("""() => {
                    const treeWalker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    let node;
                    while (node = treeWalker.nextNode()) {
                        const text = node.textContent.trim();
                        // 包含邮箱正则匹配
                        const match = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                        if (match) return match[0];
                    }
                    // 尝试从 aria-label 中提取
                    const googleAccountBtn = document.querySelector('button[aria-label*="Google Account"]');
                    if (googleAccountBtn) {
                        const label = googleAccountBtn.getAttribute('aria-label');
                        const match = label.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                        if (match) return match[0];
                        return label;
                    }
                    // 检查页面上是否有任何文本包含 @gmail.com
                    const bodyText = document.body.innerText;
                    const match = bodyText.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}/);
                    if (match) return match[0];
                    
                    return "Unknown";
                }""")
            except Exception as e:
                # print(f"提取账户名出错: {str(e)}")
                pass

            found = False
            for s in selectors:
                try:
                    el = page.locator(s).first
                    if await el.is_visible():
                        found = True
                        break
                except:
                    continue
            
            if found:
                # 进一步验证：检查是否能加载出特定的 API Key 或 Project 信息 (可选)
                print(f"✅ {name}: 有效 (识别到 UI 组件) | 账户: {account_name}")
                return True
            else:
                print(f"❌ {name}: 界面加载异常 (可能账号已失效或网络问题)")
                os.makedirs("logs", exist_ok=True)
                await page.screenshot(path=f"logs/error_{name}.png")
                return False

    except Exception as e:
        print(f"❌ {name}: 验证过程出错: {str(e)}")
        return False

async def main():
    load_dotenv()
    
    cookie_vars = [k for k in os.environ.keys() if k.startswith("USER_COOKIE_")]
    cookie_vars.sort(key=lambda x: int(x.split("_")[-1]) if x.split("_")[-1].isdigit() else 0)
    
    cookie_vars = [k for k in os.environ.keys() if k.startswith("USER_COOKIE_")]
    cookie_vars.sort(key=lambda x: int(x.split("_")[-1]) if x.split("_")[-1].isdigit() else 0)
    
    if not cookie_vars:
        print("未在 .env 中找到任何 USER_COOKIE_* 变量")
        return

    for var_name in cookie_vars:
        cookie_val = os.environ.get(var_name)
        if cookie_val:
            await check_cookie(var_name, cookie_val)

if __name__ == "__main__":
    asyncio.run(main())
