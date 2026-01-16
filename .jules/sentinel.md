## 2026-01-16 - [Fix Predictable User Passwords]
**Vulnerability:** New users created via the "join" flow were assigned a hardcoded password ("temp_password_will_be_set_on_activation").
**Learning:** Even if users don't use passwords to login (using WhatsApp instead), the underlying auth system (PocketBase) still requires them. If the API is exposed, these predictable passwords allow account takeover.
**Prevention:** Always generate cryptographically strong random passwords for accounts created programmatically, even if the primary auth method is different. Use `secrets` module for CSPRNG.
