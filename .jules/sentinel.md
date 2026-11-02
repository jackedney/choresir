## 2025-02-14 - Fix Missing Rate Limiting on Admin Login
**Vulnerability:** The admin login endpoint at `/admin/login/submit` was missing rate limiting, allowing unlimited brute-force attempts on the admin password.
**Learning:** FastHTML apps do not automatically provide rate limiting. We need to implement it at the handler level. IP rate limiting should be space-bounded using safe O(1) eviction for `dict` using `next(iter(dict))` to avoid memory exhaustion DoS vectors. Furthermore, timing should use `time.monotonic()` to guard against clock skew vulnerabilities.
**Prevention:** Implement an in-memory space-bounded dictionary rate limiter for login endpoints based on `req.client.host` properly populated securely by ASGI proxy middleware.
