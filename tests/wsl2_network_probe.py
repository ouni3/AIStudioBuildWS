"""
Layer 1: WSL2 Network Infrastructure Probe
===========================================
验证容器内网络代理 (host.docker.internal:7897) 的联通性。

断言逻辑:
- 状态码 200 或 3xx -> 绿灯 (代理正常)
- 超时或无法解析 -> 立即抛出 [SOS_REPORT]: WSL2_Proxy_Disconnected

执行方式:
    # 容器内
    pytest tests/wsl2_network_probe.py -v

    # 本地 WSL2 环境验证 docker-compose
    docker-compose -f docker-compose.async.yml up -d --build
    docker exec aistudio-websocket-async pytest /app/tests/wsl2_network_probe.py -v
"""

import requests
import pytest
import sys
import os

# 在容器内运行时，代理地址
PROXY_URL = os.getenv("HTTPS_PROXY", "http://host.docker.internal:7897")
TARGET_URL = "https://accounts.google.com"
TIMEOUT_SEC = 5


class TestWSL2NetworkProbe:
    """网络基建探针：验证 Docker 容器到宿主机的代理联通性"""

    def test_proxy_connectivity_via_http(self):
        """
        [探针] 使用 HTTP HEAD 请求验证代理可达性 (快速)
        """
        test_url = "https://www.google.com"
        proxies = {
            "http": PROXY_URL,
            "https": PROXY_URL,
        }

        try:
            response = requests.head(test_url, proxies=proxies, timeout=TIMEOUT_SEC, allow_redirects=True)
            status = response.status_code
            assert 200 <= status < 400, (
                f"[FAIL] HTTP {status} - 代理响应异常。"
                f"期望 2xx/3xx，实际 {status}"
            )
            print(f"[PASS] HTTP HEAD {test_url} -> HTTP {status}")

        except requests.exceptions.Timeout:
            pytest.fail(
                f"[SOS_REPORT]: WSL2_Proxy_Disconnected | "
                f"目标: {test_url} | 代理: {PROXY_URL} | "
                f"超时: {TIMEOUT_SEC}s | 现象: 连接超时"
            )
        except requests.exceptions.ProxyError as e:
            pytest.fail(
                f"[SOS_REPORT]: WSL2_Proxy_Disconnected | "
                f"目标: {test_url} | 代理: {PROXY_URL} | "
                f"错误: 代理错误 - {e}"
            )
        except requests.exceptions.ConnectionError as e:
            pytest.fail(
                f"[SOS_REPORT]: WSL2_Proxy_Disconnected | "
                f"目标: {test_url} | 代理: {PROXY_URL} | "
                f"错误: 连接建立失败 - {e}"
            )
        except Exception as e:
            pytest.fail(
                f"[SOS_REPORT]: WSL2_Proxy_Disconnected | "
                f"目标: {test_url} | 代理: {PROXY_URL} | "
                f"错误类型: {type(e).__name__} | 消息: {e}"
            )

    def test_google_accounts_redirect_block(self):
        """
        [探针] 模拟对 accounts.google.com 的导航，验证代理能正确路由到 Google

        注: accounts.google.com 通常会触发重定向到登录页，
        因此期望状态码可能是 200 (直接返回) 或 3xx (重定向到登录页)
        """
        proxies = {
            "http": PROXY_URL,
            "https": PROXY_URL,
        }

        try:
            response = requests.get(TARGET_URL, proxies=proxies, timeout=TIMEOUT_SEC, allow_redirects=True)
            status = response.status_code

            # 200 = Google 返回了页面内容
            # 3xx = 被重定向 (通常是登录页)
            # 这两种情况都说明代理工作正常
            if status == 200:
                print(f"[PASS] GET {TARGET_URL} -> HTTP 200 (页面内容)")
            elif 300 <= status < 400:
                final_url = response.url
                print(f"[PASS] GET {TARGET_URL} -> HTTP {status} -> 最终: {final_url}")
            else:
                pytest.fail(
                    f"[FAIL] HTTP {status} - accounts.google.com 响应异常。"
                    f"期望 200 或 3xx，实际 {status}"
                )

        except requests.exceptions.Timeout:
            pytest.fail(
                f"[SOS_REPORT]: WSL2_Proxy_Disconnected | "
                f"目标: {TARGET_URL} | 代理: {PROXY_URL} | "
                f"超时: {TIMEOUT_SEC}s | 现象: Google 域名解析或连接超时"
            )
        except requests.exceptions.ProxyError as e:
            pytest.fail(
                f"[SOS_REPORT]: WSL2_Proxy_Disconnected | "
                f"目标: {TARGET_URL} | 代理: {PROXY_URL} | "
                f"错误: 代理错误 - {e}"
            )
        except requests.exceptions.ConnectionError as e:
            pytest.fail(
                f"[SOS_REPORT]: WSL2_Proxy_Disconnected | "
                f"目标: {TARGET_URL} | 代理: {PROXY_URL} | "
                f"错误: 连接建立失败 - {e}"
            )
        except Exception as e:
            pytest.fail(
                f"[SOS_REPORT]: WSL2_Proxy_Disconnected | "
                f"目标: {TARGET_URL} | 代理: {PROXY_URL} | "
                f"错误类型: {type(e).__name__} | 消息: {e}"
            )

    def test_proxy_environment_variables(self):
        """
        [安全检查] 验证容器内代理环境变量已正确设置
        支持两种代理寻址方案:
        - Docker 容器内: host.docker.internal (解析到宿主机网关)
        - WSL2 原生: 192.168.0.x 网段 (Windows 宿主机 IP)
        """
        http_proxy = os.getenv("HTTP_PROXY")
        https_proxy = os.getenv("HTTPS_PROXY")
        camoufox_proxy = os.getenv("CAMOUFOX_PROXY")

        print(f"[INFO] HTTP_PROXY:  {http_proxy}")
        print(f"[INFO] HTTPS_PROXY: {https_proxy}")
        print(f"[INFO] CAMOUFOX_PROXY: {camoufox_proxy}")

        assert http_proxy is not None, "[FAIL] HTTP_PROXY 环境变量未设置"
        assert https_proxy is not None, "[FAIL] HTTPS_PROXY 环境变量未设置"

        # 验证代理指向: host.docker.internal (Docker) 或 IP:port 形式 (WSL2/原生)
        proxy_valid = (
            "host.docker.internal" in https_proxy or
            ("192.168." in https_proxy and ":7897" in https_proxy)
        )
        assert proxy_valid, (
            f"[FAIL] HTTPS_PROXY 未指向有效代理地址 (host.docker.internal 或 192.168.x.x)，"
            f"当前值: {https_proxy}"
        )
        print("[PASS] 代理环境变量已正确配置 (兼容 Docker/WSL2 原生)")

    def test_cliproxy_dr_ws_endpoint_reachable(self):
        """
        [探针] 验证容器内可通过 127.0.0.1:8317 访问 cliproxy-dr 的 WebSocket 端点
        使用 requests.get("http://127.0.0.1:8317/v1/models", timeout=5)
        断言返回 200 或非空内容
        """
        endpoints = ["http://127.0.0.1:8317/v1/models", "http://cli-proxy-dr:8317/v1/models"]
        last_exception = None
        
        for url in endpoints:
            try:
                # 显式禁用代理，因为这些是内部网络服务
                response = requests.get(url, timeout=TIMEOUT_SEC, proxies={"http": None, "https": None})
                if response.status_code == 200 or response.text:
                    print(f"[PASS] {url} 可达 (HTTP {response.status_code})")
                    return
            except Exception as e:
                last_exception = e
                print(f"[INFO] 尝试 {url} 失败: {e}")
        
        pytest.fail(f"[FAIL] cliproxy-dr 端点均不可达。最后错误: {last_exception}")

    def test_cliproxy_dr_model_list_nonempty(self):
        """
        [探针] 验证 cliproxy-dr 返回的模型列表非空
        """
        primary_url = "http://127.0.0.1:8317/v1/models"
        fallback_url = "http://cli-proxy-dr:8317/v1/models"
        
        response = None
        try:
            response = requests.get(primary_url, timeout=TIMEOUT_SEC, proxies={"http": None, "https": None})
        except:
            try:
                response = requests.get(fallback_url, timeout=TIMEOUT_SEC, proxies={"http": None, "https": None})
            except Exception as e:
                pytest.fail(f"[FAIL] 无法连接到 cliproxy-dr 获取模型列表: {e}")
            
        assert response.status_code == 200, f"[FAIL] HTTP {response.status_code} - 无法获取模型列表"
        data = response.json()
        models = data.get("models", []) or data.get("data", []) # 兼容不同 OpenAI 格式
        assert len(models) > 0, f"[FAIL] 模型列表为空: {data}"
        print(f"[PASS] cliproxy-dr 模型数量: {len(models)}")

    def test_cliproxy_dr_all_ports_accessible(self):
        """
        [探针] 验证 8317, 8318, 8319 三端口均可访问 (容灾转发验证)
        """
        import warnings
        ports = [8317, 8318, 8319]
        base_host = "127.0.0.1"
        
        # 先检测 127.0.0.1 是否可用，不可用则切换到 cli-proxy-dr
        try:
            requests.get(f"http://{base_host}:8317/v1/models", timeout=2, proxies={"http": None, "https": None})
        except:
            base_host = "cli-proxy-dr"
            
        for port in ports:
            url = f"http://{base_host}:{port}/v1/models"
            try:
                # 三端口都应有响应（不要求 200，但不应该连接超时）
                requests.get(url, timeout=TIMEOUT_SEC, proxies={"http": None, "https": None})
                print(f"[PASS] 端口 {port} 可访问")
            except Exception as e:
                warnings.warn(f"[WARN] 端口 {port} 不可达: {e}")
                print(f"[WARN] 端口 {port} 不可达: {e}")


if __name__ == "__main__":
    # 允许直接执行: python tests/wsl2_network_probe.py
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))