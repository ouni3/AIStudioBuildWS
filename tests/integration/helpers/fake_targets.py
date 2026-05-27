import asyncio
import json
from aiohttp import web

class FakeTargets:
    """
    本地可控的 mock redirect 与 websocket 服务器
    用于验证极速斩杀和 WS 隔离
    """
    def __init__(self, port=8888):
        self.port = port
        self.base_url = None
        self.app = web.Application()
        self.app.add_routes([
            web.get('/signin', self.handle_redirect),
            web.get('/ws', self.handle_ws),
            web.get('/normal', self.handle_normal)
        ])
        self.runner = None

    async def handle_normal(self, request):
        return web.Response(text="<html><body><h1>Normal Page</h1></body></html>", content_type='text/html')

    async def handle_redirect(self, request):
        # 模拟跳转到 google login
        return web.HTTPFound(location='https://accounts.google.com/signin')

    async def handle_ws(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        account_id = request.query.get('account_id', 'unknown')
        
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                # 简单回显并包含 account_id
                data = {"msg": msg.data, "account_id": account_id, "server_ts": asyncio.get_event_loop().time()}
                await ws.send_str(json.dumps(data))
            elif msg.type == web.WSMsgType.ERROR:
                break
        return ws

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', self.port)
        await site.start()
        sockets = getattr(site, '_server', None).sockets if getattr(site, '_server', None) else None
        if sockets:
            bound_port = sockets[0].getsockname()[1]
        else:
            bound_port = self.port
        self.port = bound_port
        self.base_url = f'http://127.0.0.1:{self.port}'

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
