"""Rate limiting configuration using slowapi.

Development Notice:
By default, this limiter uses an in-memory storage strategy keyed by client IP.
In multi-worker production deployments, configure a persistent backend (such as Redis)
to share rate limit counters across worker processes.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    headers_enabled=False,
)
