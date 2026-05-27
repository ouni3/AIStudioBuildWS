# WebSocket Tunnel Architecture & Bypass Strategy

## 1. Browser Worker / API Gateway Decoupling Model
To handle high-concurrency LLM inference requests while maintaining stealth, the system employs a decoupling strategy:
- **API Gateway (moe-cli-proxy-dr)**: Acts as the central traffic controller, managing model routing, load balancing, and credential injection.
- **Browser Worker (aistudio-shard)**: Runs localized `camoufox` instances to perform actual inference. These workers are ephemeral and state-isolated.
- **Decoupling Benefit**: The gateway doesn't need to know about the browser's complex DOM state, and the browser doesn't need to manage API keys or global routing logic.

## 2. Mixed Content Bypass Tunnel Principle
Directly connecting to a secure WebSocket (WSS) or a different origin API from within a restricted browser environment often triggers "Mixed Content" or CORS violations.
- **The Tunnel**: By creating a local TCP tunnel within the container, we present the external resource as a local resource (`127.0.0.1` or a predictable container alias).
- **Stealth**: This bypasses strict browser security policies that would otherwise block cross-origin WebSocket upgrades or non-HTTPS requests from a secure context.

## 3. `socat` TCP Transparent Forwarding
To implement the tunnel at the network layer without modifying the application logic, we use `socat`.

### Dependencies
- **socat**: Must be installed in the worker image (`apt-get install -y socat`).

### Configuration (Docker Compose)
The worker container starts a background `socat` process before the main application:
```bash
socat TCP-LISTEN:8317,fork,reuseaddr TCP:moe-cli-proxy-dr:8317 &
```
- `TCP-LISTEN:8317`: Listens for incoming traffic on port 8317 within the container.
- `fork`: Spawns a new process for each connection, allowing multiple simultaneous requests.
- `reuseaddr`: Allows immediate restart of the listener if the process cycles.
- `TCP:moe-cli-proxy-dr:8317`: Forwards all traffic to the API Gateway's specific port.

### Environment Requirements
- **NO_PROXY**: The target `moe-cli-proxy-dr` must be included in the `NO_PROXY` environment variable to prevent the tunnel traffic from being intercepted by outgoing corporate/system proxies.
