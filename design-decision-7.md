# Design Decision 7: Async Message Processing Strategy for WhatsApp Chatbot

**Date:** 2026-03-04
**Status:** Proposed
**Context:** Python WhatsApp chatbot using FastAPI or Litestar, SQLite, single-process self-hosted deployment

---

## Problem Statement

A WhatsApp chatbot webhook handler must:

1. Acknowledge webhook receipt (HTTP 200) before completing AI processing — WhatsApp will retry if no fast acknowledgment is received.
2. Deduplicate messages — WhatsApp delivers notifications at-least-once; duplicates are normal operating conditions, not edge cases.
3. Enforce per-user rate limits — prevent one user from monopolising the AI pipeline.
4. Handle AI model unavailability with retry and exponential backoff.
5. Remain simple, maintainable, and deployable as a single process with SQLite and no external infrastructure.

---

## Options Evaluated

### Option 1: FastAPI/Litestar `BackgroundTasks`

The built-in `BackgroundTasks` mechanism (identical API surface in both frameworks) schedules a callable to run in the same event loop after the response has been sent.

**How it works:**

```python
@app.post("/webhook")
async def webhook(payload: WebhookPayload, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_message, payload)
    return {"status": "ok"}
```

**Pros:**
- Zero setup: no extra packages, no infrastructure.
- Trivially simple to understand and test.
- Async-native; no thread overhead.

**Cons:**
- No persistence: tasks are lost if the process crashes or restarts between receipt and completion.
- No built-in deduplication; the developer must implement a seen-ID store manually (e.g., a Python `set` or SQLite table), and that state is also lost on restart.
- No queue: all background tasks run immediately and concurrently with no backpressure mechanism.
- Rate limiting must be layered on entirely by hand; there is no scheduling slot to hook into.
- Retry logic must be embedded inside the task function itself (e.g., via `tenacity`), with no external visibility.
- Confirmed issue: if the request itself raises an exception the background task does not run at all (fastapi/fastapi #2604).
- Confirmed issue: a long-running blocking background task keeps the request lifecycle open in some Starlette versions (fastapi/fastapi Discussion #11210).

**Verdict:** Acceptable only for trivial fire-and-forget work where loss is tolerable. Unsuitable for this use case.

---

### Option 2: Redis + arq (or Celery)

`arq` is a modern async-native job queue backed by Redis. It supports deduplication via stable job IDs, retry/backoff, deferred execution, and result storage. Celery is the older, heavier alternative.

**How it works:**

```python
# Enqueue with stable job ID for deduplication
await queue.enqueue_job("process_message", msg_id, _job_id=f"wamsg:{msg_id}")

# Worker with built-in retry
async def process_message(ctx, msg_id):
    ...
    raise Retry(defer=5)  # built-in retry primitive
```

**Pros:**
- First-class deduplication via `_job_id` parameter: enqueueing the same job ID twice is a no-op.
- Built-in retry/backoff with `Retry(defer=N)` or via `tenacity`.
- Worker pool with configurable concurrency.
- Jobs survive process restarts (stored in Redis).
- Excellent FastAPI integration; widely documented.
- Sub-5ms latency per arq's own benchmarks.
- Actively maintained (v0.27.0 as of 2025).

**Cons:**
- Requires Redis as an external dependency, violating the single-process no-external-infrastructure constraint.
- Adds operational complexity: Redis must be installed, configured, and kept running.
- Per-user rate limiting is not built in; must be implemented with Redis sorted-sets or a separate rate-limiter.
- Celery is even heavier and overkill for a single-user chatbot deployment.

**Verdict:** The right answer for multi-process or multi-host deployments. Overkill and operationally costly for a single self-hosted process.

---

### Option 3: `asyncio.Queue` with Worker Coroutines

A bounded `asyncio.Queue` paired with one or more long-running worker coroutines started at application startup. The webhook handler enqueues the raw payload and returns immediately.

**How it works:**

```python
# Initialised at ASGI startup
message_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
seen_ids: set[str] = set()           # in-memory; backed by SQLite on restart
user_limiters: dict[str, AsyncLimiter] = {}

async def message_worker():
    while True:
        item = await message_queue.get()
        try:
            msg_id = item["id"]
            if msg_id in seen_ids:
                continue
            seen_ids.add(msg_id)
            user_id = item["user_id"]
            limiter = user_limiters.setdefault(user_id, AsyncLimiter(5, 60))
            async with limiter:
                await call_ai_with_backoff(item)
        finally:
            message_queue.task_done()

# Webhook handler
@app.post("/webhook")
async def webhook(payload: dict):
    try:
        message_queue.put_nowait(payload)
    except asyncio.QueueFull:
        return Response(status_code=503)
    return {"status": "ok"}
```

**Pros:**
- Zero external dependencies: pure stdlib plus optional `aiolimiter`.
- Full control over deduplication logic (in-memory `set` for speed; SQLite lookup for cross-restart persistence).
- Natural backpressure via bounded queue: `put_nowait` raises `QueueFull` if the queue is saturated, allowing the handler to return a 503 gracefully.
- Per-user rate limiting is straightforward: maintain a dict of `aiolimiter.AsyncLimiter` instances keyed by `user_id`.
- Retry/backoff is handled inside the worker with `tenacity` wrapping the AI call.
- Lives entirely within the ASGI process: no additional processes or services to manage.
- Worker count is configurable: start N worker coroutines to fan out processing.
- Works identically with FastAPI and Litestar.

**Cons:**
- In-memory queue state is lost on process restart. Jobs that were enqueued but not yet processed are dropped unless the queue is durably backed (see Option 5).
- Deduplication `seen_ids` set is also in-memory by default; must be written to SQLite to survive restarts.
- No built-in UI or observability: must instrument manually.
- Retry sleep inside the worker blocks that worker slot for the duration of all retry delays unless the re-enqueue pattern is used (put a deferred item back into the queue rather than sleeping inline).

**Verdict:** Best overall fit for this project given the constraints when crash-safety of in-flight messages is acceptable. The only gap versus the full requirements list is durability, which Option 5 closes.

---

### Option 4: Ad-hoc `asyncio.create_task` (In-Process Task Spawning)

Rather than a structured queue, tasks are spawned on demand with `asyncio.create_task`. Functionally similar to `BackgroundTasks` but managed explicitly.

**How it works:**

```python
_tasks: set[asyncio.Task] = set()

@app.post("/webhook")
async def webhook(payload: dict):
    t = asyncio.create_task(process_message(payload))
    _tasks.add(t)         # prevent garbage collection
    t.add_done_callback(_tasks.discard)
    return {"status": "ok"}
```

**Pros:**
- Extremely simple to write.
- Async-native, low overhead.

**Cons:**
- Unbounded concurrency: every incoming webhook spawns a task immediately with no queue depth limit and no backpressure.
- Same lack of persistence as `BackgroundTasks`.
- A WhatsApp flood or retry storm would spawn thousands of concurrent coroutines consuming memory and event-loop slots.
- Deduplication and rate limiting are just as manual as in Option 3, but without the natural serialisation a queue provides.
- Task references must be kept alive manually to prevent premature garbage collection (Python `asyncio` docs explicitly warn about this).

**Verdict:** Strictly worse than Option 3. The queue structure in Option 3 adds backpressure and natural serialisation at negligible extra cost.

---

### Option 5: SQLite-Backed Job Queue (Custom `message_jobs` Table)

Jobs are written to a SQLite table before the webhook returns. A worker loop polls the table, claims and processes jobs, and marks them complete. A thin custom table is preferred over third-party libraries (`persist-queue`, `huey`, `stq`) to keep full control, use `aiosqlite` directly, and keep the queue schema visible in the project's own migrations.

**Schema:**

```sql
CREATE TABLE IF NOT EXISTS message_jobs (
    id         TEXT PRIMARY KEY,       -- WhatsApp message_id (dedup key)
    user_id    TEXT NOT NULL,
    payload    TEXT NOT NULL,          -- JSON blob of raw webhook payload
    status     TEXT DEFAULT 'pending', -- pending | processing | done | failed
    attempts   INTEGER DEFAULT 0,
    run_after  REAL DEFAULT 0,         -- unix epoch; worker skips rows where run_after > now()
    created_at REAL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_runafter
    ON message_jobs (status, run_after);
```

**How it works:**

```python
# Webhook handler: fast insert, immediate 200
@app.post("/webhook")
async def webhook(payload: dict, db: AsyncConnection):
    msg_id = extract_message_id(payload)
    if msg_id:
        await db.execute(
            "INSERT OR IGNORE INTO message_jobs (id, user_id, payload) VALUES (?,?,?)",
            (msg_id, extract_user_id(payload), json.dumps(payload))
        )
        await db.commit()
    return {"status": "ok"}

# Worker coroutine (started in ASGI lifespan)
BACKOFF_SECS = [5, 30, 120, 600]
MAX_ATTEMPTS = 4

async def message_worker(db_path: str):
    user_limiters: dict[str, AsyncLimiter] = {}
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        while True:
            row = await claim_next_job(db)   # SELECT ... FOR UPDATE equivalent via status='processing'
            if row is None:
                await asyncio.sleep(0.2)
                continue
            job_id, user_id, payload_json, attempts = row
            limiter = user_limiters.setdefault(user_id, AsyncLimiter(5, 60))
            async with limiter:
                try:
                    await call_ai(json.loads(payload_json))
                    await db.execute(
                        "UPDATE message_jobs SET status='done' WHERE id=?", (job_id,)
                    )
                except AIUnavailable:
                    delay = BACKOFF_SECS[min(attempts, len(BACKOFF_SECS) - 1)]
                    await db.execute(
                        "UPDATE message_jobs SET status='pending', attempts=?, run_after=? WHERE id=?",
                        (attempts + 1, time.time() + delay, job_id)
                    )
                except Exception:
                    if attempts + 1 >= MAX_ATTEMPTS:
                        await db.execute(
                            "UPDATE message_jobs SET status='failed' WHERE id=?", (job_id,)
                        )
                    else:
                        delay = BACKOFF_SECS[min(attempts, len(BACKOFF_SECS) - 1)]
                        await db.execute(
                            "UPDATE message_jobs SET status='pending', attempts=?, run_after=? WHERE id=?",
                            (attempts + 1, time.time() + delay, job_id)
                        )
                await db.commit()
```

**Pros:**
- Full durability: jobs survive process crashes and restarts.
- Deduplication is native: `INSERT OR IGNORE` on the `message_id` primary key; WhatsApp re-deliveries are silently discarded without any application logic.
- Per-user rate limiting: in-memory `aiolimiter.AsyncLimiter` dict keyed by `user_id`, no extra DB reads needed.
- Retry/backoff: set `run_after = now() + backoff` on failure; worker only claims rows where `run_after <= now()`. No `tenacity` required for scheduling, though `tenacity` can still wrap the AI call for cleaner code.
- No external dependencies beyond SQLite and `aiosqlite`, which are already present.
- Compatible with both FastAPI and Litestar.
- Single-process deployment: worker runs as a background coroutine started in the ASGI lifespan handler.
- Observable: the `message_jobs` table is a queryable audit log with full processing history.
- Crash recovery is automatic: rows left in `processing` status on restart can be reset to `pending` at startup.

**Cons:**
- More boilerplate than Option 3 if rolling a custom table (though the schema and worker loop are small and self-contained).
- SQLite write throughput could become a bottleneck at very high message volume — not a concern at chatbot scale (tens of messages per minute, not thousands).
- WAL mode must be explicitly enabled for concurrent reads alongside writes.
- Polling introduces latency (configurable; 100-500ms at 200ms sleep interval) vs. the immediate dispatch of an in-memory queue. Acceptable for chatbot response times where the AI call itself dominates latency.
- Third-party SQLite queue libraries (`persist-queue`, `huey`, `stq`) add dependencies and may not expose all needed SQLite tuning knobs; rolling a custom table is the preferred approach here.

**Verdict:** The correct answer when durability is a hard requirement. Adds modest, well-contained complexity over Option 3 in exchange for crash safety and a queryable audit log.

---

## Comparison Table

| Criterion | BackgroundTasks | Redis + arq | asyncio.Queue + workers | ad-hoc create_task | SQLite-backed queue |
|---|---|---|---|---|---|
| **Simplicity** | Highest | Medium | High | High | Medium-High |
| **Reliability (crash safety)** | None | High (Redis) | None | None | High (SQLite) |
| **Deduplication** | Manual only | Built-in (job ID) | Manual (easy) | Manual only | Native (PK INSERT OR IGNORE) |
| **Per-user rate limiting** | Manual only | Manual (Redis) | Easy (limiter dict) | Manual only | Easy (limiter dict at dequeue) |
| **Retry / backoff** | Manual (tenacity) | Built-in | tenacity in worker | Manual (tenacity) | Native (run_after column) |
| **External dependencies** | None | Redis required | None | None | None |
| **Single-process suitability** | Poor | Poor | Excellent | Poor | Excellent |
| **Backpressure** | None | Queue depth | Bounded queue | None | Queue depth (DB rows) |
| **Observability** | None | Redis UI / arq UI | Manual logging | None | Queryable DB table |
| **Persistence across restart** | No | Yes | No | No | Yes |
| **Production maturity** | Good | Excellent | Good | Marginal | Good |

---

## Recommendation

### Primary: SQLite-Backed Job Queue (Option 5) with a custom `message_jobs` table

This is the only option that satisfies all five stated requirements without introducing any external service or dependency.

| Requirement | How it is satisfied |
|---|---|
| Acknowledge before processing | Webhook handler inserts the job row and returns 200 immediately |
| Deduplication | `INSERT OR IGNORE` on the `message_id` primary key |
| Per-user rate limiting | In-memory `aiolimiter.AsyncLimiter` dict keyed by `user_id` |
| Retry with backoff | `run_after` column updated on failure with exponential delay |
| Single process, no Redis | Worker runs as a coroutine in the ASGI lifespan; no external broker |

A custom table (rather than `persist-queue`, `huey`, or `stq`) is the preferred implementation because it uses `aiosqlite` directly (already in the stack), gives full control over schema and indexes, and keeps the queue logic visible and auditable within the project's own codebase.

### Secondary: `asyncio.Queue` + worker coroutines (Option 3)

If the deployment context makes process restarts rare and graceful, and losing a handful of in-flight messages is acceptable, Option 3 is simpler to implement and test. The worker logic is nearly identical to Option 5: the only difference is whether the queue is backed by SQLite rows or `asyncio.Queue` slots. This is a valid starting point that can be upgraded to Option 5 without changing the worker or rate-limiting code.

### Required packages (both options)

| Package | Purpose |
|---|---|
| `aiosqlite` | Async SQLite access (likely already in the stack) |
| `aiolimiter` | Per-user async rate limiting (leaky-bucket, asyncio-native) |
| `tenacity` | Retry/backoff decorator for AI API calls |

No Redis. No Celery. No arq. No additional system processes.

---

## Rejected Options Summary

| Option | Reason for rejection |
|---|---|
| BackgroundTasks | No persistence, no queue, no backpressure; confirmed bugs with exception handling |
| Redis + arq | Excellent product but requires Redis, violating the single-process no-external-infra constraint |
| ad-hoc create_task | Unbounded concurrency, no backpressure, no advantage over asyncio.Queue |

---

## References

- [FastAPI BackgroundTasks documentation](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [Managing Background Tasks in FastAPI: BackgroundTasks vs ARQ + Redis](https://davidmuraya.com/blog/fastapi-background-tasks-arq-vs-built-in/)
- [FastAPI BackgroundTasks blocks entire application (Discussion #11210)](https://github.com/fastapi/fastapi/discussions/11210)
- [BackgroundTasks do not run when request failed (Issue #2604)](https://github.com/fastapi/fastapi/issues/2604)
- [arq documentation — deduplication and retry](https://arq-docs.helpmanual.io/)
- [arq GitHub repository](https://github.com/python-arq/arq)
- [Building Resilient Task Queues in FastAPI with ARQ Retries](https://davidmuraya.com/blog/fastapi-arq-retries/)
- [persist-queue PyPI](https://pypi.org/project/persist-queue/)
- [litequeue — queue built on top of SQLite](https://github.com/litements/litequeue)
- [STQ — simple SQLite task queue](https://github.com/danthedeckie/stq)
- [aiolimiter documentation](https://aiolimiter.readthedocs.io/)
- [tenacity — retrying library for Python](https://tenacity.readthedocs.io/)
- [Implementing Retry and Timeout Strategies in AI APIs (2026)](https://dasroot.net/posts/2026/02/implementing-retry-timeout-strategies-ai-apis/)
- [Guide to WhatsApp Webhooks: features and best practices](https://hookdeck.com/webhooks/platforms/guide-to-whatsapp-webhooks-features-and-best-practices)
- [Webhook deduplication checklist for developers](https://latenode.com/blog/integration-api-management/webhook-setup-configuration/webhook-deduplication-checklist-for-developers)
- [Webhooks at Scale: Best Practices](https://hookdeck.com/blog/webhooks-at-scale)
- [Python Background Task Processing in 2025](https://danielsarney.com/blog/python-background-task-processing-2025-handling-asynchronous-work-modern-applications/)
- [Asyncio Queue — Python 3 documentation](https://docs.python.org/3/library/asyncio-queue.html)
- [Litestar SAQ plugin](https://pypi.org/project/litestar-saq/)
- [Effective Strategies for Rate Limiting Async Requests in Python](https://proxiesapi.com/articles/effective-strategies-for-rate-limiting-asynchronous-requests-in-python)
