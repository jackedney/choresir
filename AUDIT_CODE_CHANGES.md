# Code Changes Required

**Total Tasks:** 1
**Priority:** HIGH
**PM Decision Status:** RESOLVED

---

## H1. Upgrade PocketBase to v0.23.6

### PM Decision
**APPROVED: Upgrade production to v0.23.6**

Rationale from PM: Tests already validate v0.23.6 successfully, and upgrading aligns with "test what you deploy" principle.

### Problem
**Test/Production Parity Violation**

- **Production:** Uses PocketBase v0.22.0 (specified in deployment docs, docker-compose)
- **Tests:** Use PocketBase v0.23.6 (in test fixtures, CI configuration)
- **Impact:** Tests may pass against v0.23.6 features that fail in v0.22.0 production

### Required Changes

1. **Update `docker-compose.yml`:**
   ```yaml
   services:
     pocketbase:
       image: ghcr.io/muchobien/pocketbase:0.23.6
   ```

2. **Update `docs/DEPLOYMENT.md`:**
   - Change PocketBase version references from v0.22.0 to v0.23.6

3. **Update `docs/RAILWAY_DEPLOYMENT.md`:**
   - Change PocketBase version in deployment instructions

4. **Update `.env.example`** if it contains version references

### Testing Plan
1. Review PocketBase v0.23.x changelog for breaking changes
2. Test database migration path in staging
3. Run full test suite against upgraded version
4. Backup production database before upgrade
5. Deploy with rollback plan ready

### Verification
After implementation:
1. Confirm production and test environments use same PocketBase version (v0.23.6)
2. Run full test suite
3. Verify deployment documentation matches actual deployed version

---

## Implementation Notes

This is a straightforward version bump. The main risk is schema migration - review the PocketBase changelog between v0.22.0 and v0.23.6 before deploying.
