# ADR 004: Redis Caching for Leaderboard Performance

## Status

Implemented - Alternatives under evaluation

## Context

The application requires real-time leaderboard functionality to display top-performing home service providers based on various metrics (ratings, completed jobs, response times, etc.). Initial implementation used direct database aggregation queries on each request, which presented performance challenges:

1. **Query Complexity**: Leaderboard generation requires complex aggregation across multiple tables (users, bookings, ratings, verifications)
2. **Query Frequency**: Leaderboards are frequently accessed by users and displayed prominently in the application
3. **Data Freshness**: Real-time accuracy is desirable but not critical - staleness of 1-5 minutes is acceptable
4. **Scalability**: Direct database queries would not scale efficiently as user base and booking volume grow

Key evaluation criteria included:
- Query performance improvement
- Implementation complexity
- Infrastructure requirements
- Data freshness guarantees
- Operational overhead

## Decision

We will use **Redis for leaderboard caching** to improve performance of aggregation queries.

## Rationale

### Performance Benefits
- Reduces database load by serving frequently-accessed leaderboard data from memory
- Aggregation queries executed periodically rather than on every request
- Sub-millisecond response times for cached leaderboard data
- Enables handling higher concurrent user loads without database bottlenecks

### Implementation Simplicity
- Redis provides native support for sorted sets, ideal for leaderboard use cases
- Straightforward integration with Python using redis-py client
- Cache invalidation strategy is simple: time-based expiration with periodic refresh

### Data Freshness Trade-off
- Leaderboard data does not require real-time accuracy
- Acceptable staleness window (1-5 minutes) provides significant performance gains
- TTL-based cache invalidation ensures data freshness without manual intervention

### Infrastructure Considerations
- Railway platform (current deployment target) offers managed Redis as a service
- Minimal operational overhead compared to self-managed Redis
- Simple scaling path if caching needs expand

## Consequences

### Positive
- **Significant performance improvement**: Leaderboard queries served in <10ms vs 200-500ms
- **Reduced database load**: Frees up database connections for transaction processing
- **Better user experience**: Faster page loads and smoother scrolling
- **Scalability foundation**: Caching infrastructure in place for future needs
- **Simple maintenance**: Managed Redis on Railway requires minimal operations work

### Negative
- **Additional infrastructure dependency**: Introduces Redis as a required service
- **Increased deployment complexity**: One more service to configure and monitor
- **Cost increase**: Managed Redis adds ~$5-10/month to infrastructure costs
- **Data staleness**: Leaderboard may show slightly outdated information
- **Failure mode consideration**: Application behavior needs to handle Redis unavailability

### Neutral
- Cache invalidation strategy requires ongoing tuning based on usage patterns
- Monitoring needed to track cache hit rates and performance metrics
- Development team needs Redis expertise for troubleshooting

## Implementation Details

### Current Approach
- Redis sorted sets store leaderboard rankings
- Background job refreshes leaderboard data every 5 minutes
- Cache keys use TTL of 10 minutes as failsafe
- Fallback to direct database query if Redis unavailable

### Cache Key Structure
```
leaderboard:daily:{date}
leaderboard:weekly:{week}
leaderboard:monthly:{month}
leaderboard:all-time
```

## Alternatives Considered

### Direct Database Queries Only
**Rejected** due to:
- Poor performance at scale (200-500ms query times)
- Inefficient use of database resources
- Negative impact on user experience
- Does not support future growth

### Materialized Views
**Considered but not selected** because:
- Requires PostgreSQL-specific features
- More complex to maintain and refresh
- Less flexible than application-level caching
- Harder to implement incremental updates
- May revisit if Redis proves inadequate

### Application-Level In-Memory Cache
**Considered but not selected** because:
- Does not share cache across multiple application instances
- Requires cache warming on each instance startup
- More complex cache invalidation in distributed environment
- Redis provides better tooling and monitoring

### Database Query Optimization Only
**Insufficient alone** because:
- Indexes and query optimization attempted first
- Fundamental limitation: aggregation requires scanning large datasets
- Performance improvements were marginal
- Caching remains necessary for acceptable performance

## Future Considerations

- **Alternative evaluation**: Continue evaluating materialized views, database optimizations, or other caching strategies
- **Cache expansion**: Consider caching other frequently-accessed aggregated data
- **Redis clustering**: May need Redis cluster if single instance becomes bottleneck
- **Cache warming strategy**: Implement proactive cache warming for better cold-start performance
- **Monitoring**: Track cache hit rates, Redis memory usage, and query performance metrics
- **Cost optimization**: Re-evaluate if managed Redis costs become significant relative to value provided

## Migration Path

If future evaluation indicates Redis is not the optimal solution:
1. Implement alternative caching/optimization approach alongside Redis
2. A/B test performance and reliability
3. Gradually shift traffic to new approach
4. Deprecate Redis once new solution proven
5. Estimated effort: 2-3 engineering days

## Related ADRs

- [ADR 011: Version Management Strategy](011-version-management.md) - Establishes version parity requirements that apply to Redis infrastructure

## References

- Redis Sorted Sets: https://redis.io/docs/data-types/sorted-sets/
- Railway Redis: https://docs.railway.app/databases/redis
- PM Decision: Redis selected for initial implementation, alternatives to be evaluated based on operational experience
