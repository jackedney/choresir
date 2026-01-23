# Sentinel Security Journal

This journal documents security vulnerabilities discovered, lessons learned, and preventive measures implemented in the Amarillo project.

---

## 2026-01-17 - [Timing Attack Prevention]
**Vulnerability:** The application was using direct string comparison (`!=`) for verifying house codes and passwords during user onboarding. This is vulnerable to timing attacks where an attacker can deduce the password length or content by measuring how long the comparison takes. Additionally, using logical OR with short-circuit evaluation allowed attackers to distinguish between invalid house codes vs invalid passwords based on execution time.

**Learning:** Even in non-cryptographic contexts like simple passwords, using standard equality checks can leak information. Furthermore, combining constant-time comparisons with short-circuit logical operators undermines the timing attack protection.

**Prevention:**
1. Replaced `!=` with `secrets.compare_digest()` which performs a constant-time comparison
2. Used bitwise AND (`&`) instead of logical OR to ensure both comparisons always execute, preventing timing-based information leakage about which credential failed

## 2026-02-18 - [Public API Access Lockdown]
**Vulnerability:** PocketBase collections (`users`, `chores`, etc.) were configured with public API rules (`listRule: ""`, etc.), allowing unauthenticated users to list and view all data, including PII like phone numbers.
**Learning:** The initial configuration likely assumed public access was required for the backend service to function or for registration, not realizing that the backend service uses Admin authentication which bypasses these rules.
**Prevention:** Default to restrictive rules (`None`) for all collections. Only enable public or user-scoped rules when there is a direct client-side requirement.

## 2026-05-24 - [PocketBase Filter Injection]
**Vulnerability:** User inputs (like `user_id`) were directly interpolated into PocketBase filter strings (e.g., `f'assigned_to = "{user_id}"'`) in service layers. This allowed attackers to manipulate queries using quote injection (e.g., `user" || true || "`).
**Learning:** Even internal IDs should be treated as untrusted input when constructing raw query strings. The assumption that `user_id` is always a safe system-generated string can be violated by upstream callers or future code changes.
**Prevention:** Always use `src.core.db_client.sanitize_param(value)` when embedding values into filter strings. Ideally, use a query builder if available, but for raw strings, strict sanitization is mandatory.
