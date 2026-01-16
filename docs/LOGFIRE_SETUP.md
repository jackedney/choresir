# Logfire Setup Guide

Pydantic Logfire provides observability for FastAPI and Pydantic AI with native integration.

## Setup

1. Create account at [logfire.pydantic.dev](https://logfire.pydantic.dev)
2. Create project (e.g., `choresir-dev`)
3. Get write token from **Settings** → **Write Tokens**
4. Add to environment:

**Local (.env):**
```bash
LOGFIRE_TOKEN=lf_your_token_here
```

**Railway:**
Add `LOGFIRE_TOKEN` variable in service settings.

## Verification

Start services and send test request:
```bash
curl http://localhost:8000/health
```

Check dashboard for traces at [logfire.pydantic.dev](https://logfire.pydantic.dev).

## Dashboard Features

- **Live**: Real-time traces as they arrive
- **Traces**: Search and filter historical traces
- **Errors**: Grouped exceptions with stack traces
- **Metrics**: Request rate, error rate, latency percentiles

## Key Metrics

**Development:**
- Error rate (should be 0%)
- Agent tool calls (verify correct behavior)
- Token usage (optimize if >500 per request)

**Production:**
- Error rate spike (indicates bug/outage)
- P99 latency >2.5s (approaching timeout)
- Token usage (tracks OpenRouter costs)

## Privacy

Logfire sees: request metadata, function arguments, LLM prompts/responses, database queries, stack traces.

For sensitive data, consider self-hosted OpenTelemetry instead.

## Costs

**Free Tier:**
- 5 GB/month
- 30-day retention
- Sufficient for 1-3 households

**Pro ($20/month):**
- 50 GB/month
- 90-day retention
- Email/Slack alerts
- Sufficient for 10-20 households

## Disable Temporarily

Remove or comment out `LOGFIRE_TOKEN` in `.env` and restart.

## Troubleshooting

**No traces appearing:**
- Verify `LOGFIRE_TOKEN` is set correctly
- Check startup logs for errors
- Ensure network access to logfire.pydantic.dev

**High data usage:**
```python
# Reduce sampling
logfire.configure(sample_rate=0.1)

# Exclude health checks
logfire.instrument_fastapi(app, excluded_paths=["/health"])
```
