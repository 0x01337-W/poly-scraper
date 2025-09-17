import asyncio
import os
from src.workers.markets import run_markets_worker
from src.workers.trades import run_trades_worker
from src.workers.candles import run_candles_worker
from src.workers.orderbook import run_orderbook_worker


async def main() -> None:
    poll_ms = int(os.getenv("POLL_INTERVAL_MARKETS_MS", "10000"))
    trades_ms = int(os.getenv("POLL_INTERVAL_TRADES_MS", "3000"))
    enable_trades = os.getenv("ENABLE_TRADES_INGESTER", "false").lower() == "true"
    enable_candles = os.getenv("ENABLE_CANDLES_WORKER", "false").lower() == "true"
    enable_orderbook = os.getenv("ENABLE_ORDERBOOK_WORKER", "false").lower() == "true"

    tasks = [asyncio.create_task(run_markets_worker(poll_ms=poll_ms))]
    if enable_trades:
        tasks.append(asyncio.create_task(run_trades_worker(poll_ms=trades_ms)))
    if enable_candles:
        tasks.append(asyncio.create_task(run_candles_worker()))
    if enable_orderbook:
        tasks.append(asyncio.create_task(run_orderbook_worker()))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())

