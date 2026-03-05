---
name: tech-httpx
description: Reference guide for httpx — async HTTP client for outbound WAHA API calls
user-invocable: false
---

# httpx

> Purpose: Async HTTP client — outbound messages to WAHA API (send text, manage sessions)
> Docs: https://www.python-httpx.org
> Version researched: latest

## Quick Start

```python
import httpx

async with httpx.AsyncClient(
    base_url="http://waha:3000",
    headers={"X-Api-Key": "your-api-key"},
    timeout=10.0,
) as client:
    resp = await client.post("/api/sendText", json={...})
    resp.raise_for_status()
```

## Common Patterns

### Long-lived client (recommended for WAHAClient)

```python
class WAHAClient:
    def __init__(self, base_url: str, api_key: str, http: httpx.AsyncClient) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._http = http

    async def send(self, chat_id: str, text: str) -> None:
        resp = await self._http.post(
            "/api/sendText",
            json={"chatId": chat_id, "text": text, "session": "default"},
            headers={"X-Api-Key": self._api_key},
        )
        resp.raise_for_status()
```

### Lifecycle management in FastAPI lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(base_url=settings.waha_url, timeout=10.0) as http:
        app.state.http = http
        yield
```

### Error handling

```python
try:
    resp = await client.post("/api/sendText", json=payload)
    resp.raise_for_status()
except httpx.HTTPStatusError as e:
    logger.error("WAHA API error", status=e.response.status_code, body=e.response.text)
    raise
except httpx.RequestError as e:
    logger.error("WAHA connection error", error=str(e))
    raise
```

### Timeout configuration

```python
# Different timeouts for connect vs read
timeout = httpx.Timeout(30.0, connect=5.0)
client = httpx.AsyncClient(timeout=timeout)

# Disable timeout for long-polling (avoid in general)
resp = await client.get("/api/session/status", timeout=None)
```

### Testing with pytest-httpx

```python
import pytest
from pytest_httpx import HTTPXMock

@pytest.mark.anyio
async def test_send_message(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url="http://waha:3000/api/sendText", status_code=200)
    client = WAHAClient("http://waha:3000", "key", httpx.AsyncClient())
    await client.send("group@g.us", "Hello")
```

## Gotchas & Pitfalls

- **Don't create a new `AsyncClient` per request**: Creating clients is expensive (connection pool setup). Share a single client for the app's lifetime via the lifespan context.
- **`raise_for_status()` is explicit**: httpx does not raise on 4xx/5xx by default. Always call `raise_for_status()` or check `resp.status_code`.
- **`base_url` trailing slash**: `base_url="http://waha:3000"` + path `"/api/sendText"` works correctly. Avoid trailing slash on `base_url` if paths start with `/`.
- **Connection pool limits**: Default max connections is 100. For a single downstream service (WAHA), this is more than sufficient.
- **`aclose()` on explicit lifecycle**: If not using `async with`, call `await client.aclose()` on shutdown to drain connections.

## Idiomatic Usage

Inject `httpx.AsyncClient` into service constructors rather than creating it inside methods. This enables testing with mock responses without patching internals.

```python
# Good — injectable
class WAHAClient:
    def __init__(self, http: httpx.AsyncClient): ...

# Avoid — hidden dependency
async def send_message(chat_id: str, text: str):
    async with httpx.AsyncClient() as client:  # new client each call
        ...
```
