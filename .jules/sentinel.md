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

## 2026-02-19 - [Sensitive Data Exposure in Auxiliary Collections]
**Vulnerability:** Collections `join_sessions`, `personal_chores`, and `personal_chore_logs` were left with public API rules (`""`), exposing personal phone numbers and private chore data.
**Learning:** Security audits must cover all collections, including auxiliary or "temporary" ones like `join_sessions`. Comments suggesting public access is "needed for webhook processing" can be misleading when the backend uses admin privileges.
**Prevention:** Verify the actual client usage (Admin vs. User) before trusting comments claiming public access is required. Audit all collections during security reviews, not just the core ones.

## 2026-02-27 - [Hardcoded Password in User Provisioning]
**Vulnerability:** The user onboarding process (`user_service.request_join`) used a hardcoded string (`"temp_password_will_be_set_on_activation"`) as the initial password for pending user accounts.
**Learning:** Hardcoding credentials, even for temporary or pending accounts, creates a persistent vulnerability. If the pending account status is bypassed or if the user becomes active without changing the password, the account remains compromised.
**Prevention:** Use `secrets.token_urlsafe(32)` to generate a cryptographically secure random password for all new accounts, ensuring that even initial/pending accounts are protected against default credential attacks.
