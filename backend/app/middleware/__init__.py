"""ASGI middleware — idempotency + write-rate-limiting, both scoped to the
same set of financial/state-changing write routes. See write_routes.py for
the shared route matcher, idempotency.py and rate_limit.py for the two
middlewares themselves, and app/main.py for how they're installed.
"""

from __future__ import annotations
