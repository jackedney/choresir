# Sentinel Security Journal

This journal documents security vulnerabilities discovered, lessons learned, and preventive measures implemented in the Amarillo project.

---

## 2026-01-17 - [Timing Attack Prevention]
**Vulnerability:** The application was using direct string comparison (`!=`) for verifying house codes and passwords during user onboarding. This is vulnerable to timing attacks where an attacker can deduce the password length or content by measuring how long the comparison takes. Additionally, using logical OR with short-circuit evaluation allowed attackers to distinguish between invalid house codes vs invalid passwords based on execution time.

**Learning:** Even in non-cryptographic contexts like simple passwords, using standard equality checks can leak information. Furthermore, combining constant-time comparisons with short-circuit logical operators undermines the timing attack protection.

**Prevention:**
1. Replaced `!=` with `secrets.compare_digest()` which performs a constant-time comparison
2. Used bitwise AND (`&`) instead of logical OR to ensure both comparisons always execute, preventing timing-based information leakage about which credential failed

## 2026-01-17 - [PocketBase Filter Injection]
**Vulnerability:** The application constructed PocketBase filter queries using f-strings with unsanitized user input (e.g., `phone = "{phone}"`). This allowed attackers to inject filter logic (e.g., `||`) to bypass checks or retrieve unauthorized records.
**Learning:** PocketBase's Python SDK requires raw filter strings and does not automatically parameterize inputs like SQL drivers. Developers must explicitly sanitize inputs when building filter strings.
**Prevention:** Introduced `src.core.db_client.sanitize_param` which uses `json.dumps` to correctly escape quotes and backslashes. All dynamic filter construction must use this helper.
