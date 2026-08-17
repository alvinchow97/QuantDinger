"""
moomoo (Futu OpenD) Trading Module

Supports US/HK/CN stock trading via a locally running OpenD gateway,
mirroring the IBKR/TWS integration shape.

Default OpenD port: 11111
"""

from app.services.moomoo_trading.client import MoomooClient, MoomooConfig
from app.services.moomoo_trading.symbols import normalize_symbol, parse_symbol

__all__ = ['MoomooClient', 'MoomooConfig', 'normalize_symbol', 'parse_symbol']
