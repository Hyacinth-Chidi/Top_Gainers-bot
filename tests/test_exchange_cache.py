import asyncio

from exchanges.client import ExchangeClient


def test_gainers_and_losers_share_one_fetch():
    client = ExchangeClient.__new__(ExchangeClient)
    client.exchanges = {"binance": object()}
    client._ticker_cache = {}
    client._fetch_locks = {}
    calls = []

    async def fake_fetch(name):
        calls.append(name)
        return [{"symbol": s, "change_24h": c} for s, c in (("A", 5), ("B", -3), ("C", 9))]

    client._fetch_exchange_tickers_uncached = fake_fetch

    async def scenario():
        gainers = await client.get_top_gainers("binance", 2)
        losers = await client.get_top_losers("binance", 2)
        # Concurrent callers also share the in-flight fetch
        await asyncio.gather(*(client.get_top_gainers("binance") for _ in range(5)))
        return gainers, losers

    gainers, losers = asyncio.run(scenario())
    assert [g["symbol"] for g in gainers] == ["C", "A"]
    assert [l["symbol"] for l in losers] == ["B", "A"]
    assert calls == ["binance"]
