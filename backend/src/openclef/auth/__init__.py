"""Native auth subsystem for openclef.

Layered modules so each piece is testable in isolation:
- `hashing` — argon2 wrapper that mixes in the per-install pepper
- `sessions` — itsdangerous signer + Redis-backed revocation set
- `ratelimit` — Redis token bucket per username (login throttling)
- `bootstrap` — first-run admin from env vars (called from lifespan)
- `deps` — FastAPI dependencies (current_user, require_admin)

OIDC support is intentionally deferred to ticket 0143.
"""
