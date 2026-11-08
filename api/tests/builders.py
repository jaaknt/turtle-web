"""Hand-built fills and closes for the ledger and analytics tests."""

from datetime import date, timedelta

from turtleweb.ledger import Close, Fill

BENCH = "BENCH.US"
D0 = date(2026, 1, 5)  # a Monday


def day(n: int) -> date:
    return D0 + timedelta(days=n)


def closes(symbol: str, prices: list[float], adjusted: list[float] | None = None, start: int = 0) -> list[Close]:
    """One close per day from day(start); adjusted defaults to the raw price."""
    adjusted = adjusted or prices
    return [Close(symbol, day(start + i), c, a) for i, (c, a) in enumerate(zip(prices, adjusted, strict=True))]


def buy(n: int, symbol: str, quantity: float, price: float, fee: float = 0.0) -> Fill:
    return Fill(day(n), symbol, "buy", quantity, price, fee, 0.0)


def sell(n: int, symbol: str, quantity: float, price: float, fee: float = 0.0) -> Fill:
    return Fill(day(n), symbol, "sell", quantity, price, fee, 0.0)
