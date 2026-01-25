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

## 2026-03-05 - [Unbounded Query DoS Prevention]
**Vulnerability:** The `verify_chore` and `get_pending_verifications` functions in `verification_service.py` contained `while True` loops that fetched *all* logs from the database to filter them in memory. This is a Denial of Service (DoS) vulnerability as the logs collection grows.
**Learning:** Using in-memory filtering for database records is unsafe and unscalable. Always push filtering to the database query layer.
**Prevention:**
1. Replaced unbounded loops with specific PocketBase filter queries (e.g., `filter_query='chore_id = "..." && action = "..."'`).
2. Utilized `db_client.get_first_record` for single-record lookups.
3. Added `user_id` filtering to list queries to ensure pagination limits (500) don't hide security-critical records (like self-claims).
