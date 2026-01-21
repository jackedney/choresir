# ADR 002: Version Management Strategy

## Status

Accepted

## Context

The application uses PocketBase as its backend database and API layer, deployed across test and production environments. During early development, version mismatches between environments led to inconsistent behavior, failed migrations, and debugging challenges.

Key issues encountered:
- Test environment running PocketBase v0.22.x while production used v0.23.x
- API behavior differences between versions causing deployment surprises
- Migration scripts working in test but failing in production
- Difficult-to-reproduce bugs due to version drift
- Time wasted debugging environment-specific issues

The critical question: How do we maintain consistency across environments while allowing safe dependency upgrades?

## Decision

**All test and production environments must use identical dependency versions for critical infrastructure components (database, runtime, core libraries).**

Current implementation:
- Upgrade PocketBase to **v0.23.6** across all environments
- Enforce version parity through configuration management
- Establish a process for coordinated version updates

## Rationale

### Test-Production Parity
- Ensures bugs found in test will reproduce in production
- Eliminates "works in test, fails in prod" scenarios
- Makes testing meaningful and reliable
- Reduces deployment risk

### Simplified Debugging
- Single version to understand and debug
- No need to track version-specific behavior differences
- Stack Overflow and documentation searches are more relevant
- Easier onboarding for new developers

### Predictable Deployments
- No surprises from version differences during deployment
- Migration scripts tested against production version
- API behavior is consistent across environments
- Reduces rollback scenarios

### Current Action: PocketBase v0.23.6
- Latest stable release with important bug fixes
- Well-documented upgrade path from v0.22.x
- Active community support
- Addresses known issues in previous versions

## Implementation

### Configuration Files
Version specifications must be explicit in:
- `Dockerfile.pocketbase`: Pin exact PocketBase version
- `docker-compose.yml`: Lock all service versions
- `railway.toml`: Specify runtime versions
- `.env.example`: Document required versions

### Version Update Process
1. **Research**: Review changelog, breaking changes, migration requirements
2. **Update Test**: Deploy new version to test environment first
3. **Validate**: Run full test suite, manual testing, migration verification
4. **Update Prod**: Deploy to production only after test validation
5. **Document**: Update all config files and deployment documentation
6. **Monitor**: Watch for issues in first 24-48 hours post-upgrade

### Version Pinning Strategy
- **Exact versions** for PocketBase and core infrastructure (e.g., `0.23.6`, not `^0.23.0`)
- **Minor version ranges** for application libraries only when appropriate
- **No `latest` tags** in production configurations
- **Document rationale** when intentional version differences are required

## Consequences

### Positive
- **Reliable testing**: Test results accurately predict production behavior
- **Faster debugging**: Eliminates version differences as a variable
- **Safer deployments**: Reduces deployment-related incidents
- **Better documentation**: Single version to document and understand
- **Team confidence**: Developers trust test environment

### Negative
- **Coordination required**: Can't independently upgrade test/prod
- **Update overhead**: Both environments must be updated together
- **Testing time**: Can't test new versions in isolation before committing
- **Rollback complexity**: Both environments must rollback together

### Mitigations
- Use feature flags for application-level experiments
- Maintain local development environments for version exploration
- Schedule upgrade windows during low-traffic periods
- Keep rollback procedures well-documented and tested

## Alternatives Considered

### Test Runs Latest, Prod Stays Stable
**Rejected** because:
- Creates two different systems to understand
- Test results don't predict production behavior
- Leads to "works in test" deployment failures
- Makes debugging production issues harder

### Independent Environment Versioning
**Rejected** because:
- Maximizes configuration drift over time
- Requires tracking multiple version combinations
- Makes issue reproduction extremely difficult
- Increases cognitive load on team

### Rolling Updates (Test → Staging → Prod)
**Deferred** because:
- Current scale doesn't justify staging environment
- Adds infrastructure complexity and cost
- May revisit at larger scale (10K+ users)
- Version parity principle still applies within each environment

## Future Considerations

- Consider staging environment if team grows beyond 5 developers
- Evaluate automated version synchronization tools
- Monitor for version-specific security vulnerabilities
- Review policy quarterly as application matures
- Document exceptions if prod-only patches are needed

## Related ADRs

- [ADR 013: Redis Caching for Leaderboard Performance](013-redis-caching.md) - Another infrastructure component subject to version management requirements

## References

- [Twelve-Factor App: Dev/Prod Parity](https://12factor.net/dev-prod-parity)
- [PocketBase v0.23.6 Changelog](https://github.com/pocketbase/pocketbase/releases/tag/v0.23.6)
- Current deployment: Railway.app configuration
- PM Decision: Documented in AUDIT_PM_DECISIONS.md
