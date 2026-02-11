import os
import threading
import signal
import sys
import time
import asyncio

from browser.manager import BrowserManager
from utils.logger import setup_logging
from utils.paths import logs_dir, ws_log_flag_path, cookies_dir
from utils.cookie_manager import CookieManager
from utils.common import clean_env_value, ensure_dir

# 全局变量
app_running = False
flask_app = None
# 使用 threading.Event 实现线程间通信 (因改为单进程多协程架构)
shutdown_event = threading.Event()
browser_manager = None

def load_instance_configurations(logger):
    """
    使用CookieManager解析环境变量和Cookies目录，为每个Cookie来源创建独立的浏览器实例配置。
    """
    # 1. 读取所有实例共享的URL
    shared_url = clean_env_value(os.getenv("CAMOUFOX_INSTANCE_URL"))
    if not shared_url:
        logger.error("错误: 缺少环境变量 CAMOUFOX_INSTANCE_URL。所有实例需要一个共享的目标URL")
        return None, None

    # 2. 读取全局设置
    global_settings = {
        "headless": clean_env_value(os.getenv("CAMOUFOX_HEADLESS")) or "virtual",
        "url": shared_url  # 所有实例都使用这个URL
    }

    proxy_value = clean_env_value(os.getenv("CAMOUFOX_PROXY"))
    if proxy_value:
        global_settings["proxy"] = proxy_value

    # 3. 使用CookieManager检测所有Cookie来源
    cookie_manager = CookieManager(logger)
    sources = cookie_manager.detect_all_sources()

    # 检查是否有任何Cookie来源
    if not sources:
        logger.error("错误: 未找到任何Cookie来源（既没有JSON文件，也没有环境变量Cookie）")
        return None, None

    # 4. 为每个Cookie来源创建实例配置
    instances = []
    for source in sources:
        if source.type == "file":
            instances.append({
                "cookie_file": source.identifier,
                "cookie_source": source
            })
        elif source.type == "env_var":
            # 从环境变量名中提取索引，如 "USER_COOKIE_1" -> 1
            env_index = source.identifier.split("_")[-1]
            instances.append({
                "cookie_file": None,
                "env_cookie_index": int(env_index),
                "cookie_source": source
            })

    logger.info(f"将启动 {len(instances)} 个浏览器上下文")

    return global_settings, instances

async def monitor_auto_restart(logger, shutdown_event):
    """监控自动重启计时器"""
    auto_restart_hours = os.getenv("AUTO_RESTART_HOURS")
    if not auto_restart_hours:
        return

    try:
        hours = float(auto_restart_hours)
        if hours <= 0:
            return
        
        seconds = hours * 3600
        logger.info(f"自动重启已开启: 将在 {hours} 小时后 ({int(seconds)} 秒) 自动退出进程以触发重启")
        
        # 使用 wait_for 或循环检查 shutdown_event
        # 考虑到 asyncio.sleep 是可取消的，我们在这里等待
        start_time = time.time()
        while not shutdown_event.is_set():
            elapsed = time.time() - start_time
            if elapsed >= seconds:
                logger.info(f"已达到自动重启时间 ({hours} 小时)，正在触发关闭...")
                shutdown_event.set()
                break
            await asyncio.sleep(60) # 每分钟检查一次
    except ValueError:
        logger.error(f"无效的 AUTO_RESTART_HOURS 值: {auto_restart_hours}")

async def start_app_async(logger, global_settings, instance_profiles, shutdown_event):
    """异步启动应用及其监控协程"""
    global browser_manager
    browser_manager = BrowserManager(global_settings, instance_profiles, shutdown_event)
    
    # 同时运行浏览器管理器和重启监控
    await asyncio.gather(
        browser_manager.run(),
        monitor_auto_restart(logger, shutdown_event)
    )

def run_async_manager():
    """在 asyncio 事件循环中运行 BrowserManager"""
    global shutdown_event
    
    logger = setup_logging(str(logs_dir() / 'app.log'))
    
    # 延迟启动以等待系统稳定 (如果需要)
    start_delay = int(os.getenv("INSTANCE_START_DELAY", "30"))
    if start_delay > 0:
        logger.info(f"等待 {start_delay} 秒后启动...")
        time.sleep(start_delay)

    global_settings, instance_profiles = load_instance_configurations(logger)
    
    if not instance_profiles:
        logger.error("无有效配置，退出")
        return

    # 运行异步主循环
    try:
        asyncio.run(start_app_async(logger, global_settings, instance_profiles, shutdown_event))
    except KeyboardInterrupt:
        # 通常由 signal_handler 处理，这里只是为了防止 Traceback
        pass
    except Exception as e:
        logger.error(f"Async loop error: {e}")

def run_standalone_mode():
    """独立模式"""
    global app_running
    app_running = True
    run_async_manager()

def run_server_mode():
    """服务器模式 (Flask + Async Browser)"""
    global app_running, flask_app, browser_manager
    
    log_dir = logs_dir()
    server_logger = setup_logging(str(log_dir / 'app.log'), prefix="server")
    
    try:
        from flask import Flask, jsonify
        flask_app = Flask(__name__)
    except ImportError:
        server_logger.error("错误: 服务器模式需要 Flask，请安装: pip install flask")
        return
        
    app_running = True
    
    # 在后台线程中启动异步浏览器管理器
    browser_thread = threading.Thread(target=run_async_manager, daemon=True)
    browser_thread.start()
    
    @flask_app.route('/health')
    def health_check():
        """健康检查端点"""
        global browser_manager
        
        status = 'initializing'
        running_count = 0
        total_count = 0
        msg = 'Browser manager starting...'
        
        if browser_manager:
            status = 'healthy'
            running_count = browser_manager.get_active_count()
            total_count = browser_manager.get_total_count()
            msg = f'Application is running with {running_count} active browser contexts'
            
        return jsonify({
            'status': status,
            'browser_instances': total_count,
            'running_instances': running_count,
            'message': msg
        })

    @flask_app.route('/api/logs/ws/status')
    def get_ws_log_status():
        enabled = ws_log_flag_path().exists()
        return jsonify({'enabled': enabled})

    @flask_app.route('/api/logs/ws/enable', methods=['POST'])
    def enable_ws_logs():
        try:
            flag_path = ws_log_flag_path()
            ensure_dir(flag_path.parent)
            flag_path.touch()
            return jsonify({'status': 'success', 'enabled': True})
        except Exception as e:
            server_logger.error(f"无法创建标志文件: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @flask_app.route('/api/logs/ws/disable', methods=['POST'])
    def disable_ws_logs():
        try:
            flag_path = ws_log_flag_path()
            if flag_path.exists():
                flag_path.unlink()
            return jsonify({'status': 'success', 'enabled': False})
        except Exception as e:
            server_logger.error(f"无法删除标志文件: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @flask_app.route('/')
    def index():
        global browser_manager
        
        running_count = 0
        total_count = 0
        if browser_manager:
            running_count = browser_manager.get_active_count()
            total_count = browser_manager.get_total_count()
            
        ws_log_enabled = ws_log_flag_path().exists()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>AIStudioBuildWS 控制台</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f5f5f7; }}
                .card {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); margin-bottom: 20px; }}
                h1 {{ margin-top: 0; color: #1d1d1f; }}
                .status-item {{ display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #eee; }}
                .status-item:last-child {{ border-bottom: none; }}
                .label {{ color: #86868b; }}
                .value {{ font-weight: 600; color: #1d1d1f; }}
                .switch-container {{ display: flex; align-items: center; justify-content: space-between; margin-top: 20px; }}
                .switch {{ position: relative; display: inline-block; width: 60px; height: 34px; }}
                .switch input {{ opacity: 0; width: 0; height: 0; }}
                .slider {{ position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: .4s; border-radius: 34px; }}
                .slider:before {{ position: absolute; content: ""; height: 26px; width: 26px; left: 4px; bottom: 4px; background-color: white; transition: .4s; border-radius: 50%; }}
                input:checked + .slider {{ background-color: #0071e3; }}
                input:checked + .slider:before {{ transform: translateX(26px); }}
                button {{ background-color: #0071e3; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; margin-top: 10px; }}
                button:hover {{ background-color: #0077ed; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>系统状态</h1>
                <div class="status-item">
                    <span class="label">运行模式</span>
                    <span class="value">Server (Async/Single-Process)</span>
                </div>
                <div class="status-item">
                    <span class="label">总配置数</span>
                    <span class="value">{total_count}</span>
                </div>
                <div class="status-item">
                    <span class="label">活跃会话数</span>
                    <span class="value">{running_count}</span>
                </div>
                <div class="status-item">
                    <span class="label">健康状态</span>
                    <span class="value" style="color: green">Healthy</span>
                </div>
            </div>

            <div class="card">
                <h1>调试控制</h1>
                <div class="switch-container">
                    <span>WebSocket 日志记录 (详细)</span>
                    <label class="switch">
                        <input type="checkbox" id="wsLogToggle" {'checked' if ws_log_enabled else ''} onchange="toggleWsLogs(this)">
                        <span class="slider"></span>
                    </label>
                </div>
                <p style="color: #86868b; font-size: 14px;">开启后，所有 WebSocket 通信的详细内容将被记录到 <code>logs/ws_messages/</code> 目录。</p>
            </div>

            <script>
                function toggleWsLogs(checkbox) {{
                    const action = checkbox.checked ? 'enable' : 'disable';
                    fetch(`/api/logs/ws/${{action}}`, {{ method: 'POST' }})
                        .then(response => response.json())
                        .then(data => {{
                            if (data.status !== 'success') {{
                                alert('操作失败: ' + data.message);
                                checkbox.checked = !checkbox.checked; // Revert
                            }}
                        }})
                        .catch(err => {{
                            alert('网络错误');
                            checkbox.checked = !checkbox.checked;
                        }});
                }}
            </script>
        </body>
        </html>
        """
        return html

    # 禁用 Flask 的默认日志
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    # 启动 Flask 服务器
    try:
        flask_app.run(host='0.0.0.0', port=7860, debug=False)
    except KeyboardInterrupt:
        server_logger.info("服务器正在关闭...")

def signal_handler(signum, frame):
    """信号处理器"""
    global shutdown_event
    
    logger = setup_logging(str(logs_dir() / 'app.log'), prefix="signal")
    logger.info(f"接收到信号 {signum}，正在通知 Async Manager 关闭...")
    
    shutdown_event.set()
    
    # 给一点时间让 async loop 反应
    # 注意：这里不能等待太久，否则系统会强杀
    # 但由于我们在主线程，如果不退出，可能导致程序 hang 住
    # 实际上，在 standalone 模式下，signal_handler 返回后，asyncio.run() 可能会继续运行直到 loop 退出
    # 只要 loop 中的 task 检测到了 shutdown_event 并退出
    
def main():
    """主入口函数"""
    ensure_dir(logs_dir())
    ensure_dir(cookies_dir())

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    try:
        signal.signal(signal.SIGQUIT, signal_handler)
    except (ValueError, AttributeError):
        pass

    hg_mode = os.getenv('HG', '').lower()

    if hg_mode == 'true':
        run_server_mode()
    else:
        run_standalone_mode()

if __name__ == "__main__":
    main()
