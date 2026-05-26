"""
WebSocket 日志记录模块

用于捕获和记录浏览器与 Google AI Studio 之间的 WebSocket 通信。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from utils.paths import logs_dir, ws_log_flag_path
from utils.common import ensure_dir


class WebSocketLogger:
    """WebSocket 消息日志记录器"""

    def __init__(self, logger, instance_label):
        """
        初始化 WebSocket 日志记录器

        :param logger: 日志记录器实例
        :param instance_label: 实例标签，用于区分不同的浏览器实例
        """
        self.logger = logger
        self.instance_label = instance_label
        self.ws_log_dir = Path(logs_dir()) / 'ws_messages'
        ensure_dir(self.ws_log_dir)
        self.active_connections = {}

    def attach_to_page(self, page):
        """
        附加 WebSocket 监听器到页面

        :param page: Playwright Page 对象
        """
        page.on('websocket', self._handle_websocket)
        self.logger.info("WebSocket 监听器已附加到页面")

    def _handle_websocket(self, ws):
        """
        处理新的 WebSocket 连接

        :param ws: Playwright WebSocket 对象
        """
        # 仅在标志文件存在时才进行详细记录（可选：如果希望始终记录连接建立，可不加判断）
        # 这里我们选择始终记录连接建立/关闭，但只在开关开启时记录详细内容
        ws_url = ws.url
        self.logger.info(f"[WS] 新连接建立: {self._mask_url(ws_url)}")
        self.active_connections[ws_url] = datetime.now()

        # 注册帧事件监听器
        ws.on('framesent', lambda payload: self._log_frame('SENT', ws_url, payload))
        ws.on('framereceived', lambda payload: self._log_frame('RECV', ws_url, payload))
        ws.on('close', lambda: self._handle_close(ws_url))

    def _handle_close(self, ws_url):
        """处理 WebSocket 连接关闭"""
        duration = ""
        if ws_url in self.active_connections:
            start_time = self.active_connections.pop(ws_url)
            elapsed = datetime.now() - start_time
            duration = f" (持续时间: {elapsed.total_seconds():.1f}秒)"
        self.logger.info(f"[WS] 连接已关闭: {self._mask_url(ws_url)}{duration}")

    def _log_frame(self, direction, ws_url, payload):
        """
        记录 WebSocket 帧

        :param direction: 'SENT' 或 'RECV'
        :param ws_url: WebSocket URL
        :param payload: 帧数据
        """
        # 检查是否开启了日志记录
        if not ws_log_flag_path().exists():
            return

        timestamp = datetime.now().isoformat()
        arrow = "→" if direction == 'SENT' else "←"

        # 处理 payload
        try:
            if isinstance(payload, bytes):
                payload_str = payload.decode('utf-8')
            else:
                payload_str = payload

            # 尝试解析为 JSON
            try:
                data = json.loads(payload_str)
                is_json = True
            except json.JSONDecodeError:
                data = payload_str
                is_json = False

            # 输出到控制台（精简版）
            summary = self._extract_summary(data, is_json)
            self.logger.info(f"[WS {arrow}] {summary}")

            # 保存完整消息到文件
            self._save_to_file(direction, ws_url, timestamp, data, is_json)

        except UnicodeDecodeError:
            # 二进制数据
            self.logger.debug(f"[WS {arrow}] 二进制数据 ({len(payload)} bytes)")

    def _extract_summary(self, data, is_json):
        """
        提取消息摘要用于控制台显示

        :param data: 消息数据
        :param is_json: 是否为 JSON 格式
        :return: 摘要字符串
        """
        if not is_json:
            # 非 JSON 数据，截取前100字符
            text = str(data)
            if len(text) > 100:
                return f"文本: {text[:100]}..."
            return f"文本: {text}"

        if not isinstance(data, dict):
            return f"JSON数组: {len(data)} 项" if isinstance(data, list) else str(data)[:100]

        # 尝试提取关键字段
        summary_parts = []

        # 检查常见的消息类型字段
        for type_field in ['type', 'event', 'action', 'method', 'cmd']:
            if type_field in data:
                summary_parts.append(f"{type_field}={data[type_field]}")
                break

        # 检查是否包含 prompt/content
        for content_field in ['prompt', 'content', 'text', 'message', 'input']:
            if content_field in data:
                content = str(data[content_field])
                if len(content) > 50:
                    content = content[:50] + "..."
                summary_parts.append(f"{content_field}={content}")
                break

        # 检查响应相关字段
        for resp_field in ['response', 'result', 'output', 'answer']:
            if resp_field in data:
                resp = str(data[resp_field])
                if len(resp) > 50:
                    resp = resp[:50] + "..."
                summary_parts.append(f"{resp_field}={resp}")
                break

        # 如果没有找到关键字段，显示顶层键
        if not summary_parts:
            keys = list(data.keys())[:5]
            summary_parts.append(f"keys={keys}")

        return " | ".join(summary_parts)

    def _save_to_file(self, direction, ws_url, timestamp, data, is_json):
        """
        保存完整消息到 JSONL 文件

        :param direction: 'SENT' 或 'RECV'
        :param ws_url: WebSocket URL
        :param timestamp: 时间戳
        :param data: 消息数据
        :param is_json: 是否为 JSON 格式
        """
        # 使用日期和实例标签命名文件
        safe_label = self.instance_label.replace(os.sep, "_").replace(":", "_")
        filename = f"ws_{safe_label}_{datetime.now().strftime('%Y%m%d')}.jsonl"
        filepath = self.ws_log_dir / filename

        record = {
            'timestamp': timestamp,
            'direction': direction,
            'url': self._mask_url(ws_url),
            'is_json': is_json,
            'data': data
        }

        try:
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        except Exception as e:
            self.logger.error(f"保存 WebSocket 日志失败: {e}")

    def _mask_url(self, url):
        """
        对 URL 进行脱敏处理

        :param url: 原始 URL
        :return: 脱敏后的 URL
        """
        # 保留协议和主机部分，隐藏敏感参数
        if '?' in url:
            base, params = url.split('?', 1)
            # 对参数进行简化处理
            return f"{base}?..."
        return url