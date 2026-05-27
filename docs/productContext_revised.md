# AIStudioBuildWS Product Context

## 1. Vision & Core Goals
AIStudioBuildWS serves as a high-performance, stealthy **Browser Worker (Provider)** for the Google AI Studio environment. It is designed to work in tandem with an API Gateway (`moe-cli-proxy-dr`) to bridge high-concurrency LLM inference requests to the AI Studio web interface.

- **Stealth**: Utilize `camoufox` and advanced stealth patches to evade bot detection.
- **Scalability**: Decoupled architecture allows multiple worker shards to feed into a single gateway.
- **Reliability**: Automated session persistence and passive WebSocket monitoring.

## 2. Decoupled Architecture Model
The system operates on a clear decoupling between the **API Gateway** and the **Browser Worker**.

### 2.1 Role Definitions
- **API Gateway (`moe-cli-proxy-dr`)**:
    - Central traffic controller and load balancer.
    - Exposes OpenAI/Gemini compatible endpoints to end-users.
    - Hosts the WebSocket Server (`/v1/ws`) for provider registration.
- **Browser Worker (`aistudio-shard`)**:
    - Executes localized browser instances (`camoufox`).
    - Injects authentication cookies and navigates to Google AI Studio.
    - Page-level JS logic initiates the connection *outward* to the Gateway.
    - Passive logging of page-level WebSocket traffic.

### 2.2 Communication Flow
1. **Startup**: Browser Worker launches and opens AI Studio.
2. **Inbound**: The worker receives NO inbound task traffic.
3. **Outbound**: The AI Studio page JS connects to the Gateway's WS server.
4. **Execution**: Gateway pushes tasks over WS; page JS executes via AI Studio DOM and returns results via WS.

## 3. Connectivity: Mixed Content Bypass
To navigate the security restrictions of secure browser contexts (HTTPS), the worker utilizes a local loopback tunnel.

- **The Problem**: Secure browser contexts often block Mixed Content (connecting to non-TLS/different origin WSS).
- **The Solution (socat Tunneling)**:
    - A `socat` process runs within the container listening on `127.0.0.1:8317`.
    - It transparently forwards traffic to `moe-cli-proxy-dr:8317`.
    - The browser page connects to `ws://127.0.0.1:8317/v1/ws`, which is treated as a safe local loopback, bypassing Mixed Content blocks.

## 4. Diagnostics & Troubleshooting
### 4.1 Connectivity Checklist
- **[L1] Container Listeners**: Verify `socat` is listening on `127.0.0.1:8317` and Flask on `0.0.0.0:7860`.
- **[L2] Gateway Reachability**: Ensure the worker container can resolve and reach `moe-cli-proxy-dr:8317/v1/models`.
- **[L3] Page Outbound**: Check `WebSocketLogger` output. If no WS connections are attempted, the page JS failed to load or configurations (WEBSOCKET_PROXY_URL) are missing.

### 4.2 Common Failure Patterns
- **1006 Close**: Infrastructure/network instability or page keepalive failure.
- **Unauthorized**: JWT_TOKEN or `wsauth` mismatch between worker config and Gateway settings.
- **Mixed Content Block**: Occurs if `socat` is missing and the browser attempts to connect directly to an external non-TLS endpoint.
