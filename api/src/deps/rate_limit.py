import os
import time
from fastapi import HTTPException, status, Request


class TokenBucket:
    def __init__(self, rate_per_sec: float, burst: int, daily_cap: int) -> None:
        self.rate_per_sec = rate_per_sec
        self.capacity = burst
        self.tokens = burst
        self.last = time.time()
        self.daily_cap = daily_cap
        self.daily_used = 0
        self.day_start = int(time.time() // 86400)

    def allow(self) -> bool:
        now = time.time()
        elapsed = now - self.last
        self.last = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_sec)
        # reset daily window if a day boundary has passed
        day_now = int(now // 86400)
        if day_now != self.day_start:
            self.day_start = day_now
            self.daily_used = 0
        if self.daily_used >= self.daily_cap:
            return False
        if self.tokens >= 1:
            self.tokens -= 1
            self.daily_used += 1
            return True
        return False


_buckets: dict[str, TokenBucket] = {}


def require_rate_limit(request: Request) -> None:
    # Exempt admin routes from public rate limiting
    if request.url.path.startswith("/admin"):
        return
    key = getattr(request.state, "api_key", None)
    if not key:
        # Auth must run first
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    rps = float(os.getenv("API_RATE_RPS", "10"))
    daily_cap = int(os.getenv("API_DAILY_CAP", "100000"))
    burst = max(1, int(rps * 2))

    bucket = _buckets.get(key)
    if bucket is None:
        bucket = TokenBucket(rate_per_sec=rps, burst=burst, daily_cap=daily_cap)
        _buckets[key] = bucket
    if not bucket.allow():
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")


