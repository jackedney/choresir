1. **Add rate limiting mechanism to admin login**
   - Import `threading` and `time` (if not already imported).
   - Create a global `_login_attempts` dictionary and a `_login_lock` for thread safety.
   - Update `login_post` in `src/choresir/admin/pages.py` to inject the `req` parameter (Starlette Request) and use `req.client.host` for IP-based rate limiting.
   - Implement rate limiting logic: allow up to 5 attempts per minute per IP. Evict oldest IPs if the dictionary size exceeds a threshold (e.g., 1000) using `del dict[next(iter(dict))]` to prevent memory exhaustion and DoS.
   - Return a redirect to `/admin/login?error=ratelimit` if the rate limit is exceeded.
2. **Update the login page to handle rate limit errors**
   - Update `login_get` in `src/choresir/admin/pages.py` to accept an `error` query parameter and display an appropriate error message.
3. **Complete pre-commit steps**
   - Ensure proper testing, verification, review, and reflection are done.
4. **Submit the change**
   - Commit and submit the code as Sentinel.
