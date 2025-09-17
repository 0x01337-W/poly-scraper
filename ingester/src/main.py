import asyncio
import os
from src.workers.markets import run_markets_worker


async def main() -> None:
    poll_ms = int(os.getenv("POLL_INTERVAL_MARKETS_MS", "10000"))
    await run_markets_worker(poll_ms=poll_ms)


if __name__ == "__main__":
    asyncio.run(main())

