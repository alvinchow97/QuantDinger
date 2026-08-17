"""
Symbol Mapping and Conversion

Converts QuantDinger system symbols to moomoo/Futu OpenD contract codes.

moomoo (Futu OpenD) codes are market-prefixed, e.g. "US.AAPL", "HK.00700".
"""

from typing import Optional, Tuple

_MARKET_PREFIX = {
    "USStock": "US",
    "HKStock": "HK",
    "CNStock": "SH",  # Shanghai; A-shares also use "SZ" for Shenzhen
}

_PREFIX_MARKET = {v: k for k, v in _MARKET_PREFIX.items()}


def normalize_symbol(symbol: str, market_type: str) -> str:
    """
    Convert a system symbol to a moomoo contract code.

    Args:
        symbol: Symbol code in the system (e.g. "AAPL", "0700")
        market_type: Market type ("USStock", "HKStock", "CNStock")

    Returns:
        moomoo contract code (e.g. "US.AAPL", "HK.00700")
    """
    symbol = (symbol or "").strip().upper()
    prefix = _MARKET_PREFIX.get((market_type or "").strip(), "US")

    if prefix == "HK":
        # HK codes are zero-padded to 5 digits, e.g. 700 -> 00700
        digits = symbol.lstrip("HK.").strip()
        if digits.isdigit():
            symbol = digits.zfill(5)

    return f"{prefix}.{symbol}"


def parse_symbol(code: str) -> Tuple[str, Optional[str]]:
    """
    Parse a moomoo contract code back into a system symbol and market type.

    Args:
        code: moomoo contract code (e.g. "US.AAPL")

    Returns:
        (clean_symbol, market_type)
    """
    code = (code or "").strip().upper()
    if "." in code:
        prefix, symbol = code.split(".", 1)
    else:
        prefix, symbol = "US", code

    market_type = _PREFIX_MARKET.get(prefix, "USStock")
    return symbol, market_type


def format_display_symbol(code: str) -> str:
    """Convert a moomoo contract code back to a display symbol."""
    symbol, _ = parse_symbol(code)
    return symbol
