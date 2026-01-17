# Sentinel's Security Journal

## 2026-01-17 - [Timing Attack Prevention]
**Vulnerability:** The application was using direct string comparison (`!=`) for verifying house codes and passwords during user onboarding. This is vulnerable to timing attacks where an attacker can deduce the password length or content by measuring how long the comparison takes.
**Learning:** Even in non-cryptographic contexts like simple passwords, using standard equality checks can leak information.
**Prevention:** Replaced `!=` with `secrets.compare_digest()` which performs a constant-time comparison, making the time taken independent of the input content.
