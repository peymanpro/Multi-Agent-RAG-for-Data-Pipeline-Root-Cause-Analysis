# Distributed API Rate Limiting

The API rate-limits `POST /v1/investigations` using a fixed window. Every request consumes an IP budget; authenticated requests also consume a subject budget. This protects against repeated invalid-token probes while enforcing per-user budgets after authentication.

## Local development

The default in-memory backend is process-local and intended only for local development, tests, and a single process. Its state is not shared between workers and resets when the process restarts. The readiness endpoint identifies this backend as `process-local`.

The defaults are 30 requests per identity per 60-second fixed window. Override them with `RCA_RATE_LIMIT_REQUESTS` and `RCA_RATE_LIMIT_WINDOW_SECONDS`, both positive integers.

## Multi-worker / production deployment

Install the optional Redis dependency:

```bash
python -m pip install -e ".[api-redis]"
```

Configure a shared Redis instance:

```bash
export RCA_DEPLOYMENT_MODE=production
export RCA_RATE_LIMIT_REDIS_URL='rediss://rate-limit-user:secret@redis.example.internal:6379/0'
export RCA_API_USERS_JSON='[{"subject":"operator","token":"replace-with-a-random-secret-of-at-least-32-characters","scopes":["investigations:run"]}]'
export RCA_RATE_LIMIT_REQUESTS=30
export RCA_RATE_LIMIT_WINDOW_SECONDS=60
uvicorn pipeline_rca.api.app:app --host 0.0.0.0 --port 8000 --workers 4
```

Production mode refuses to start without a configured identity registry and a distributed rate-limit backend. The Redis implementation uses a single atomic Lua script (`INCR` + `PEXPIRE`) and hashes identity keys before storing them. Each worker talks to the same Redis namespace, so the counter is shared across workers and replicas. Use a private network, TLS (`rediss://`), ACL credentials with only the required key operations, and an appropriate Redis availability/retention policy.

## Response behavior

Successful investigation responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`. Rejected requests receive HTTP 429 and `Retry-After`. If Redis cannot enforce the budget, the API returns 503 rather than silently falling back to per-process limits.

The fixed-window algorithm can allow a burst around a window boundary. For workloads requiring smoother behavior, a token bucket or sliding window can be added behind the same `RateLimitStore` contract and evaluated with the same contract tests. Limit budgets are application-level protection and should complement, not replace, gateway/WAF quotas, request timeouts, concurrency controls, and upstream capacity planning.
